const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
let latest = { feedback: { intensity: 0, valid: false }, running: false };
let source = null;
let mission = null;
let paused = false;
let soundOn = false;
let audio = null;
let lastRender = performance.now();

const canvas = $('#arena');
const ctx = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;
const W = canvas.width, H = canvas.height;
const keys = new Set();
const pulseHistory = [];
const eventHistory = [];

const walls = [
  {x:0,y:0,w:960,h:24},{x:0,y:576,w:960,h:24},{x:0,y:0,w:24,h:600},{x:936,y:0,w:24,h:600},
  {x:220,y:24,w:20,h:170},{x:220,y:280,w:20,h:296},{x:460,y:24,w:20,h:105},{x:460,y:205,w:20,h:210},{x:460,y:490,w:20,h:86},
  {x:700,y:24,w:20,h:190},{x:700,y:290,w:20,h:286},{x:24,y:184,w:130,h:20},{x:286,y:184,w:155,h:20},
  {x:539,y:184,w:150,h:20},{x:764,y:184,w:172,h:20},{x:24,y:414,w:130,h:20},{x:286,y:414,w:155,h:20},
  {x:539,y:414,w:150,h:20},{x:764,y:414,w:172,h:20}
];
const lockers = [{x:70,y:100,w:94,h:58},{x:330,y:235,w:92,h:52},{x:570,y:330,w:90,h:54},{x:790,y:95,w:92,h:58}];
const spawn = {x:80,y:500};
const coreSpawns = [{x:110,y:90},{x:370,y:505},{x:830,y:335}];
const watcherSpawns = [{x:365,y:90},{x:825,y:500}];

function send(obj) { if (ws.readyState === 1) ws.send(JSON.stringify(obj)); }
ws.addEventListener('open', () => { $('#connection-dot').style.background = 'var(--mint)'; $('#connection-label').textContent = 'LINKED'; });
ws.addEventListener('close', () => { $('#connection-dot').style.background = 'var(--coral)'; $('#connection-label').textContent = 'OFFLINE'; });
ws.addEventListener('message', e => {
  const msg = JSON.parse(e.data);
  if (msg.type === 'state') { latest = msg.state; receiveState(latest); }
  if (msg.type === 'hrv') showToast(msg.result.error || 'HRV session complete');
});

function receiveState(s) {
  const fb = s.feedback || {};
  $('#bpm').textContent = fb.bpm == null ? '--' : Math.round(fb.bpm);
  $('#delta').textContent = fb.baseline ? `BASELINE ${Math.round(fb.baseline)} / ${fb.delta >= 0 ? '+' : ''}${Math.round(fb.delta)} Δ` : 'BASELINE CALIBRATING';
  $('#calibration-progress').style.width = `${Math.round((fb.calibration || 0) * 100)}%`;
  $('#source-label').textContent = source === 'camera' ? 'LIVE rPPG' : source === 'demo' ? 'SYNTHETIC FFT' : source === 'replay' ? 'SIM REPLAY' : 'NO SOURCE';
  const q = s.quality == null ? '--' : `QUALITY ${Math.round(s.quality * 100)}%`;
  $('#quality-label').textContent = q;
  const status = $('#signal-status'); status.textContent = fb.valid ? 'LINKED' : 'WAITING'; status.classList.toggle('online', !!fb.valid);
  $('#signal-message').textContent = fb.valid ? 'The measured pulse is controlling the detection field.' : (fb.reason || 'Establishing a stable signal.');
  $('#mode-badge').textContent = mission?.started ? (fb.valid ? 'FEEDBACK ACTIVE' : 'SIGNAL PAUSED') : (fb.baseline ? 'LINK READY' : 'AWAITING LINK');
  if (!mission?.started && fb.baseline) { $('#launch').disabled = false; $('#launch').textContent = 'LAUNCH MISSION'; }
  if (s.trace?.pulse) drawWave($('#pulse-chart'), s.trace.pulse, '#91f2ce');
  if (s.bcg) {
    $('#bcg-result').textContent = s.bcg.usable ? `${s.bcg.bpm} BPM / quality ${Math.round(s.bcg.quality*100)}%` : 'No usable camera BCG yet';
    $('#bcg-detail').textContent = s.bcg.reason || '';
    if (s.bcg.pulse) drawWave($('#bcg-chart'), s.bcg.pulse, '#f1c877');
  }
  if (s.jpeg) $('#feed').src = '/video.mjpg?t=' + Date.now();
  pulseHistory.push({t: performance.now()/1000, bpm: fb.bpm, intensity: fb.intensity || 0, valid: !!fb.valid});
  while (pulseHistory.length && pulseHistory[0].t < performance.now()/1000 - 600) pulseHistory.shift();
}

function drawWave(c, values, color) {
  const c2 = c.getContext('2d'), w = c.width, h = c.height;
  c2.clearRect(0,0,w,h); c2.strokeStyle = '#243432'; c2.lineWidth = 1;
  c2.beginPath(); c2.moveTo(0,h/2); c2.lineTo(w,h/2); c2.stroke();
  if (!values?.length) return;
  c2.strokeStyle = color; c2.lineWidth = 1.7; c2.beginPath();
  values.forEach((v,i) => { const x=i/(values.length-1)*w; const y=h/2-Math.max(-2,Math.min(2,v))*h*.22; i ? c2.lineTo(x,y) : c2.moveTo(x,y); }); c2.stroke();
}

function pickSource(kind) {
  if (mission?.started) endMission(false);
  source = kind;
  $$('.source-option').forEach(x => x.classList.toggle('active', x.id === `source-${kind}`));
  $('#scenario-control').hidden = kind !== 'demo';
  $('#camera-preview').hidden = kind !== 'camera';
  $('#cover').hidden = true;
  $('#launch').disabled = true;
  $('#launch').textContent = 'CALIBRATING SIGNAL';
  $('#quick-camera').textContent = 'LINK MY CAMERA';
  if (kind === 'demo') send({cmd:'demo'});
  else if (kind === 'camera') { send({cmd:'start', source:'webcam'}); $('#feed').src='/video.mjpg'; }
  else send({cmd:'start', source:'sim', options:{fitzpatrick:2, motion:.3}});
  showToast(kind === 'camera' ? 'Camera stays local. Look at the preview and hold still.' : 'Synthetic pulse is running through the real feedback controller.');
}
$('#source-demo').onclick = () => pickSource('demo');
$('#source-camera').onclick = () => pickSource('camera');
$('#source-replay').onclick = () => pickSource('replay');
$('#quick-demo').onclick = () => pickSource('demo');
$('#quick-camera').onclick = () => pickSource('camera');
$('#recalibrate').onclick = () => { send({cmd:'calibrate'}); resetMission(); showToast('Baseline cleared. Remain still for calibration.'); };
$('#scenario').onchange = e => send({cmd:'scenario', value:e.target.value});
$('#feedback-mode').onchange = () => { if(mission) addEvent(`Feedback rule: ${$('#feedback-mode').selectedOptions[0].text}`); };
$('#nav-sensors').onclick = () => $('#sensor-dialog').showModal();
$('#close-sensors').onclick = () => $('#sensor-dialog').close();
$('#sound').onclick = () => { soundOn = !soundOn; $('#sound').textContent = soundOn ? 'SOUND ON' : 'SOUND OFF'; if (soundOn) beep(220, .06); };

$('#launch').onclick = () => { if (!latest.feedback?.baseline) return; startMission(); };
function startMission() {
  mission = {started:true, start:performance.now(), elapsed:0, player:{...spawn}, cores:coreSpawns.map(p=>({...p, collected:false})), watchers:watcherSpawns.map((p,i)=>({x:p.x,y:p.y,base:{...p},phase:i*2,alert:0,stun:0})), decoys:3, integrity:3, hidden:false, ended:false, events:[], frame:[]};
  paused=false; $('#pause').disabled=false; $('#cover').hidden=true; $('#launch').disabled=true; $('#launch').textContent='MISSION RUNNING'; $('#objective').textContent='COLLECT THE MEMORY CORES'; $('#game-message').textContent='Keep to the shadows.'; $('#event-log').innerHTML=''; $('#cores').innerHTML='00 <small>/ 03</small>'; $('#integrity').textContent='INTEGRITY 3 / 3'; addEvent('Signal link established. Entering sector.'); canvas.focus();
}
function resetMission(){ if(mission?.started) endMission(false); mission=null; $('#cover').hidden=false; $('#cover-title').textContent='Enter the quiet.'; $('#cover-copy').innerHTML='Your heartbeat shapes how far the watchers can sense you.<br>Use cover. Choose your moment. Leave no trace.'; $('#launch').disabled=true; $('#launch').textContent='WAITING FOR SIGNAL'; }
$('#retry').onclick = () => { $('#replay-section').hidden=true; resetMission(); startMission(); };
$('#pause').onclick = () => { paused=!paused; $('#pause').textContent=paused?'RESUME':'PAUSE'; addEvent(paused?'Mission paused.':'Mission resumed.'); };
window.addEventListener('keydown', e => { if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight',' ','w','a','s','d','W','A','S','D','e','E','Escape'].includes(e.key)) e.preventDefault(); if(e.key==='Escape' && mission?.started) $('#pause').click(); if(e.key===' ' && mission?.started) deployDecoy(); if((e.key==='e'||e.key==='E') && mission?.started) interact(); keys.add(e.key.toLowerCase()); });
window.addEventListener('keyup', e => keys.delete(e.key.toLowerCase()));
$$('.touch-controls button').forEach(b=>{b.onpointerdown=()=>{if(b.dataset.key)keys.add(b.dataset.key.toLowerCase()); else b.dataset.action==='decoy'?deployDecoy():interact()};b.onpointerup=()=>{if(b.dataset.key)keys.delete(b.dataset.key.toLowerCase())};});

function resetEntities(){ return {player:{...spawn},cores:coreSpawns.map(p=>({...p,collected:false})),watchers:watcherSpawns.map((p,i)=>({x:p.x,y:p.y,base:{...p},phase:i*2,alert:0,stun:0})),decoys:3,integrity:3,hidden:false}; }
function collide(x,y,r=10){ return walls.some(w=>x+r>w.x&&x-r<w.x+w.w&&y+r>w.y&&y-r<w.y+w.h); }
function movePlayer(dx,dy){ const p=mission.player, speed=105; let nx=p.x+dx*speed, ny=p.y+dy*speed; if(!collide(nx,p.y))p.x=Math.max(35,Math.min(925,nx)); if(!collide(p.x,ny))p.y=Math.max(35,Math.min(565,ny)); }
function inLocker(){return lockers.some(l=>mission.player.x>l.x&&mission.player.x<l.x+l.w&&mission.player.y>l.y&&mission.player.y<l.y+l.h)}
function lineBlocked(a,b){ const n=Math.ceil(Math.hypot(a.x-b.x,a.y-b.y)/7); for(let i=1;i<n;i++){const x=a.x+(b.x-a.x)*i/n,y=a.y+(b.y-a.y)*i/n;if(walls.some(w=>x>w.x&&x<w.x+w.w&&y>w.y&&y<w.y+w.h))return true} return false; }
function interact(){if(!mission)return; mission.hidden=inLocker(); const core=mission.cores.find(c=>!c.collected&&Math.hypot(c.x-mission.player.x,c.y-mission.player.y)<34); if(core){core.collected=true; addEvent(`Memory core ${mission.cores.filter(c=>c.collected).length} recovered.`); $('#cores').innerHTML=`${String(mission.cores.filter(c=>c.collected).length).padStart(2,'0')} <small>/ 03</small>`; beep(560,.1); if(mission.cores.every(c=>c.collected)){ $('#objective').textContent='RETURN TO EXTRACTION'; addEvent('All cores recovered. Extraction pad is live.'); }} else if(mission.hidden)addEvent('Cover engaged. Watchers cannot see you through a locker.'); }
function deployDecoy(){if(!mission||mission.decoys<=0)return; mission.decoys--;$('#decoys').textContent=mission.decoys; mission.decoy={x:mission.player.x,y:mission.player.y,until:performance.now()+5000};addEvent('Decoy pulse deployed. Watchers are investigating.');beep(160,.16);}
function updateGame(dt){ if(!mission?.started||mission.ended||paused)return; mission.elapsed=(performance.now()-mission.start)/1000; const up=keys.has('w')||keys.has('arrowup'),down=keys.has('s')||keys.has('arrowdown'),left=keys.has('a')||keys.has('arrowleft'),right=keys.has('d')||keys.has('arrowright'); let dx=(right?1:0)-(left?1:0),dy=(down?1:0)-(up?1:0);if(dx||dy){const q=Math.hypot(dx,dy);movePlayer(dx/q*dt,dy/q*dt)} mission.hidden=inLocker(); const mode=$('#feedback-mode').value; const intensity=mode==='fixed'?0:(latest.feedback?.valid?latest.feedback.intensity||0:0); const radius=mode==='balance'?1-.32*intensity:1+.7*intensity; mission.radius=radius;
  mission.watchers.forEach(w=>{if(w.stun>0){w.stun-=dt;return}const p=mission.player;const distance=Math.hypot(w.x-p.x,w.y-p.y);let target=null;if(mission.decoy&&performance.now()<mission.decoy.until)target=mission.decoy;else if(!mission.hidden&&!lineBlocked(w,p)&&distance<125*radius){target=p;w.alert=Math.min(1,w.alert+dt*.7)}else w.alert=Math.max(0,w.alert-dt*.3);if(target){const d=Math.max(1,Math.hypot(target.x-w.x,target.y-w.y));const speed=28+35*w.alert;const nx=w.x+(target.x-w.x)/d*speed*dt,ny=w.y+(target.y-w.y)/d*speed*dt;if(!collide(nx,w.y,12))w.x=nx;if(!collide(w.x,ny,12))w.y=ny}else{w.x=w.base.x+Math.cos(mission.elapsed*.35+w.phase)*23;w.y=w.base.y+Math.sin(mission.elapsed*.28+w.phase)*18}if(target===p&&distance<22){mission.integrity--;w.x=w.base.x;w.y=w.base.y;w.alert=0;addEvent(`Watcher contact. Integrity ${mission.integrity} / 3.`);$('#integrity').textContent=`INTEGRITY ${mission.integrity} / 3`;beep(90,.2);if(mission.integrity<=0)endMission(false)}});if(mission.decoy&&performance.now()>mission.decoy.until)mission.decoy=null;const exit={x:875,y:510};if(mission.cores.every(c=>c.collected)&&Math.hypot(exit.x-mission.player.x,exit.y-mission.player.y)<34)endMission(true); mission.frame.push({t:mission.elapsed,bpm:latest.feedback?.bpm||null,intensity:latest.feedback?.intensity||0,radius,px:mission.player.x,py:mission.player.y,hidden:mission.hidden});if(mission.frame.length>3600)mission.frame.shift();updateHud(radius); }
function updateHud(radius){const val=radius||1;$('#field-value').innerHTML=`${val.toFixed(2)}<small>×</small>`;$('#field-label').textContent=val>1.3?'ELEVATED':val<.9?'CALM':'NOMINAL';$('#field-label').style.color=val>1.3?'var(--coral)':'var(--gold)';const on=Math.round(Math.min(1.5,val)/1.5*8);$('#field-bars').innerHTML=Array.from({length:8},(_,i)=>`<i class="${i<on?'on':''}"></i>`).join('');$('#danger-vignette').style.opacity=Math.max(0,(val-1)*.45); }
function endMission(success){if(!mission||mission.ended)return;mission.ended=true;mission.success=success;$('#pause').disabled=true;$('#cover').hidden=false;$('#cover-title').textContent=success?'Extraction complete.': 'Signal lost.';$('#cover-copy').innerHTML=success?'Three cores recovered. The quiet array is yours.':'The watchers found you. Every run teaches the director.';$('#quick-demo').textContent='REVIEW SESSION';$('#quick-camera').textContent='NEW MISSION';$('#quick-demo').onclick=()=>{$('#cover').hidden=true;showReplay()};$('#quick-camera').onclick=()=>{resetMission();pickSource(source||'demo')};addEvent(success?'Mission complete.':'Mission failed.');showReplay(); }
function addEvent(text){const t=mission?mission.elapsed:0;eventHistory.push({t,text});if(eventHistory.length>100)eventHistory.shift();const p=document.createElement('p');p.innerHTML=`<time>${fmt(t)}</time>${text}`;$('#event-log').prepend(p);if(mission)mission.events.push({t,text});}
function fmt(s){return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`}
function showReplay(){const frames=mission?.frame||[];$('#replay-section').hidden=false;$('#result-title').textContent=mission.success?'Mission complete.':'Mission interrupted.';$('#result-copy').textContent=mission.success?'You crossed the field without asking your body to perform. The director adapted gradually to the measured signal.':'The response is part of the experiment. Review where signal quality and detection diverged.';const valid=frames.filter(f=>f.bpm);const mean=valid.length?valid.reduce((a,f)=>a+f.bpm,0)/valid.length:0;const maxR=frames.length?Math.max(...frames.map(f=>f.radius)):1;$('#result-stats').innerHTML=`<div><span>MISSION TIME</span><strong>${fmt(frames.at(-1)?.t||0)}</strong></div><div><span>RECOVERED</span><strong>${mission.cores.filter(c=>c.collected).length} / 3</strong></div><div><span>MEASURED BPM</span><strong>${mean?Math.round(mean):'--'}</strong></div><div><span>MAX DETECTION</span><strong>${maxR.toFixed(2)}×</strong></div>`;drawSession();$('#replay-section').scrollIntoView({behavior:'smooth',block:'start'});}
function drawSession(){const c=$('#session-chart'),x=c.getContext('2d'),f=mission?.frame||[];x.clearRect(0,0,c.width,c.height);x.fillStyle='#101923';x.fillRect(0,0,c.width,c.height);if(!f.length)return;const maxT=f.at(-1).t||1;x.strokeStyle='#263b39';x.lineWidth=1;for(let i=0;i<5;i++){x.beginPath();x.moveTo(0,i*c.height/4);x.lineTo(c.width,i*c.height/4);x.stroke()}function line(key,color,scale,off){x.beginPath();let started=false;f.forEach(v=>{if(v[key]==null)return;const xx=v.t/maxT*c.width,yy=c.height-off-(v[key]/scale)*scale*.3;if(!started){x.moveTo(xx,yy);started=true}else x.lineTo(xx,yy)});x.strokeStyle=color;x.lineWidth=2;x.stroke()}line('bpm','#91f2ce',140,120);line('radius','#f1c877',1.5,150);x.fillStyle='#879f9a';x.font='10px IBM Plex Mono';x.fillText('PULSE',8,16);x.fillStyle='#c79d54';x.fillText('DETECTION',58,16);}
$('#replay-toggle').onclick=()=>{if(!mission?.frame.length)return;let i=0;const timer=setInterval(()=>{if(i>=mission.frame.length){clearInterval(timer);return}$('#scrub').value=i/mission.frame.length*100;drawScrub(i);i+=4},35)};
$('#scrub').oninput=e=>drawScrub(Math.round(e.target.value/100*(mission?.frame.length||1)));
function drawScrub(i){const f=mission?.frame[i];if(!f)return;$('#scrub-time').textContent=fmt(f.t);$('#field-value').innerHTML=`${f.radius.toFixed(2)}<small>×</small>`;}
$('#export').onclick=()=>{const data={experiment:'TRACE Ghost Protocol',success:mission?.success,events:mission?.events,frames:mission?.frame,signal_source:source,disclaimer:'Research gameplay telemetry, not a medical measurement or diagnosis.'};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download='trace-ghost-session.json';a.click();URL.revokeObjectURL(a.href)};

function beep(freq,dur){if(!soundOn)return;if(!audio)audio=new (window.AudioContext||window.webkitAudioContext)();const o=audio.createOscillator(),g=audio.createGain();o.frequency.value=freq;o.type='square';g.gain.value=.025;o.connect(g);g.connect(audio.destination);o.start();g.gain.exponentialRampToValueAtTime(.001,audio.currentTime+dur);o.stop(audio.currentTime+dur)}
function drawArena(){ctx.clearRect(0,0,W,H);ctx.fillStyle='#0b171f';ctx.fillRect(0,0,W,H);ctx.strokeStyle='#122a2c';ctx.lineWidth=1;for(let x=24;x<936;x+=24){ctx.beginPath();ctx.moveTo(x,24);ctx.lineTo(x,576);ctx.stroke()}for(let y=24;y<576;y+=24){ctx.beginPath();ctx.moveTo(24,y);ctx.lineTo(936,y);ctx.stroke()}walls.forEach(w=>{ctx.fillStyle='#172b31';ctx.fillRect(w.x,w.y,w.w,w.h);ctx.fillStyle='#284341';ctx.fillRect(w.x,w.y,w.w,2);ctx.fillStyle='#0c141c';ctx.fillRect(w.x+4,w.y+5,w.w-8,2)});lockers.forEach(l=>{ctx.fillStyle=mission?.hidden&&mission.player.x>l.x&&mission.player.x<l.x+l.w&&mission.player.y>l.y&&mission.player.y<l.y+l.h?'#52786d':'#203c3e';ctx.fillRect(l.x,l.y,l.w,l.h);ctx.strokeStyle='#45736a';ctx.strokeRect(l.x+.5,l.y+.5,l.w-1,l.h-1);ctx.fillStyle='#0b1a21';for(let x=l.x+12;x<l.x+l.w-4;x+=16)ctx.fillRect(x,l.y+10,5,l.h-20)});const exit={x:875,y:510};ctx.strokeStyle='#91f2ce';ctx.globalAlpha=.5+.2*Math.sin(performance.now()/300);ctx.strokeRect(exit.x-18,exit.y-18,36,36);ctx.globalAlpha=1;ctx.fillStyle='#91f2ce';ctx.font='9px IBM Plex Mono';ctx.fillText('EXIT',exit.x-12,exit.y+32);if(mission){mission.cores.forEach(c=>{if(c.collected)return;ctx.save();ctx.translate(c.x,c.y);ctx.rotate(Math.PI/4);ctx.fillStyle='#f1c877';ctx.shadowColor='#f1c877';ctx.shadowBlur=15;ctx.fillRect(-9,-9,18,18);ctx.shadowBlur=0;ctx.restore()});if(mission.decoy){ctx.strokeStyle='#f87868';ctx.beginPath();ctx.arc(mission.decoy.x,mission.decoy.y,12+Math.sin(performance.now()/80)*3,0,Math.PI*2);ctx.stroke()}mission.watchers.forEach(w=>{ctx.save();ctx.translate(w.x,w.y);ctx.fillStyle='#fa826e';ctx.shadowColor='#fa826e';ctx.shadowBlur=12;ctx.fillRect(-10,-8,20,16);ctx.shadowBlur=0;ctx.fillStyle='#3b1c26';ctx.fillRect(-5,-3,10,4);ctx.strokeStyle='#fa826e';ctx.globalAlpha=.25;ctx.beginPath();ctx.arc(0,0,125*(mission.radius||1),0,Math.PI*2);ctx.stroke();ctx.restore()});ctx.fillStyle='#91f2ce';ctx.shadowColor='#91f2ce';ctx.shadowBlur=12;ctx.fillRect(mission.player.x-8,mission.player.y-8,16,16);ctx.shadowBlur=0;ctx.strokeStyle='#b9ffe7';ctx.strokeRect(mission.player.x-11,mission.player.y-11,22,22);if(mission.hidden){ctx.strokeStyle='#91f2ce';ctx.globalAlpha=.65;ctx.beginPath();ctx.arc(mission.player.x,mission.player.y,16,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1}}}
function loop(now){const dt=Math.min(.04,(now-lastRender)/1000);lastRender=now;updateGame(dt);drawArena();requestAnimationFrame(loop)}requestAnimationFrame(loop);

$('#phone-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;$('#phone-result').textContent='Processing CSV locally on the TRACE server...';const r=await fetch('/api/phone/analyse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv:await file.text()})});const out=await r.json();if(!r.ok){$('#phone-result').textContent=out.error;return}$('#phone-result').textContent=`SCG research estimate: ${out.bpm} BPM, quality ${Math.round(out.quality*100)}%, respiration ${out.respiration_bpm||'--'} BPM. ${out.note}`;if(out.pulse)drawWave($('#phone-chart'),out.pulse,'#f1c877');};
$('#sample-csv').onclick=()=>{const fs=100,rows=['t,ax,ay,az'];for(let i=0;i<3000;i++){const t=i/fs;rows.push(`${t.toFixed(3)},${(9.81+.03*Math.sin(2*Math.PI*1.2*t)+.005*Math.sin(2*Math.PI*8*t)).toFixed(6)},${(.01*Math.sin(2*Math.PI*1.2*t)).toFixed(6)},${(.02*Math.sin(2*Math.PI*1.2*t)).toFixed(6)}`)}const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'}));a.download='trace-synthetic-accelerometer.csv';a.click()};
function showToast(text){const t=$('#toast');t.textContent=text;t.classList.add('visible');clearTimeout(showToast.timer);showToast.timer=setTimeout(()=>t.classList.remove('visible'),3500)}
// Initial state is intentionally quiet. The cover explains the experiment before a sensor starts.
drawArena();
