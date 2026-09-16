const $ = s => document.querySelector(s);
const canvas = $('#experience');
const ctx = canvas.getContext('2d');
const W = canvas.width, H = canvas.height;
const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
const feed = $('#camera-frame');
const pending = [];
let state = {feedback:{intensity:0, valid:false}};
let phase = 'welcome';
let source = null;
let paused = false;
let soundOn = false;
let audio;
let mission;
let last = performance.now();
const keys = new Set();
const rppgHistory = [];
const bcgHistory = [];
const methodHistory = [];

const walls = [
  {x:0,y:0,w:1040,h:20},{x:0,y:680,w:1040,h:20},{x:0,y:0,w:20,h:700},{x:1020,y:0,w:20,h:700},
  {x:245,y:20,w:18,h:180},{x:245,y:325,w:18,h:355},{x:510,y:20,w:18,h:115},{x:510,y:255,w:18,h:210},{x:510,y:565,w:18,h:115},
  {x:780,y:20,w:18,h:180},{x:780,y:325,w:18,h:355},{x:20,y:205,w:150,h:18},{x:320,y:205,w:150,h:18},{x:570,y:205,w:170,h:18},{x:840,y:205,w:180,h:18},
  {x:20,y:475,w:150,h:18},{x:320,y:475,w:150,h:18},{x:570,y:475,w:170,h:18},{x:840,y:475,w:180,h:18}
];
const hidingSpots = [{x:65,y:75,w:105,h:70},{x:355,y:255,w:100,h:60},{x:625,y:355,w:100,h:60},{x:855,y:75,w:100,h:70}];
const echoes = [{x:95,y:575},{x:390,y:85},{x:910,y:365}];
const hunterHome = [{x:400,y:95},{x:900,y:585}];

function send(obj){if(ws.readyState===1)ws.send(JSON.stringify(obj));else pending.push(obj);}
ws.onopen=()=>{$('#link-status').textContent='LINKED';$('#link-status').style.color='var(--mint)';while(pending.length)ws.send(JSON.stringify(pending.shift()));draw();};
ws.onclose=()=>{$('#link-status').textContent='OFFLINE';$('#link-status').style.color='var(--red)';};
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='state'){state=m.state;consumeState();}};

function consumeState(){
  const fb=state.feedback||{};
  if(fb.bpm!=null)rppgHistory.push({v:fb.bpm,ok:fb.valid});
  if(state.bcg?.bpm!=null)bcgHistory.push({v:state.bcg.bpm,ok:state.bcg.usable});
  if(state.methods)methodHistory.push({green:state.methods.green?.bpm,chrom:state.methods.chrom?.bpm,pos:state.methods.pos?.bpm});
  if(rppgHistory.length>100)rppgHistory.shift();
  if(bcgHistory.length>100)bcgHistory.shift();
  if(methodHistory.length>100)methodHistory.shift();
  if(phase==='scan' && fb.baseline && fb.calibration>=1){
    $('#enter-game').hidden=false;
    $('#camera-start').textContent='ENTER NIGHT';
    $('#control-message').textContent='Signal locked. Enter the facility when you are ready.';
  }
  draw();
}

function begin(kind){
  source=kind;phase='scan';paused=false;$('#source-controls').hidden=false;$('#game-controls').hidden=true;$('#enter-game').hidden=true;
  $('#camera-start').textContent='CALIBRATING';$('#camera-start').disabled=true;$('#simulation-start').disabled=true;
  if(kind==='camera'){send({cmd:'start',source:'webcam',options:{game_window:10}});feed.src='/video.mjpg?session='+Date.now();$('#canvas-note').textContent='LOCAL CAMERA / FRAMES NEVER LEAVE THIS COMPUTER';}
  else{send({cmd:'demo'});$('#canvas-note').textContent='SYNTHETIC SIGNAL / REPEATABLE DEMO';}
  $('#flow-step').textContent='SIGNAL CHECK';$('#headline').innerHTML='Watch the signal.<br><em>Before it watches you.</em>';$('#subhead').textContent='Keep your face still while TRACE separates colour pulse from tiny facial motion. Both channels will stay visible during the mission.';
  draw();
}
function enterGame(){if(!state.feedback?.baseline)return;phase='game';mission={start:performance.now(),t:0,player:{x:78,y:600},hunters:hunterHome.map((p,i)=>({x:p.x,y:p.y,home:{...p},a:0,phase:i*1.7})),echoes:echoes.map(p=>({...p,got:false})),flares:3,health:3,scare:0,nextScare:9,events:[],frames:[],ended:false};paused=false;$('#flow-step').textContent='NIGHT RUN';$('#camera-start').hidden=true;$('#simulation-start').hidden=true;$('#enter-game').hidden=true;$('#game-controls').hidden=false;$('#pause').disabled=false;$('#headline').innerHTML='The facility is awake.<br><em>Do not let it hear you.</em>';$('#subhead').textContent='Find the three echoes and reach the exit. When the signal jumps, the night gets closer.';$('#control-message').textContent='The right side of the canvas is your live monitor. Escape pauses the run.';canvas.focus();beep(180,.16);draw();}

$('#camera-start').onclick=()=>{if(phase==='scan')enterGame();else begin('camera');};
$('#simulation-start').onclick=()=>begin('demo');
const enter=document.createElement('button');enter.id='enter-game';enter.className='primary';enter.textContent='ENTER NIGHT';enter.hidden=true;enter.onclick=enterGame;$('#source-controls').append(enter);
$('#return-scan').onclick=()=>{if(mission?.frames.length)downloadSession();send({cmd:'stop'});phase='welcome';mission=null;paused=false;$('#camera-start').hidden=false;$('#simulation-start').hidden=false;$('#camera-start').disabled=false;$('#simulation-start').disabled=false;$('#camera-start').textContent='OPEN CAMERA';$('#game-controls').hidden=true;$('#headline').innerHTML='Something is listening<br><em>to your heartbeat.</em>';$('#subhead').textContent='First, let TRACE find your pulse. Then enter the facility and see what happens when the dark learns your rhythm.';draw();};
$('#pause').onclick=()=>{if(!mission)return;paused=!paused;$('#pause').textContent=paused?'RESUME':'PAUSE';draw();};
$('#settings').onclick=()=>$('#settings-dialog').showModal();$('#close-settings').onclick=()=>$('#settings-dialog').close();
$('#sound-toggle').onchange=e=>{soundOn=e.target.checked;if(soundOn)beep(240,.06);};
$('#feedback-mode').onchange=()=>{if(mission)mission.events.push({t:mission.t,text:'Feedback rule changed during run.'});};
window.addEventListener('keydown',e=>{const k=e.key.toLowerCase();if(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright',' ','e','escape'].includes(k))e.preventDefault();if(k==='escape'&&mission)$('#pause').click();if(k===' '&&mission&&!paused)flare();if(k==='e'&&mission&&!paused)interact();keys.add(k);});window.addEventListener('keyup',e=>keys.delete(e.key.toLowerCase()));

function beep(freq,dur=.1){if(!soundOn)return;if(!audio)audio=new(window.AudioContext||window.webkitAudioContext)();const o=audio.createOscillator(),g=audio.createGain();o.type='sawtooth';o.frequency.value=freq;g.gain.value=.035;o.connect(g);g.connect(audio.destination);o.start();g.gain.exponentialRampToValueAtTime(.001,audio.currentTime+dur);o.stop(audio.currentTime+dur);}
function collide(x,y,r=12){return walls.some(w=>x+r>w.x&&x-r<w.x+w.w&&y+r>w.y&&y-r<w.y+w.h)}
function inHiding(){return hidingSpots.some(s=>mission.player.x>s.x&&mission.player.x<s.x+s.w&&mission.player.y>s.y&&mission.player.y<s.y+s.h)}
function blocked(a,b){const n=Math.ceil(Math.hypot(a.x-b.x,a.y-b.y)/8);for(let i=1;i<n;i++){const x=a.x+(b.x-a.x)*i/n,y=a.y+(b.y-a.y)*i/n;if(walls.some(w=>x>w.x&&x<w.x+w.w&&y>w.y&&y<w.y+w.h))return true;}return false;}
function move(dx,dy,dt){const p=mission.player,s=125;let nx=p.x+dx*s*dt,ny=p.y+dy*s*dt;if(!collide(nx,p.y))p.x=Math.max(34,Math.min(1006,nx));if(!collide(p.x,ny))p.y=Math.max(34,Math.min(666,ny));}
function interact(){mission.hidden=inHiding();const e=mission.echoes.find(x=>!x.got&&Math.hypot(x.x-mission.player.x,x.y-mission.player.y)<35);if(e){e.got=true;mission.events.push({t:mission.t,text:`Echo recovered (${mission.echoes.filter(x=>x.got).length}/3).`});beep(600,.11);}else if(mission.hidden){mission.events.push({t:mission.t,text:'You held your breath inside the locker.'});}}
function flare(){if(mission.flares<=0)return;mission.flares--;mission.flare={x:mission.player.x,y:mission.player.y,end:performance.now()+4200};beep(480,.08);mission.events.push({t:mission.t,text:'Flare thrown. The dark moved.'});}
function triggerScare(){mission.scare=1.25;mission.nextScare=mission.t+12+Math.random()*7;mission.events.push({t:mission.t,text:'JUMPSCARE: acoustic event detected.'});beep(55,.5);if(source==='demo')send({cmd:'scenario',value:'scare'});setTimeout(()=>{if(source==='demo')send({cmd:'scenario',value:'cycle'});},3500);}
function update(dt){if(phase!=='game'||paused||mission.ended)return;mission.t=(performance.now()-mission.start)/1000;const u=keys.has('w')||keys.has('arrowup'),d=keys.has('s')||keys.has('arrowdown'),l=keys.has('a')||keys.has('arrowleft'),r=keys.has('d')||keys.has('arrowright');let dx=(r?1:0)-(l?1:0),dy=(d?1:0)-(u?1:0);if(dx||dy){const q=Math.hypot(dx,dy);move(dx/q,dy/q,dt);}mission.hidden=inHiding();if(mission.t>mission.nextScare&&$('#horror-intensity').value!=='quiet')triggerScare();mission.scare=Math.max(0,mission.scare-dt);
  const mode=$('#feedback-mode').value,valid=state.feedback?.valid,intensity=valid?state.feedback.intensity||0:0;const radius=mode==='fixed'?1:mode==='balance'?1-.35*intensity:1+.95*intensity;mission.radius=radius;
  mission.hunters.forEach(h=>{const p=mission.player,dist=Math.hypot(h.x-p.x,h.y-p.y);let target=null;if(mission.flare&&performance.now()<mission.flare.end)target=mission.flare;else if(!mission.hidden&&!blocked(h,p)&&dist<150*radius)target=p;if(target){const q=Math.max(1,Math.hypot(target.x-h.x,target.y-h.y)),speed=target===p?40+35*intensity:65;h.x+=(target.x-h.x)/q*speed*dt;h.y+=(target.y-h.y)/q*speed*dt;h.a=Math.min(1,h.a+dt);}else{h.a=Math.max(0,h.a-dt);h.x=h.home.x+Math.sin(mission.t*.35+h.phase)*25;h.y=h.home.y+Math.cos(mission.t*.29+h.phase)*20;}if(target===p&&dist<25){mission.health--;h.x=h.home.x;h.y=h.home.y;mission.events.push({t:mission.t,text:`The watcher touched you. Integrity ${mission.health}/3.`});beep(70,.25);if(mission.health<=0)finish(false);}});if(mission.flare&&performance.now()>mission.flare.end)mission.flare=null;
  const done=mission.echoes.every(e=>e.got),exit={x:965,y:605};if(done&&Math.hypot(exit.x-mission.player.x,exit.y-mission.player.y)<35)finish(true);mission.frames.push({t:mission.t,bpm:state.feedback?.bpm||null,baseline:state.feedback?.baseline||null,intensity,radius,valid,scare:mission.scare,health:mission.health});if(mission.frames.length>3600)mission.frames.shift();
}
function finish(success){if(mission.ended)return;mission.ended=true;mission.success=success;paused=true;$('#pause').disabled=true;$('#control-message').textContent=success?'You escaped the Night Signal. Review the pulse response below.':'The signal dropped to zero. Review what the director saw.';setTimeout(()=>downloadSession(),200);}
function downloadSession(){if(!mission)return;const payload={experiment:'TRACE Night Signal',success:mission.success,events:mission.events,frames:mission.frames,source,disclaimer:'Interactive research telemetry. Not a medical measurement or diagnosis.'};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));a.download='trace-night-signal.json';a.click();URL.revokeObjectURL(a.href);}

function text(s,x,y,size,color= '#dceae6',font='IBM Plex Mono',align='left'){ctx.fillStyle=color;ctx.font=`${size}px ${font}`;ctx.textAlign=align;ctx.fillText(s,x,y);ctx.textAlign='left';}
function rect(x,y,w,h,fill,stroke=null){ctx.fillStyle=fill;ctx.fillRect(x,y,w,h);if(stroke){ctx.strokeStyle=stroke;ctx.strokeRect(x+.5,y+.5,w-1,h-1);}}
function line(points,color,width=2){if(!points.length)return;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.stroke();}
function panel(x,y,w,h,title){rect(x,y,w,h,'#0b151e','#2a4240');text(title.startsWith('#')?'SESSION FLOW':title,x+15,y+22,10,'#91f2ce','IBM Plex Mono');}
function chart(x,y,w,h,arr,color,label,min=null,max=null){rect(x,y,w,h,'#081018','#263e3d');text(label,x+10,y+18,9,'#91aaa7');if(!arr.length)return;const vals=arr.map(a=>typeof a==='number'?a:a.v),lo=min??Math.min(...vals),hi=max??Math.max(...vals),span=hi-lo||1;line(vals.map((v,i)=>[x+10+i/(vals.length-1)*(w-20),y+h-12-(v-lo)/span*(h-30)]),color,2);}
function methodChart(x,y,w,h){rect(x,y,w,h,'#081018','#263e3d');text('rPPG / GREEN  CHROM  POS / LIVE BPM',x+10,y+18,9,'#91aaa7');if(!methodHistory.length)return;const colors={green:'#efc66d',chrom:'#ff8876',pos:'#91f2ce'};for(const key of Object.keys(colors)){const vals=methodHistory.map(a=>a[key]).filter(v=>v!=null);if(!vals.length)continue;line(vals.map((v,i)=>[x+10+i/Math.max(1,vals.length-1)*(w-20),y+h-12-(v-40)/100*(h-30)]),colors[key],2);}text('GREEN',x+w-150,y+18,8,colors.green);text('CHROM',x+w-100,y+18,8,colors.chrom);text('POS',x+w-50,y+18,8,colors.pos);}
function drawPreview(x,y,w,h){rect(x,y,w,h,'#111d25','#41534f');if(feed.complete&&feed.naturalWidth){ctx.drawImage(feed,x,y,w,h);}else{rect(x+80,y+45,w-160,h-100,'#182a32');ctx.fillStyle='#2e6861';ctx.beginPath();ctx.arc(x+w/2,y+h/2-15,58,0,Math.PI*2);ctx.fill();ctx.fillStyle='#081017';ctx.fillRect(x+w/2-34,y+h/2-27,20,8);ctx.fillRect(x+w/2+14,y+h/2-27,20,8);ctx.strokeStyle='#91f2ce';ctx.strokeRect(x+w/2-76,y+h/2-82,152,178);}text('LOCAL FACE TRACK',x+12,y+22,9,'#91f2ce');text('ROI / FOREHEAD + CHEEKS',x+12,y+h-13,8,'#8caaa2');}
function graphForPulse(vals){return vals.length?vals.map(a=>typeof a==='number'?a:a.v):[]}
function drawScan(){background();text('01 / SIGNAL ACQUISITION',42,40,11,'#91f2ce');text('TRACE is looking for a heartbeat in colour and motion.',42,68,21,'#dceae6','Barlow Condensed');drawPreview(42,94,500,345);panel(565,94,833,345,'LIVE READOUT / THREE OPTICAL METHODS + CAMERA BCG');const fb=state.feedback||{},bpm=fb.bpm?Math.round(fb.bpm):'--';text(String(bpm),595,190,94,fb.valid?'#91f2ce':'#7f9293','Barlow Condensed');text('BPM',735,184,18,'#8ca6a2');text(fb.baseline?`BASELINE ${Math.round(fb.baseline)}  /  ${fb.delta>=0?'+':''}${Math.round(fb.delta)} Δ`:'CALIBRATING PERSONAL BASELINE',595,216,10,'#8ca6a2');text(fb.valid?'PULSE LINKED':'WAITING FOR STABLE SIGNAL',595,243,10,fb.valid?'#91f2ce':'#efc66d');const methods=state.methods||{};[['GREEN',methods.green],['CHROM',methods.chrom],['POS',methods.pos]].forEach((m,i)=>{const yy=276+i*42;text(m[0],595,yy,9,'#8ca6a2');const v=m[1]?.bpm;text(v?`${v.toFixed(1)} BPM`:'--',700,yy,12,v?'#dceae6':'#657a7c');rect(820,yy-10,500,5,'#17252b');if(v)rect(820,yy-10,Math.min(1,Math.max(0,(m[1].quality||0)))*500,5,i===0?'#efc66d':i===1?'#ff8876':'#91f2ce');});text(state.bcg?.usable?'BCG LOCKED':'BCG / GATHERING MOTION',1135,204,9,state.bcg?.usable?'#91f2ce':'#efc66d');if(state.bcg?.bpm)text(`${state.bcg.bpm} BPM`,1135,228,16,'#efc66d','Barlow Condensed');text('Optical and mechanical channels remain separate.',1135,250,8,'#718a88');methodChart(42,474,660,205);chart(728,474,670,205,graphForPulse(bcgHistory),'#efc66d','rBCG / FACIAL MOTION BPM',40,140);text(fb.calibration>=1?'BASELINE LOCKED / READY':'HOLD STILL / BASELINE '+Math.round((fb.calibration||0)*100)+'%',42,735,11,fb.calibration>=1?'#91f2ce':'#efc66d');text('GREEN  /  CHROM  /  POS   =   DIFFERENT CLASSICAL VIEWS OF THE SAME FACE',42,765,9,'#718a88');if(fb.baseline&&fb.calibration>=1){rect(1065,718,333,45,'#91f2ce','#91f2ce');text('ENTER NIGHT  >>',1231,746,13,'#092019','IBM Plex Mono','center');}}
function background(){ctx.clearRect(0,0,W,H);rect(0,0,W,H,'#081119');ctx.strokeStyle='#10252a';ctx.lineWidth=1;for(let x=0;x<W;x+=32){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke();}for(let y=0;y<H;y+=32){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();}}
function drawGame(){background();const gW=1040;rect(22,22,gW,656,'#081219','#38544e');text('02 / NIGHT SIGNAL',42,49,11,'#91f2ce');text(`SURVIVE  ${fmt(mission.t)}    ECHOES ${mission.echoes.filter(e=>e.got).length}/3`,770,49,10,'#8aa39e','IBM Plex Mono','right');walls.forEach(w=>{rect(w.x+22,w.y+22,w.w,w.h,'#152a31','#294846');});hidingSpots.forEach(s=>{rect(s.x+22,s.y+22,s.w,s.h,mission.hidden&&mission.player.x>s.x&&mission.player.x<s.x+s.w&&mission.player.y>s.y&&mission.player.y<s.y+s.h?'#365f58':'#1a393c','#47756c');});mission.echoes.forEach(e=>{if(e.got)return;ctx.save();ctx.translate(e.x+22,e.y+22);ctx.rotate(Math.PI/4);ctx.fillStyle='#efc66d';ctx.shadowColor='#efc66d';ctx.shadowBlur=16;ctx.fillRect(-10,-10,20,20);ctx.restore();});const exit={x:965,y:605};ctx.strokeStyle='#91f2ce';ctx.globalAlpha=.6+.25*Math.sin(performance.now()/250);ctx.strokeRect(exit.x+7,exit.y+7,36,36);ctx.globalAlpha=1;text('EXIT',exit.x+11,666,8,'#91f2ce');mission.hunters.forEach(h=>{ctx.save();ctx.translate(h.x+22,h.y+22);ctx.fillStyle='#ff695d';ctx.shadowColor='#ff695d';ctx.shadowBlur=18;ctx.beginPath();ctx.arc(0,0,15,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='#170d17';ctx.fillRect(-8,-4,5,8);ctx.fillRect(3,-4,5,8);ctx.strokeStyle='#ff695d';ctx.globalAlpha=.19;ctx.beginPath();ctx.arc(0,0,150*mission.radius,0,Math.PI*2);ctx.stroke();ctx.restore();});ctx.fillStyle='#91f2ce';ctx.shadowColor='#91f2ce';ctx.shadowBlur=18;ctx.fillRect(mission.player.x+14,mission.player.y+14,16,16);ctx.shadowBlur=0;if(mission.hidden){ctx.strokeStyle='#91f2ce';ctx.beginPath();ctx.arc(mission.player.x+22,mission.player.y+22,20,0,Math.PI*2);ctx.stroke();}if(mission.flare){ctx.strokeStyle='#efc66d';ctx.beginPath();ctx.arc(mission.flare.x+22,mission.flare.y+22,18+Math.sin(performance.now()/80)*4,0,Math.PI*2);ctx.stroke();}if(mission.scare>0){rect(22,22,gW,656,`rgba(255,30,35,${Math.min(.48,mission.scare*.35)})`);ctx.fillStyle='#09040a';ctx.beginPath();ctx.arc(530,330,105,0,Math.PI*2);ctx.fill();ctx.fillStyle='#ff695d';ctx.shadowColor='#ff695d';ctx.shadowBlur=25;ctx.fillRect(480,300,28,18);ctx.fillRect(552,300,28,18);ctx.fillRect(500,370,60,10);ctx.shadowBlur=0;text('MOVE',530,455,24,'#fff1e8','Barlow Condensed','center');}
  drawMonitor(1082,22,336,656);if(paused){rect(22,22,W-44,H-44,'rgba(0,0,0,.7)');text('SIGNAL PAUSED',W/2,350,48,'#91f2ce','Barlow Condensed','center');text('Press ESC or PAUSE to return.',W/2,386,12,'#b7c8c2','IBM Plex Mono','center');}}
function drawMonitor(x,y,w,h){panel(x,y,w,h,'LIVE PHYSIOLOGY');const fb=state.feedback||{};text(fb.bpm?Math.round(fb.bpm):'--',x+18,y+94,78,fb.valid?'#91f2ce':'#70858a','Barlow Condensed');text('BPM',x+145,y+86,16,'#91aaa7');text(fb.baseline?`Δ ${fb.delta>=0?'+':''}${Math.round(fb.delta)} BPM`:'BASELINE ...',x+145,y+109,9,'#efc66d');text(fb.valid?'LINKED':'NO RELIABLE SIGNAL',x+18,y+126,9,fb.valid?'#91f2ce':'#efc66d');const meter=Math.min(1,Math.max(0,(fb.intensity||0)));rect(x+18,y+143,w-36,7,'#1c292e');rect(x+18,y+143,(w-36)*meter,7,'#ff695d');text('FEAR RESPONSE',x+18,y+168,8,'#7e9791');text(`FIELD ${mission.radius?.toFixed(2)||'1.00'}x`,x+w-18,y+168,9,'#efc66d','IBM Plex Mono','right');chart(x+18,y+184,w-36,145,graphForPulse(rppgHistory),'#91f2ce','rPPG / LIVE',40,140);chart(x+18,y+345,w-36,145,graphForPulse(bcgHistory),'#efc66d','rBCG / EXPERIMENTAL',40,140);text(`INTEGRITY  ${mission.health}/3`,x+18,y+525,10,mission.health===1?'#ff695d':'#dceae6');text(`FLARES  ${mission.flares}`,x+w-18,y+525,10,'#efc66d','IBM Plex Mono','right');text('A rise expands the watcher field.',x+18,y+560,9,'#8aa09b');text('A scare is not a diagnosis.',x+18,y+578,9,'#8aa09b');}
function fmt(v){return`${String(Math.floor(v/60)).padStart(2,'0')}:${String(Math.floor(v%60)).padStart(2,'0')}`}
function draw(){if(phase==='game')drawGame();else if(phase==='scan')drawScan();else{background();text('TRACE / NIGHT SIGNAL',42,65,13,'#91f2ce');text('A camera sees the pulse in your face.',42,155,50,'#e4eeeb','Barlow Condensed');text('Then the pulse becomes part of the horror.',42,210,50,'#91aaa7','Barlow Condensed');text('Start with a live camera to see three rPPG methods and experimental camera BCG in one monitor.',42,270,13,'#8d9eaa');panel(42,345,570,260,'#0b151e');text('THE FLOW',67,380,10,'#91f2ce');[['01','CAMERA ACQUISITION','colour pulse + facial motion'],['02','SIGNAL CHECK','live BPM and graphs'],['03','NIGHT RUN','your measured response changes the danger']].forEach((a,i)=>{const yy=430+i*52;text(a[0],67,yy,11,'#efc66d');text(a[1],115,yy,11,'#dceae6');text(a[2],115,yy+17,9,'#7e9692');});text('Use simulation if a camera is unavailable.',42,658,10,'#687f7d');}}

function loop(now){const dt=Math.min(.05,(now-last)/1000);last=now;if(phase==='game')update(dt);draw();requestAnimationFrame(loop);}requestAnimationFrame(loop);
if(new URLSearchParams(location.search).has('demo'))begin('demo');
