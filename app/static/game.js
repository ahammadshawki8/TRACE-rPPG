const $ = s => document.querySelector(s);
const canvas = $('#experience');
const DPR = Math.min(window.devicePixelRatio || 1, 2);
canvas.width = 1440 * DPR;
canvas.height = 820 * DPR;
const ctx = canvas.getContext('2d');
ctx.scale(DPR, DPR);
const W = 1440, H = 820;
const shadowCanvas = document.createElement('canvas');
shadowCanvas.width = 1040;shadowCanvas.height = 700;
const shadowCtx = shadowCanvas.getContext('2d');
const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
const feed = $('#camera-frame');
const pending = [];
let state = {feedback:{intensity:0, valid:false}};
let phase = 'welcome';
let source = null;
let paused = false;
let soundOn = false;
let audio;
let soundscape;
let mission;
let last = performance.now();
const keys = new Set();
const pressed = new Set();
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
const hunterHome = [{x:400,y:95},{x:900,y:585}];
const relaySites = [
  {x:95,y:575,name:'MORGUE RELAY'},
  {x:390,y:85,name:'ARCHIVE RELAY'},
  {x:910,y:365,name:'WARD RELAY'}
];
const patrolPoints = [
  {x:120,y:265},{x:390,y:270},{x:650,y:165},{x:900,y:270},
  {x:900,y:560},{x:650,y:535},{x:390,y:575},{x:180,y:390}
];
const MAP = {x:22,y:70,w:1040,h:700};
const levels = [
  {roman:'I',name:'THE LISTENING WARD',brief:'One stalker. Restore the morgue relay.'},
  {roman:'II',name:'THE BLACKOUT',brief:'A second signal wakes. Restore the archive relay.'},
  {roman:'III',name:'THE CHOIR',brief:'The ward is hunting. Restore the final relay and extract.'}
];

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
  if(kind==='camera'){send({cmd:'start',source:'webcam',options:{game_window:15}});feed.src='/video.mjpg?session='+Date.now();$('#canvas-note').textContent='LOCAL CAMERA / FRAMES NEVER LEAVE THIS COMPUTER';}
  else{send({cmd:'demo'});$('#canvas-note').textContent='SYNTHETIC SIGNAL / REPEATABLE DEMO';}
  $('#flow-step').textContent='SIGNAL CHECK';$('#headline').innerHTML='Watch the signal.<br><em>Before it watches you.</em>';$('#subhead').textContent='Keep your face still while TRACE separates colour pulse from tiny facial motion. Both channels will stay visible during the mission.';
  draw();
}
function newMission(){
  const now=performance.now();
  return {
    mode:'briefing',start:now,t:0,player:{x:75,y:615,facing:-Math.PI/2,moving:false},
    hunters:hunterHome.map((p,i)=>({x:p.x,y:p.y,home:{...p},mode:'patrol',patrol:(i*4+1)%patrolPoints.length,lastSeen:null,alert:0,revealed:0,stun:0})),
    relays:relaySites.map(p=>({...p,online:false,progress:0})),flares:2,health:3,
    hidden:false,flashlight:true,battery:100,beatClock:.2,rings:[],stage:0,level:1,interlude:null,
    radius:1,scare:0,scareType:'face',blackout:0,flicker:0,apparition:null,
    nextEvent:11,detections:0,invulnerable:0,events:[],frames:[],ended:false,
    message:'Restore three pulse relays. The exit has no power.'
  };
}
function enterGame(){
  if(!state.feedback?.baseline)return;
  phase='game';mission=newMission();paused=false;document.body.classList.add('game-active');soundOn=$('#sound-toggle').checked;if(soundOn)ensureAudio();
  $('#flow-step').textContent='NIGHT RUN';$('#camera-start').hidden=true;$('#simulation-start').hidden=true;$('#enter-game').hidden=true;$('#game-controls').hidden=false;$('#pause').disabled=false;
  $('#headline').innerHTML='The facility knows<br><em>the rhythm of your blood.</em>';
  $('#subhead').textContent='Restore the three pulse relays. Every measured heartbeat reveals the dark and tells the stalker where to search.';
  $('#control-message').textContent='Heartbeat waves reveal danger. Sprinting and flashlight use make you easier to find.';
  canvas.focus();beep(180,.16);draw();
}

$('#camera-start').onclick=()=>{if(phase==='scan')enterGame();else begin('camera');};
$('#simulation-start').onclick=()=>begin('demo');
const enter=document.createElement('button');enter.id='enter-game';enter.className='primary';enter.textContent='ENTER NIGHT';enter.hidden=true;enter.onclick=enterGame;$('#source-controls').append(enter);
$('#return-scan').onclick=()=>{send({cmd:'stop'});phase='welcome';mission=null;paused=false;keys.clear();pressed.clear();document.body.classList.remove('game-active');$('#camera-start').hidden=false;$('#simulation-start').hidden=false;$('#camera-start').disabled=false;$('#simulation-start').disabled=false;$('#camera-start').textContent='OPEN CAMERA';$('#game-controls').hidden=true;$('#headline').innerHTML='Something is listening<br><em>to your heartbeat.</em>';$('#subhead').textContent='First, let TRACE find your pulse. Then enter the facility and see what happens when the dark learns your rhythm.';draw();};
$('#pause').onclick=()=>{if(!mission||mission.ended)return;const now=performance.now();paused=!paused;if(paused)mission.pauseAt=now;else if(mission.pauseAt)mission.start+=now-mission.pauseAt;keys.clear();pressed.clear();$('#pause').textContent=paused?'RESUME':'PAUSE';draw();};
$('#settings').onclick=()=>{if(mission&&!mission.ended&&!paused){mission.settingsPause=true;$('#pause').click();}$('#settings-dialog').showModal();};
$('#close-settings').onclick=()=>$('#settings-dialog').close();
$('#settings-dialog').addEventListener('close',()=>{if(mission?.settingsPause){mission.settingsPause=false;$('#pause').click();}});
$('#sound-toggle').onchange=e=>{soundOn=e.target.checked;if(soundOn){ensureAudio();beep(240,.06);}else if(soundscape)soundscape.master.gain.setTargetAtTime(0,audio.currentTime,.08);};
$('#sound-volume').oninput=()=>{if(soundscape&&soundOn)soundscape.master.gain.setTargetAtTime(Number($('#sound-volume').value),audio.currentTime,.08);};
$('#feedback-mode').onchange=()=>{if(mission)mission.events.push({t:mission.t,text:'Feedback rule changed during run.'});};
window.addEventListener('keydown',e=>{const k=e.key.toLowerCase();if(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright',' ','e','f','shift','enter','escape'].includes(k))e.preventDefault();if(k==='escape'&&mission)$('#pause').click();if(!e.repeat)pressed.add(k);keys.add(k);});
window.addEventListener('keyup',e=>keys.delete(e.key.toLowerCase()));
function canvasPoint(e){const r=canvas.getBoundingClientRect();return{x:(e.clientX-r.left)/r.width*W,y:(e.clientY-r.top)/r.height*H};}
function nightButtonReady(){return phase==='scan'&&state.feedback?.baseline&&state.feedback?.calibration>=1;}
canvas.addEventListener('click',e=>{const p=canvasPoint(e);if(nightButtonReady()&&p.x>=1065&&p.x<=1398&&p.y>=718&&p.y<=763){enterGame();return;}if(phase==='game'&&mission?.mode==='briefing'&&p.x>=520&&p.x<=920&&p.y>=590&&p.y<=650)startNight();else if(phase==='game'&&mission?.ended&&p.x>=425&&p.x<=705&&p.y>=590&&p.y<=650)restartNight();else if(phase==='game'&&mission?.ended&&p.x>=735&&p.x<=1015&&p.y>=590&&p.y<=650)downloadSession();});
canvas.addEventListener('mousemove',e=>{const p=canvasPoint(e);const hot=nightButtonReady()&&p.x>=1065&&p.x<=1398&&p.y>=718&&p.y<=763||phase==='game'&&mission?.mode==='briefing'&&p.x>=520&&p.x<=920&&p.y>=590&&p.y<=650||phase==='game'&&mission?.ended&&p.y>=590&&p.y<=650&&p.x>=425&&p.x<=1015;canvas.style.cursor=hot?'pointer':'default';});

function ensureAudio(){
  if(audio){audio.resume();if(soundscape)soundscape.master.gain.setTargetAtTime(Number($('#sound-volume').value),audio.currentTime,.08);return;}
  audio=new(window.AudioContext||window.webkitAudioContext)();const master=audio.createGain(),limiter=audio.createDynamicsCompressor(),droneGain=audio.createGain(),droneA=audio.createOscillator(),droneB=audio.createOscillator();
  limiter.threshold.value=-18;limiter.knee.value=18;limiter.ratio.value=7;limiter.attack.value=.003;limiter.release.value=.22;master.gain.value=Number($('#sound-volume').value);master.connect(limiter);limiter.connect(audio.destination);
  droneA.type='triangle';droneB.type='sine';droneA.frequency.value=38;droneB.frequency.value=57.2;droneB.detune.value=-9;droneGain.gain.value=.012;droneA.connect(droneGain);droneB.connect(droneGain);droneGain.connect(master);droneA.start();droneB.start();soundscape={master,droneGain,droneA,droneB,lastBreathCue:-1};audio.resume();
}
function tone(freq,dur=.1,gain=.03,type='sine',delay=0,pan=0,endFreq=null){
  if(!soundOn)return;ensureAudio();const now=audio.currentTime+delay,o=audio.createOscillator(),g=audio.createGain(),p=audio.createStereoPanner?audio.createStereoPanner():null;o.type=type;o.frequency.setValueAtTime(Math.max(20,freq),now);if(endFreq)o.frequency.exponentialRampToValueAtTime(Math.max(20,endFreq),now+dur);g.gain.setValueAtTime(.0001,now);g.gain.exponentialRampToValueAtTime(gain,now+.012);g.gain.exponentialRampToValueAtTime(.0001,now+dur);o.connect(g);if(p){p.pan.value=Math.max(-1,Math.min(1,pan));g.connect(p);p.connect(soundscape.master);}else g.connect(soundscape.master);o.start(now);o.stop(now+dur+.03);
}
function beep(freq,dur=.1){tone(freq,dur,.025,'triangle',0,0,freq*.72);}
function noiseBurst(dur=.35,gain=.045,centre=900,pan=0){
  if(!soundOn)return;ensureAudio();const n=Math.ceil(audio.sampleRate*dur),buffer=audio.createBuffer(1,n,audio.sampleRate),data=buffer.getChannelData(0);for(let i=0;i<n;i++)data[i]=(Math.random()*2-1)*(1-i/n);const src=audio.createBufferSource(),filter=audio.createBiquadFilter(),g=audio.createGain(),p=audio.createStereoPanner?audio.createStereoPanner():null;src.buffer=buffer;filter.type='bandpass';filter.frequency.value=centre;filter.Q.value=.7;g.gain.setValueAtTime(gain,audio.currentTime);g.gain.exponentialRampToValueAtTime(.0001,audio.currentTime+dur);src.connect(filter);filter.connect(g);if(p){p.pan.value=pan;g.connect(p);p.connect(soundscape.master);}else g.connect(soundscape.master);src.start();
}
function heartbeatSound(bpm,intensity){const root=38+Math.min(18,bpm*.12)+intensity*8;tone(root,.105,.045,'sine',0,0,root*.58);tone(root*.82,.115,.03,'triangle',.13,0,root*.48);}
function scareAudio(type){const hard=type==='hit';noiseBurst(hard?.62:.42,hard?.075:.055,hard?1250:780,Math.random()*.8-.4);tone(hard?74:92,hard?.75:.48,hard?.065:.045,'sawtooth',0,0,31);tone(311,.36,.025,'square',.025,-.45,143);tone(337,.39,.025,'square',.035,.45,151);}
function updateSoundscape(intensity){
  if(!soundscape||!audio)return;const on=soundOn?1:0,interlude=mission?.interlude&&mission.interlude.delay<=0,stage=mission?.stage||0,nearest=mission?Math.min(...mission.hunters.map(h=>distance(h,mission.player))):999,proximity=Math.max(0,1-nearest/310),now=audio.currentTime;
  soundscape.master.gain.setTargetAtTime(on*Number($('#sound-volume').value),now,.12);soundscape.droneGain.gain.setTargetAtTime(on*(interlude?.004:.009+.014*intensity+.018*proximity),now,.35);soundscape.droneA.frequency.setTargetAtTime(interlude?32:37+stage*2.5+intensity*7,now,.5);soundscape.droneB.frequency.setTargetAtTime(interlude?48:55+stage*3+proximity*9,now,.5);
}
function collide(x,y,r=12){return walls.some(w=>x+r>w.x&&x-r<w.x+w.w&&y+r>w.y&&y-r<w.y+w.h)}
function blocked(a,b){const n=Math.ceil(Math.hypot(a.x-b.x,a.y-b.y)/8);for(let i=1;i<n;i++){const x=a.x+(b.x-a.x)*i/n,y=a.y+(b.y-a.y)*i/n;if(walls.some(w=>x>w.x&&x<w.x+w.w&&y>w.y&&y<w.y+w.h))return true;}return false;}
function distance(a,b){return Math.hypot(a.x-b.x,a.y-b.y)}
function nearestLocker(){return hidingSpots.map(s=>({...s,cx:s.x+s.w/2,cy:s.y+s.h/2})).find(s=>Math.hypot(s.cx-mission.player.x,s.cy-mission.player.y)<58)}
function nearbyRelay(){const relay=mission.relays[mission.stage];return relay&&!relay.online&&distance(relay,mission.player)<48?relay:null}
function startNight(){if(!mission||mission.mode!=='briefing')return;mission.mode='play';mission.start=performance.now();mission.events.push({t:0,text:'Entered Saint Orison Ward.'});mission.message='Restore a relay. Hold E at an amber terminal.';beep(115,.25);}
function restartNight(){mission=newMission();paused=false;$('#pause').disabled=false;$('#pause').textContent='PAUSE';canvas.focus();}
function movePlayer(dx,dy,dt,speed){const p=mission.player,nx=p.x+dx*speed*dt,ny=p.y+dy*speed*dt;if(!collide(nx,p.y))p.x=Math.max(34,Math.min(1006,nx));if(!collide(p.x,ny))p.y=Math.max(34,Math.min(666,ny));p.facing=Math.atan2(dy,dx);}
function navPath(from,target){
  const step=32,cols=31,rows=21,toCell=p=>({c:Math.max(0,Math.min(cols-1,Math.round((p.x-32)/step))),r:Math.max(0,Math.min(rows-1,Math.round((p.y-32)/step)))}),point=(c,r)=>({x:32+c*step,y:32+r*step});
  const start=toCell(from),goal=toCell(target),startId=start.r*cols+start.c,goalId=goal.r*cols+goal.c,prev=new Int32Array(cols*rows).fill(-1),queue=new Int32Array(cols*rows);let head=0,tail=0,best=startId,bestD=Infinity;queue[tail++]=startId;prev[startId]=startId;
  while(head<tail){const id=queue[head++],c=id%cols,r=Math.floor(id/cols),p=point(c,r),d=(c-goal.c)**2+(r-goal.r)**2;if(d<bestD){bestD=d;best=id;}if(id===goalId)break;for(const [dc,dr] of [[1,0],[-1,0],[0,1],[0,-1]]){const nc=c+dc,nr=r+dr,nid=nr*cols+nc;if(nc<0||nr<0||nc>=cols||nr>=rows||prev[nid]>=0)continue;const np=point(nc,nr);if(collide(np.x,np.y,14)||blocked(p,np))continue;prev[nid]=id;queue[tail++]=nid;}}
  const end=prev[goalId]>=0?goalId:best,path=[];let id=end;while(id!==startId&&id>=0){path.push(point(id%cols,Math.floor(id/cols)));id=prev[id];}path.reverse();path.push({x:target.x,y:target.y});return path;
}
function moveHunter(h,target,speed,dt){
  if(!h.path||mission.t>(h.pathAt||0)||!h.pathTarget||distance(h.pathTarget,target)>46){h.path=navPath(h,target);h.pathTarget={x:target.x,y:target.y};h.pathAt=mission.t+.35;}
  while(h.path.length>1&&distance(h,h.path[0])<14)h.path.shift();const waypoint=h.path[0]||target,q=Math.max(1,distance(h,waypoint)),dx=(waypoint.x-h.x)/q,dy=(waypoint.y-h.y)/q,nx=h.x+dx*speed*dt,ny=h.y+dy*speed*dt;
  if(!collide(nx,h.y,14))h.x=nx;if(!collide(h.x,ny,14))h.y=ny;
}
function interact(){
  if(mission.mode==='briefing'){startNight();return;}
  if(mission.ended)return;
  if(mission.hidden){mission.hidden=false;mission.message='You leave the locker. Your pulse is audible again.';beep(170,.06);return;}
  const locker=nearestLocker();
  if(locker&&!nearbyRelay()){mission.hidden=true;mission.player.x=locker.cx;mission.player.y=locker.cy;mission.message='Hidden. Press E to leave. A racing pulse can still betray you.';mission.events.push({t:mission.t,text:'Entered a hiding place.'});beep(95,.08);}
}
function flare(){if(!mission||mission.mode!=='play'||mission.ended||mission.hidden||mission.flares<=0)return;mission.flares--;mission.flare={x:mission.player.x+Math.cos(mission.player.facing)*46,y:mission.player.y+Math.sin(mission.player.facing)*46,end:performance.now()+5200};mission.rings.push({x:mission.flare.x,y:mission.flare.y,r:8,max:245,speed:310,flare:true});beep(520,.12);mission.events.push({t:mission.t,text:'Signal flare deployed. The stalker changed course.'});mission.message='The flare attracts and briefly stuns anything that reaches it.';}
function toggleFlashlight(){if(!mission||mission.mode!=='play'||mission.ended)return;if(mission.battery<=0){mission.message='Flashlight cell empty. Keep it off to recharge.';return;}mission.flashlight=!mission.flashlight;beep(mission.flashlight?260:110,.04);}
function triggerScare(type='face'){
  if(!mission||mission.ended)return;
  if($('#horror-intensity').value==='quiet'&&type!=='hit'){mission.flicker=1.2;mission.blackout=.25;mission.message='The ward shudders, then goes quiet.';return;}
  mission.scare=type==='hit'?1.35:.9;mission.scareType=type;mission.blackout=Math.max(mission.blackout,type==='hit'?.55:.2);
  mission.events.push({t:mission.t,text:`Director event: ${type}.`});scareAudio(type);
  if(source==='demo')send({cmd:'scenario',value:'scare'});
  setTimeout(()=>{if(source==='demo')send({cmd:'scenario',value:'cycle'});},3200);
}
function directorEvent(){
  const setting=$('#horror-intensity').value,pressure=mission.stage+(state.feedback?.intensity||0);
  if(setting==='quiet'){mission.flicker=.5;mission.message='The current stutters through the empty ward.';}
  else{
    const roll=Math.random();
    if(roll<.34){mission.flicker=1.5;mission.message='Something crossed the light behind you.';tone(38,.55,.025,'sawtooth',0,Math.random()>.5?-.7:.7,27);}
    else if(roll<.7){const pan=Math.random()>.5?-.8:.8;mission.apparition={x:mission.player.x-Math.cos(mission.player.facing)*115,y:mission.player.y-Math.sin(mission.player.facing)*115,end:performance.now()+1450};mission.message='Do not turn around.';noiseBurst(.7,.018,1700,pan);tone(74,.65,.02,'triangle',0,pan,49);}
    else triggerScare(pressure>2.4?'hands':'face');
  }
  const base=Math.max(6,(setting==='nightmare'?8:14)-mission.stage*1.5);mission.nextEvent=mission.t+base+Math.random()*(setting==='nightmare'?5:9);
}
function emitHeartbeat(intensity,bpm){
  const p=mission.player,max=145+155*intensity;
  mission.rings.push({x:p.x,y:p.y,r:8,max,speed:255,flare:false});mission.beatFlash=.16;
  heartbeatSound(bpm,intensity);
  mission.hunters.forEach((h,i)=>{
    if(i===1&&mission.stage<1)return;
    const heard=distance(h,p)<max*(blocked(h,p)?.65:1);
    if(heard&&(!mission.hidden||distance(h,p)<70+45*intensity)){
      if(h.mode==='patrol')h.mode='investigate';h.lastSeen={x:p.x,y:p.y};h.alert=Math.max(h.alert,2.8+2*intensity);
    }
  });
}
function activateRelay(relay){
  relay.online=true;relay.progress=1;mission.stage++;mission.blackout=.75;mission.flicker=2;
  mission.events.push({t:mission.t,text:`${relay.name} restored (${mission.stage}/3).`});
  mission.message=mission.stage===3?'All relays online. Reach the green extraction door.':`${relay.name} online. The ward has noticed.`;
  mission.rings.push({x:relay.x,y:relay.y,r:8,max:360,speed:380,flare:true});beep(720,.16);
  if(mission.stage<3){triggerScare(mission.stage===1?'face':'hands');mission.interlude={delay:1,total:10,remaining:10,nextLevel:mission.stage+1,startBpm:state.feedback?.bpm||null,segment:''};mission.hunters.forEach(h=>h.stun=12);}
  else{triggerScare('hands');mission.nextEvent=mission.t+5;mission.hunters.forEach(h=>{h.mode='hunt';h.lastSeen={x:mission.player.x,y:mission.player.y};h.alert=30;});}
}
function updateInterlude(dt){
  const q=mission.interlude;if(!q)return false;if(q.delay>0){q.delay-=dt;return true;}q.remaining=Math.max(0,q.remaining-dt);const phase=(q.total-q.remaining)%10,segment=phase<4?'INHALE':'EXHALE';q.breathPhase=phase;q.segment=segment;
  if(q.audioSegment!==segment){q.audioSegment=segment;tone(segment==='INHALE'?196:147,segment==='INHALE'?3.5:5.2,.014,'sine',0,0,segment==='INHALE'?247:98);}
  if(q.remaining<=0){mission.level=q.nextLevel;mission.interlude=null;mission.message=levels[mission.level-1].brief;mission.nextEvent=mission.t+8;mission.events.push({t:mission.t,text:`Level ${mission.level} entered after paced recovery.`});mission.hunters.forEach(h=>{h.stun=0;h.mode='patrol';h.path=null;});tone(294,.5,.025,'triangle');return false;}return true;
}
function damagePlayer(h){
  if(mission.invulnerable>0)return;mission.health--;mission.invulnerable=2.8;mission.detections++;
  mission.events.push({t:mission.t,text:`The stalker reached you. Integrity ${mission.health}/3.`});triggerScare('hit');
  h.stun=2;h.x=h.home.x;h.y=h.home.y;h.mode='patrol';
  if(mission.health<=0)finish(false);
}
function updateHunter(h,index,dt,intensity){
  if(index===1&&mission.stage<1)return;
  h.revealed=Math.max(0,h.revealed-dt);h.stun=Math.max(0,h.stun-dt);if(h.stun>0)return;
  const p=mission.player,dist=distance(h,p),lightRange=mission.flashlight?260:105;
  const sees=!mission.hidden&&!blocked(h,p)&&dist<lightRange*mission.radius;
  if(sees){if(h.mode!=='hunt')mission.detections++;h.mode='hunt';h.lastSeen={x:p.x,y:p.y};h.alert=4.5;h.revealed=.15;}
  else h.alert=Math.max(0,h.alert-dt);
  let target,speed;
  if(mission.flare&&performance.now()<mission.flare.end){target=mission.flare;speed=82;if(distance(h,target)<35){h.stun=1.6;h.revealed=1.6;}}
  else if((h.mode==='hunt'||h.mode==='investigate')&&h.lastSeen){target=h.lastSeen;const difficulty=$('#horror-intensity').value==='nightmare'?1.16:1;speed=(h.mode==='hunt'?72+mission.stage*7+intensity*24:52+mission.stage*5)*difficulty;if(distance(h,target)<22||h.alert<=0){h.mode='patrol';h.lastSeen=null;}}
  else{h.mode='patrol';target=patrolPoints[h.patrol];speed=34+mission.stage*4;if(distance(h,target)<28)h.patrol=(h.patrol+1+Math.floor(Math.random()*3))%patrolPoints.length;}
  if(target)moveHunter(h,target,speed,dt);
  if(dist<25)damagePlayer(h);
}
function recordFrame(fb,intensity,valid,recovery=false){if(!mission.nextFrame||mission.t>=mission.nextFrame){mission.frames.push({t:mission.t,bpm:fb.bpm||null,baseline:fb.baseline||null,intensity,radius:mission.radius,valid,level:mission.level,stage:mission.stage,recovery,hidden:mission.hidden,flashlight:mission.flashlight,health:mission.health,player:{x:Math.round(mission.player.x),y:Math.round(mission.player.y)},hunters:mission.hunters.map(h=>({x:Math.round(h.x),y:Math.round(h.y),mode:h.mode}))});mission.nextFrame=mission.t+.25;if(mission.frames.length>2400)mission.frames.shift();}}
function update(dt){
  if(phase!=='game'||paused||!mission)return;
  if(mission.mode==='briefing'){if(pressed.has('e')||pressed.has('enter'))startNight();pressed.clear();return;}
  if(mission.ended){pressed.clear();return;}
  mission.t=(performance.now()-mission.start)/1000;
  const fb=state.feedback||{},valid=!!fb.valid,intensity=valid?fb.intensity||0:0,mode=$('#feedback-mode').value;
  mission.radius=mode==='fixed'?1:mode==='balance'?Math.max(.72,1-.28*intensity):1+.85*intensity;
  updateSoundscape(intensity);
  if(mission.interlude){mission.scare=Math.max(0,mission.scare-dt);mission.blackout=Math.max(0,mission.blackout-dt);mission.flicker=Math.max(0,mission.flicker-dt);const recovering=updateInterlude(dt);recordFrame(fb,intensity,valid,recovering);pressed.clear();return;}
  if(pressed.has(' '))flare();if(pressed.has('f'))toggleFlashlight();if(pressed.has('e'))interact();
  const u=keys.has('w')||keys.has('arrowup'),d=keys.has('s')||keys.has('arrowdown'),l=keys.has('a')||keys.has('arrowleft'),r=keys.has('d')||keys.has('arrowright');
  let dx=(r?1:0)-(l?1:0),dy=(d?1:0)-(u?1:0);const sprint=keys.has('shift')&&!mission.hidden,relay=nearbyRelay();
  mission.player.moving=!!(dx||dy)&&!mission.hidden;
  if(mission.player.moving){const q=Math.hypot(dx,dy);movePlayer(dx/q,dy/q,dt,(sprint?174:112)*(relay&&keys.has('e')?.42:1));}
  if(sprint&&mission.player.moving)mission.hunters.forEach((h,i)=>{if((i===0||mission.stage>=1)&&distance(h,mission.player)<245*mission.radius){h.mode='investigate';h.lastSeen={x:mission.player.x,y:mission.player.y};h.alert=2.2;}});
  if(relay&&keys.has('e')&&!mission.hidden){relay.progress=Math.min(1,relay.progress+dt/(1.65+mission.stage*.28));mission.message=`LINKING ${relay.name}  ${Math.round(relay.progress*100)}%`;if(relay.progress>=1)activateRelay(relay);}else mission.relays.filter(q=>!q.online).forEach(q=>q.progress=Math.max(0,q.progress-dt*.08));
  mission.battery=Math.max(0,Math.min(100,mission.battery+(mission.flashlight?-.75:1.5)*dt));if(mission.battery<=0)mission.flashlight=false;
  mission.beatClock-=dt;const bpm=valid&&fb.bpm?fb.bpm:fb.baseline||72;if(mission.beatClock<=0){mission.beatClock+=60/Math.max(45,Math.min(180,bpm));emitHeartbeat(intensity,bpm);}
  mission.rings.forEach(ring=>{ring.r+=ring.speed*dt;mission.hunters.forEach(h=>{if(Math.abs(distance(h,ring)-ring.r)<25)h.revealed=Math.max(h.revealed,.35);});});mission.rings=mission.rings.filter(ring=>ring.r<ring.max);
  mission.hunters.forEach((h,i)=>updateHunter(h,i,dt,intensity));
  mission.invulnerable=Math.max(0,mission.invulnerable-dt);mission.scare=Math.max(0,mission.scare-dt);mission.blackout=Math.max(0,mission.blackout-dt);mission.flicker=Math.max(0,mission.flicker-dt);mission.beatFlash=Math.max(0,(mission.beatFlash||0)-dt);
  if(mission.apparition&&performance.now()>mission.apparition.end)mission.apparition=null;if(mission.flare&&performance.now()>mission.flare.end)mission.flare=null;
  if(mission.t>mission.nextEvent)directorEvent();
  const exit={x:965,y:605};if(mission.stage===3&&distance(exit,mission.player)<36)finish(true);
  recordFrame(fb,intensity,valid);
  pressed.clear();
}
function finish(success){if(mission.ended)return;mission.ended=true;mission.success=success;mission.mode='end';mission.score=Math.max(0,Math.round(1200-mission.t*5+mission.health*240+mission.flares*90-mission.detections*35));$('#pause').disabled=true;$('#control-message').textContent=success?'Extraction complete. Run again or export the physiology timeline.':'The stalker found the signal. Run again or export the physiology timeline.';beep(success?640:45,success?.35:.8);}
function downloadSession(){if(!mission)return;const payload={experiment:'TRACE Night Signal',success:mission.success,score:mission.score,events:mission.events,frames:mission.frames,source,disclaimer:'Interactive research telemetry. Not a medical measurement or diagnosis.'};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));a.download='trace-night-signal.json';a.click();URL.revokeObjectURL(a.href);}

function text(s,x,y,size,color= '#dceae6',font='IBM Plex Mono',align='left'){ctx.fillStyle=color;ctx.font=`${size}px ${font}`;ctx.textAlign=align;ctx.fillText(s,x,y);ctx.textAlign='left';}
function rect(x,y,w,h,fill,stroke=null){ctx.fillStyle=fill;ctx.fillRect(x,y,w,h);if(stroke){ctx.strokeStyle=stroke;ctx.strokeRect(x+.5,y+.5,w-1,h-1);}}
function line(points,color,width=2){if(!points.length)return;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.stroke();}
function panel(x,y,w,h,title){rect(x,y,w,h,'#0b151e','#2a4240');text(title.startsWith('#')?'SESSION FLOW':title,x+15,y+22,10,'#91f2ce','IBM Plex Mono');}
function clippedLine(points,color,width,x,y,w,h){ctx.save();ctx.beginPath();ctx.rect(x,y,w,h);ctx.clip();line(points,color,width);ctx.restore();}
function chart(x,y,w,h,arr,color,label,min=40,max=140){rect(x,y,w,h,'#081018','#263e3d');text(label,x+10,y+18,9,'#91aaa7');const vals=arr.map(a=>typeof a==='number'?a:a.v).filter(Number.isFinite);if(vals.length<2)return;if(Math.max(...vals.map(Math.abs))<20){const mean=vals.reduce((a,b)=>a+b,0)/vals.length,centred=vals.map(v=>v-mean),sorted=centred.map(Math.abs).sort((a,b)=>a-b),scale=sorted[Math.floor(sorted.length*.95)]||1;clippedLine(centred.map((v,i)=>[x+10+i/(centred.length-1)*(w-20),y+h/2+8-Math.max(-1.15,Math.min(1.15,v/scale))*(h-40)*.38]),color,2,x+1,y+25,w-2,h-26);return;}const span=max-min;clippedLine(vals.map((v,i)=>[x+10+i/(vals.length-1)*(w-20),y+h-12-(Math.max(min,Math.min(max,v))-min)/span*(h-34)]),color,2,x+1,y+25,w-2,h-26);}
function waveChart(x,y,w,h,values,color,label){rect(x,y,w,h,'#081018','#263e3d');text(label,x+10,y+18,9,'#91aaa7');const vals=(values||[]).filter(Number.isFinite);if(vals.length<2){text('WAITING FOR A CLEAN WAVEFORM',x+w/2,y+h/2+5,8,'#52696a','IBM Plex Mono','center');return;}const mean=vals.reduce((a,b)=>a+b,0)/vals.length;const centred=vals.map(v=>v-mean);const sorted=centred.map(Math.abs).sort((a,b)=>a-b);const scale=sorted[Math.floor(sorted.length*.95)]||1;ctx.strokeStyle='#172b30';ctx.beginPath();ctx.moveTo(x+10,y+h/2+8);ctx.lineTo(x+w-10,y+h/2+8);ctx.stroke();clippedLine(centred.map((v,i)=>[x+10+i/(centred.length-1)*(w-20),y+h/2+8-Math.max(-1.15,Math.min(1.15,v/scale))*(h-40)*.38]),color,2,x+1,y+25,w-2,h-26);}
function methodChart(x,y,w,h){rect(x,y,w,h,'#081018','#263e3d');text('rPPG / THREE COLOUR EXTRACTIONS',x+10,y+18,9,'#91aaa7');const traces=state.method_traces||{};const rows=[['green','#efc66d'],['chrom','#ff8876'],['pos','#91f2ce']],lane=(h-34)/3;rows.forEach(([key,color],i)=>{const vals=(traces[key]||[]).filter(Number.isFinite),cy=y+30+lane*(i+.5);text(key.toUpperCase(),x+10,cy+3,8,color);ctx.strokeStyle='#15272c';ctx.beginPath();ctx.moveTo(x+62,cy);ctx.lineTo(x+w-10,cy);ctx.stroke();if(vals.length<2)return;const sorted=vals.map(Math.abs).sort((a,b)=>a-b),scale=sorted[Math.floor(sorted.length*.95)]||1;clippedLine(vals.map((v,j)=>[x+62+j/(vals.length-1)*(w-72),cy-Math.max(-1.2,Math.min(1.2,v/scale))*lane*.33]),color,1.7,x+61,cy-lane*.43,w-70,lane*.86);});}
function drawPreview(x,y,w,h){rect(x,y,w,h,'#111d25','#41534f');if(feed.complete&&feed.naturalWidth){ctx.drawImage(feed,x,y,w,h);}else{rect(x+80,y+45,w-160,h-100,'#182a32');ctx.fillStyle='#2e6861';ctx.beginPath();ctx.arc(x+w/2,y+h/2-15,58,0,Math.PI*2);ctx.fill();ctx.fillStyle='#081017';ctx.fillRect(x+w/2-34,y+h/2-27,20,8);ctx.fillRect(x+w/2+14,y+h/2-27,20,8);ctx.strokeStyle='#91f2ce';ctx.strokeRect(x+w/2-76,y+h/2-82,152,178);}text('LOCAL FACE TRACK',x+12,y+22,9,'#91f2ce');text('ROI / FOREHEAD + CHEEKS',x+12,y+h-13,8,'#8caaa2');}
function graphForPulse(vals){if(vals===bcgHistory&&state.bcg?.pulse)return state.bcg.pulse;if(vals===rppgHistory&&state.trace?.pulse)return state.trace.pulse;return vals.length?vals.map(a=>typeof a==='number'?a:a.v):[]}
function drawScan(){
  background();
  text('01 / SIGNAL ACQUISITION',42,40,11,'#91f2ce');
  text('TRACE is looking for a heartbeat in colour and motion.',42,68,21,'#dceae6','Barlow Condensed');
  drawPreview(42,94,500,345);
  panel(565,94,833,345,'LIVE READOUT / THREE OPTICAL METHODS + GUIDED rBCG');
  const fb=state.feedback||{},bpm=fb.bpm?Math.round(fb.bpm):'--';
  text(String(bpm),595,190,94,fb.valid?'#91f2ce':'#7f9293','Barlow Condensed');
  text('BPM',735,184,18,'#8ca6a2');
  text(fb.baseline?`BASELINE ${Math.round(fb.baseline)}  /  ${fb.delta>=0?'+':''}${Math.round(fb.delta)} Δ`:'CALIBRATING PERSONAL BASELINE',595,216,10,'#8ca6a2');
  text(fb.valid?'PULSE LINKED':'WAITING FOR STABLE SIGNAL',595,243,10,fb.valid?'#91f2ce':'#efc66d');
  const methods=state.methods||{};
  [['GREEN',methods.green],['CHROM',methods.chrom],['POS',methods.pos]].forEach((m,i)=>{
    const yy=276+i*42;
    text(m[0],595,yy,9,'#8ca6a2');
    const v=m[1]?.bpm;
    text(v?`${v.toFixed(1)} BPM`:'--',700,yy,12,v?'#dceae6':'#657a7c');
    rect(820,yy-10,500,5,'#17252b');
    if(v)rect(820,yy-10,Math.min(1,Math.max(0,(m[1].quality||0)))*500,5,i===0?'#efc66d':i===1?'#ff8876':'#91f2ce');
  });
  text(state.bcg?.usable?'rBCG CONFIRMED':'rBCG / VERIFYING',1135,204,9,state.bcg?.usable?'#91f2ce':'#efc66d');
  if(state.bcg?.bpm)text(`${state.bcg.bpm} BPM`,1135,228,16,'#efc66d','Barlow Condensed');
  text('Shown only when motion agrees with rPPG.',1135,250,8,'#718a88');
  methodChart(42,474,660,205);
  chart(728,474,670,205,graphForPulse(bcgHistory),'#efc66d','rBCG / GUIDED FACIAL MOTION',40,140);
  text(fb.calibration>=1?'BASELINE LOCKED / READY':'HOLD STILL / BASELINE '+Math.round((fb.calibration||0)*100)+'%',42,735,11,fb.calibration>=1?'#91f2ce':'#efc66d');
  text('GREEN  /  CHROM  /  POS   =   DIFFERENT CLASSICAL VIEWS OF THE SAME FACE',42,765,9,'#718a88');
  if(fb.baseline&&fb.calibration>=1){
    rect(1065,718,333,45,'#91f2ce','#91f2ce');
    text('ENTER NIGHT  >>',1231,746,13,'#092019','IBM Plex Mono','center');
  }
}
function background(){ctx.clearRect(0,0,W,H);rect(0,0,W,H,'#081119');ctx.strokeStyle='#10252a';ctx.lineWidth=1;for(let x=0;x<W;x+=32){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke();}for(let y=0;y<H;y+=32){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();}}
{
function drawGame(){background();const gW=1040;rect(22,22,gW,656,'#081219','#38544e');text('02 / NIGHT SIGNAL',42,49,11,'#91f2ce');text(`SURVIVE  ${fmt(mission.t)}    ECHOES ${mission.echoes.filter(e=>e.got).length}/3`,770,49,10,'#8aa39e','IBM Plex Mono','right');walls.forEach(w=>{rect(w.x+22,w.y+22,w.w,w.h,'#152a31','#294846');});hidingSpots.forEach(s=>{rect(s.x+22,s.y+22,s.w,s.h,mission.hidden&&mission.player.x>s.x&&mission.player.x<s.x+s.w&&mission.player.y>s.y&&mission.player.y<s.y+s.h?'#365f58':'#1a393c','#47756c');});mission.echoes.forEach(e=>{if(e.got)return;ctx.save();ctx.translate(e.x+22,e.y+22);ctx.rotate(Math.PI/4);ctx.fillStyle='#efc66d';ctx.shadowColor='#efc66d';ctx.shadowBlur=16;ctx.fillRect(-10,-10,20,20);ctx.restore();});const exit={x:965,y:605};ctx.strokeStyle='#91f2ce';ctx.globalAlpha=.6+.25*Math.sin(performance.now()/250);ctx.strokeRect(exit.x+7,exit.y+7,36,36);ctx.globalAlpha=1;text('EXIT',exit.x+11,666,8,'#91f2ce');mission.hunters.forEach(h=>{ctx.save();ctx.translate(h.x+22,h.y+22);ctx.fillStyle='#ff695d';ctx.shadowColor='#ff695d';ctx.shadowBlur=18;ctx.beginPath();ctx.arc(0,0,15,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='#170d17';ctx.fillRect(-8,-4,5,8);ctx.fillRect(3,-4,5,8);ctx.strokeStyle='#ff695d';ctx.globalAlpha=.19;ctx.beginPath();ctx.arc(0,0,150*mission.radius,0,Math.PI*2);ctx.stroke();ctx.restore();});ctx.fillStyle='#91f2ce';ctx.shadowColor='#91f2ce';ctx.shadowBlur=18;ctx.fillRect(mission.player.x+14,mission.player.y+14,16,16);ctx.shadowBlur=0;if(mission.hidden){ctx.strokeStyle='#91f2ce';ctx.beginPath();ctx.arc(mission.player.x+22,mission.player.y+22,20,0,Math.PI*2);ctx.stroke();}if(mission.flare){ctx.strokeStyle='#efc66d';ctx.beginPath();ctx.arc(mission.flare.x+22,mission.flare.y+22,18+Math.sin(performance.now()/80)*4,0,Math.PI*2);ctx.stroke();}if(mission.scare>0){rect(22,22,gW,656,`rgba(255,30,35,${Math.min(.48,mission.scare*.35)})`);ctx.fillStyle='#09040a';ctx.beginPath();ctx.arc(530,330,105,0,Math.PI*2);ctx.fill();ctx.fillStyle='#ff695d';ctx.shadowColor='#ff695d';ctx.shadowBlur=25;ctx.fillRect(480,300,28,18);ctx.fillRect(552,300,28,18);ctx.fillRect(500,370,60,10);ctx.shadowBlur=0;text('MOVE',530,455,24,'#fff1e8','Barlow Condensed','center');}
  drawMonitor(1082,22,336,656);if(paused){rect(22,22,W-44,H-44,'rgba(0,0,0,.7)');text('SIGNAL PAUSED',W/2,350,48,'#91f2ce','Barlow Condensed','center');text('Press ESC or PAUSE to return.',W/2,386,12,'#b7c8c2','IBM Plex Mono','center');}}
function drawMonitor(x,y,w,h){panel(x,y,w,h,'LIVE PHYSIOLOGY');const fb=state.feedback||{};text(fb.bpm?Math.round(fb.bpm):'--',x+18,y+94,78,fb.valid?'#91f2ce':'#70858a','Barlow Condensed');text('BPM',x+145,y+86,16,'#91aaa7');text(fb.baseline?`Δ ${fb.delta>=0?'+':''}${Math.round(fb.delta)} BPM`:'BASELINE ...',x+145,y+109,9,'#efc66d');text(fb.valid?'LINKED':'NO RELIABLE SIGNAL',x+18,y+126,9,fb.valid?'#91f2ce':'#efc66d');const meter=Math.min(1,Math.max(0,(fb.intensity||0)));rect(x+18,y+143,w-36,7,'#1c292e');rect(x+18,y+143,(w-36)*meter,7,'#ff695d');text('FEAR RESPONSE',x+18,y+168,8,'#7e9791');text(`FIELD ${mission.radius?.toFixed(2)||'1.00'}x`,x+w-18,y+168,9,'#efc66d','IBM Plex Mono','right');chart(x+18,y+184,w-36,145,graphForPulse(rppgHistory),'#91f2ce','rPPG / LIVE',40,140);chart(x+18,y+345,w-36,145,graphForPulse(bcgHistory),'#efc66d','rBCG / EXPERIMENTAL',40,140);text(`INTEGRITY  ${mission.health}/3`,x+18,y+525,10,mission.health===1?'#ff695d':'#dceae6');text(`FLARES  ${mission.flares}`,x+w-18,y+525,10,'#efc66d','IBM Plex Mono','right');text('A rise expands the watcher field.',x+18,y+560,9,'#8aa09b');text('A scare is not a diagnosis.',x+18,y+578,9,'#8aa09b');}
}
function drawRelay(r,index){
  const active=!r.online&&index===mission.stage,locked=index>mission.stage,glow=r.online?'#91f2ce':locked?'#41504f':'#efc66d';
  ctx.save();ctx.translate(r.x,r.y);ctx.shadowColor=glow;ctx.shadowBlur=active?13:r.online?22:0;ctx.strokeStyle=glow;ctx.lineWidth=2;ctx.strokeRect(-13,-13,26,26);ctx.fillStyle=r.online?'#173d35':locked?'#151e20':'#3a2d16';ctx.fillRect(-8,-8,16,16);ctx.shadowBlur=0;
  if(active&&r.progress>0){ctx.strokeStyle='#fff1bd';ctx.lineWidth=4;ctx.beginPath();ctx.arc(0,0,20,-Math.PI/2,-Math.PI/2+Math.PI*2*r.progress);ctx.stroke();}
  text(String(index+1).padStart(2,'0'),0,4,8,glow,'IBM Plex Mono','center');ctx.restore();
}
function drawHunter(h,index,afterDark=false){
  if(index===1&&mission.stage<1)return;if(afterDark&&h.revealed<=0)return;
  ctx.save();ctx.translate(h.x,h.y);const hunt=h.mode==='hunt',alpha=afterDark?Math.min(1,h.revealed*3):1;ctx.globalAlpha=alpha;
  ctx.shadowColor=hunt?'#ff4d52':'#ab3346';ctx.shadowBlur=hunt?24:12;ctx.fillStyle='#09070d';
  ctx.beginPath();ctx.moveTo(-12,25);ctx.lineTo(-18,-5);ctx.quadraticCurveTo(-15,-31,0,-35);ctx.quadraticCurveTo(15,-31,18,-5);ctx.lineTo(13,25);ctx.lineTo(5,15);ctx.lineTo(0,29);ctx.lineTo(-6,15);ctx.closePath();ctx.fill();
  ctx.shadowBlur=18;ctx.fillStyle='#ff5960';ctx.fillRect(-9,-15,6,3);ctx.fillRect(3,-15,6,3);ctx.shadowBlur=0;
  if(hunt){ctx.strokeStyle='#ff596066';ctx.lineWidth=1;ctx.beginPath();ctx.arc(0,0,36+Math.sin(performance.now()/90)*4,0,Math.PI*2);ctx.stroke();}
  ctx.restore();
}
function drawPlayer(){
  const p=mission.player;ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.facing);ctx.shadowColor=mission.invulnerable>0?'#ff695d':'#91f2ce';ctx.shadowBlur=16;ctx.fillStyle=mission.hidden?'#45645e':'#91f2ce';ctx.fillRect(-8,-8,16,16);ctx.fillStyle='#071018';ctx.fillRect(1,-5,5,10);if(mission.flashlight&&!mission.hidden){ctx.fillStyle='#efffd8';ctx.fillRect(8,-3,7,6);}ctx.restore();
  if(mission.hidden){ctx.strokeStyle='#91f2ce';ctx.setLineDash([3,4]);ctx.beginPath();ctx.arc(p.x,p.y,21,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);}
}
function drawDarkness(){
  const s=shadowCtx,p=mission.player;s.clearRect(0,0,MAP.w,MAP.h);let alpha=.86+Math.min(.1,mission.blackout*.16);if(mission.flicker>0&&Math.random()<.38)alpha=.96;s.fillStyle=`rgba(1,3,8,${alpha})`;s.fillRect(0,0,MAP.w,MAP.h);s.save();s.globalCompositeOperation='destination-out';
  const halo=s.createRadialGradient(p.x,p.y,16,p.x,p.y,78);halo.addColorStop(0,'rgba(0,0,0,1)');halo.addColorStop(.55,'rgba(0,0,0,.82)');halo.addColorStop(1,'rgba(0,0,0,0)');s.fillStyle=halo;s.beginPath();s.arc(p.x,p.y,80,0,Math.PI*2);s.fill();
  if(mission.flashlight&&mission.battery>0&&!mission.hidden){const a=p.facing,len=260,width=.42;s.globalAlpha=.82;s.fillStyle='#000';s.beginPath();s.moveTo(p.x,p.y);s.arc(p.x,p.y,len,a-width,a+width);s.closePath();s.fill();s.globalAlpha=1;}
  mission.rings.forEach(r=>{s.globalAlpha=Math.max(0,1-r.r/r.max);s.strokeStyle='#000';s.lineWidth=r.flare?64:34;s.beginPath();s.arc(r.x,r.y,r.r,0,Math.PI*2);s.stroke();});
  mission.relays.filter(r=>r.online).forEach(r=>{s.globalAlpha=.65;s.fillStyle='#000';s.beginPath();s.arc(r.x,r.y,48,0,Math.PI*2);s.fill();});s.restore();ctx.drawImage(shadowCanvas,0,0);
}
function drawFacility(){
  const shake=mission.scare>0?mission.scare*7:0;ctx.save();ctx.translate(MAP.x+(Math.random()-.5)*shake,MAP.y+(Math.random()-.5)*shake);ctx.beginPath();ctx.rect(0,0,MAP.w,MAP.h);ctx.clip();
  rect(0,0,MAP.w,MAP.h,'#071017','#38544e');ctx.strokeStyle='#0e2428';ctx.lineWidth=1;for(let x=20;x<MAP.w;x+=40){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,MAP.h);ctx.stroke();}for(let y=20;y<MAP.h;y+=40){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(MAP.w,y);ctx.stroke();}
  text('MORGUE',55,665,9,'#203b3d');text('ARCHIVE',325,48,9,'#203b3d');text('WARD C',830,340,9,'#203b3d');text('OBSERVATION',585,665,9,'#203b3d');
  hidingSpots.forEach((s,i)=>{rect(s.x,s.y,s.w,s.h,'#11282d','#355552');for(let q=12;q<s.w;q+=24)rect(s.x+q,s.y+9,2,s.h-18,'#29423f');text(`LOCKER ${i+1}`,s.x+8,s.y+s.h-8,7,'#54736d');});
  mission.relays.forEach(drawRelay);
  const exit={x:965,y:605},open=mission.stage===3;ctx.save();ctx.translate(exit.x,exit.y);ctx.shadowColor=open?'#91f2ce':'#ff695d';ctx.shadowBlur=open?24:8;ctx.strokeStyle=open?'#91f2ce':'#713c42';ctx.lineWidth=3;ctx.strokeRect(-22,-30,44,60);ctx.fillStyle=open?'#173d35':'#25151a';ctx.fillRect(-17,-25,34,50);ctx.shadowBlur=0;text(open?'EXTRACT':'NO POWER',0,46,7,open?'#91f2ce':'#8c555a','IBM Plex Mono','center');ctx.restore();
  walls.forEach(w=>{rect(w.x,w.y,w.w,w.h,'#172930','#33514f');if(w.w>w.h)rect(w.x,w.y+3,w.w,3,'#203a3e');else rect(w.x+3,w.y,3,w.h,'#203a3e');});
  if(mission.flare){ctx.fillStyle='#efc66d';ctx.shadowColor='#efc66d';ctx.shadowBlur=30;ctx.beginPath();ctx.arc(mission.flare.x,mission.flare.y,7+Math.sin(performance.now()/65)*2,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;}
  if(mission.apparition){const a=mission.apparition;ctx.globalAlpha=.55;ctx.fillStyle='#030207';ctx.beginPath();ctx.arc(a.x,a.y-17,12,0,Math.PI*2);ctx.fill();ctx.fillRect(a.x-8,a.y-5,16,38);ctx.fillStyle='#ff5960';ctx.fillRect(a.x-7,a.y-19,4,2);ctx.fillRect(a.x+3,a.y-19,4,2);ctx.globalAlpha=1;}
  mission.hunters.forEach((h,i)=>drawHunter(h,i));drawDarkness();mission.hunters.forEach((h,i)=>drawHunter(h,i,true));
  mission.rings.forEach(r=>{ctx.strokeStyle=r.flare?'#efc66d':'#91f2ce';ctx.globalAlpha=Math.max(.08,.72*(1-r.r/r.max));ctx.lineWidth=r.flare?3:2;ctx.beginPath();ctx.arc(r.x,r.y,r.r,0,Math.PI*2);ctx.stroke();ctx.globalAlpha=1;});drawPlayer();
  const relay=nearbyRelay(),locker=nearestLocker();let prompt='';if(mission.hidden)prompt='[E] LEAVE HIDING PLACE';else if(relay)prompt=`HOLD [E] LINK ${relay.name}`;else if(locker)prompt='[E] HIDE IN LOCKER';else if(mission.stage===3)prompt='REACH THE GREEN EXTRACTION DOOR';if(prompt){rect(250,650,540,32,'rgba(4,10,14,.86)','#3f5d58');text(prompt,520,671,9,'#e8f4ef','IBM Plex Mono','center');}
  ctx.restore();
}
function drawJumpscare(){
  if(mission.scare<=0)return;const a=Math.min(.92,.25+mission.scare*.58);rect(MAP.x,MAP.y,MAP.w,MAP.h,`rgba(90,0,8,${a})`);ctx.save();ctx.translate(MAP.x+MAP.w/2,MAP.y+MAP.h/2);const pulse=1+Math.sin(performance.now()/28)*.035;ctx.scale(pulse,pulse);ctx.fillStyle='#050307';ctx.shadowColor='#ff384b';ctx.shadowBlur=45;
  if(mission.scareType==='hands'){for(const side of [-1,1]){ctx.save();ctx.scale(side,1);ctx.fillRect(120,-190,75,350);for(let i=0;i<5;i++){ctx.save();ctx.translate(130+i*14,-175);ctx.rotate((i-2)*.09);ctx.fillRect(-5,-105,11,115);ctx.restore();}ctx.restore();}text('DON\'T LET IT COUNT THEM',0,205,30,'#fff1e8','Barlow Condensed','center');}
  else{ctx.beginPath();ctx.ellipse(0,-20,138,175,0,0,Math.PI*2);ctx.fill();ctx.shadowBlur=24;ctx.fillStyle='#ff5360';ctx.fillRect(-78,-72,42,13);ctx.fillRect(36,-72,42,13);ctx.fillStyle='#f7ddd7';for(let i=-4;i<=4;i++)ctx.fillRect(i*15-5,55+Math.abs(i)*2,10,30);text(mission.scareType==='hit'?'FOUND YOU':'I HEARD THAT BEAT',0,225,34,'#fff1e8','Barlow Condensed','center');}
  ctx.restore();for(let y=MAP.y;y<MAP.y+MAP.h;y+=9)rect(MAP.x,y,MAP.w,2,'rgba(255,255,255,.035)');
}
function drawInterlude(){const q=mission.interlude,phase=q.breathPhase||0,grow=phase<4?phase/4:1-(phase-4)/6,ease=.5-.5*Math.cos(Math.PI*Math.max(0,Math.min(1,grow))),radius=54+38*ease,fb=state.feedback||{},entry=q.startBpm?Math.round(q.startBpm):'--',now=fb.bpm?Math.round(fb.bpm):'--',next=levels[q.nextLevel-1];rect(235,145,970,520,'rgba(3,8,13,.97)','#3d665e');text(`LEVEL ${levels[mission.level-1].roman} COMPLETE`,720,195,10,'#91f2ce','IBM Plex Mono','center');text(`NEXT / ${next.name}`,720,250,39,'#e4efeb','Barlow Condensed','center');text('RECOVERY WINDOW / 6 BREATHS PER MINUTE',720,286,9,'#718984','IBM Plex Mono','center');ctx.save();ctx.translate(500,430);ctx.strokeStyle='#91f2ce';ctx.shadowColor='#91f2ce';ctx.shadowBlur=22;ctx.lineWidth=4;ctx.beginPath();ctx.arc(0,0,radius,0,Math.PI*2);ctx.stroke();ctx.shadowBlur=0;text(q.segment||'INHALE',0,5,13,'#dceae6','IBM Plex Mono','center');ctx.restore();text(`${Math.ceil(q.remaining)} s`,500,555,11,'#718984','IBM Plex Mono','center');text('LIVE RESPONSE',835,376,9,'#718984');text(String(now),835,445,62,'#91f2ce','Barlow Condensed');text('BPM NOW',950,437,10,'#91aaa7');text(`ENTRY ${entry} BPM`,835,477,9,'#efc66d');text('Slow pacing can increase vagal rhythm and HRV.',835,525,9,'#809690');text('Your immediate BPM response may differ.',835,546,9,'#809690');}
function drawBriefing(){rect(245,125,950,570,'rgba(4,8,13,.96)','#4c6962');text('SAINT ORISON / INCIDENT 06',285,170,10,'#efc66d');text('THE BUILDING CAN HEAR YOU.',285,230,46,'#e9f3ef','Barlow Condensed');text('Your measured heartbeat travels through the ward as a signal wave.',285,272,13,'#91aaa7');text('The wave reveals the stalker for a moment. It also tells the stalker where to search.',285,296,13,'#91aaa7');levels.forEach((level,i)=>{const x=285+i*285;rect(x,345,255,132,'#0b1820','#29443f');text(`LEVEL ${level.roman}`,x+18,375,10,'#efc66d');text(level.name.replace('THE ',''),x+18,409,18,'#dceae6','Barlow Condensed');text(level.brief,x+18,441,8,'#829895');});text('WASD MOVE   /   SHIFT SPRINT   /   F FLASHLIGHT   /   SPACE SIGNAL FLARE',720,530,9,'#78908c','IBM Plex Mono','center');rect(520,590,400,60,'#91f2ce','#91f2ce');text('ENTER SAINT ORISON  >>',720,627,13,'#071a17','IBM Plex Mono','center');text('PRESS E OR ENTER',720,674,8,'#607a75','IBM Plex Mono','center');}
function drawEnd(){const won=mission.success;rect(315,120,810,590,'rgba(4,8,13,.97)',won?'#91f2ce':'#ff5960');text(won?'EXTRACTION COMPLETE':'SIGNAL CONSUMED',720,208,48,won?'#91f2ce':'#ff5960','Barlow Condensed','center');text(won?'You restored the ward and escaped with the recording.':'The stalker learned the rhythm before you found the exit.',720,245,11,'#99aaa6','IBM Plex Mono','center');const peak=Math.round(Math.max(...mission.frames.map(f=>f.bpm||0),0));[['SCORE',mission.score],['TIME',fmt(mission.t)],['PEAK',peak?`${peak} BPM`:'--'],['DETECTIONS',mission.detections]].forEach((s,i)=>{const x=390+i*170;text(s[0],x,345,8,'#718984','IBM Plex Mono','center');text(String(s[1]),x,385,25,'#e3eeea','Barlow Condensed','center');});text('RELAYS',410,470,9,'#718984');for(let i=0;i<3;i++)rect(410+i*58,490,42,8,i<mission.stage?'#91f2ce':'#26373a');text(`INTEGRITY  ${mission.health}/3`,1030,498,10,mission.health===0?'#ff5960':'#e3eeea','IBM Plex Mono','right');rect(425,590,280,60,'#91f2ce','#91f2ce');text('RUN AGAIN',565,627,12,'#071a17','IBM Plex Mono','center');rect(735,590,280,60,'#111e26','#45635c');text('EXPORT RUN JSON',875,627,11,'#b8cbc5','IBM Plex Mono','center');}
function drawGame(){
  const level=levels[mission.level-1];background();text(`LEVEL ${level.roman} / ${level.name}`,22,35,11,'#91f2ce');text(`SAINT ORISON  /  ${fmt(mission.t)}`,400,35,9,'#607975');text(`RELAYS ${mission.stage}/3`,1048,35,10,mission.stage===3?'#91f2ce':'#efc66d','IBM Plex Mono','right');
  drawFacility();drawMonitor(1082,70,336,700);drawJumpscare();text(mission.message||'',32,800,9,'#718984');
  if(mission.mode==='briefing')drawBriefing();else if(mission.ended)drawEnd();else if(paused){rect(22,70,W-44,700,'rgba(0,0,0,.82)');text('NIGHT PAUSED',W/2,350,52,'#91f2ce','Barlow Condensed','center');text('Press ESC or PAUSE to return to Saint Orison.',W/2,390,11,'#b7c8c2','IBM Plex Mono','center');}else if(mission.interlude&&mission.interlude.delay<=0)drawInterlude();
}
function drawMonitor(x,y,w,h){
  panel(x,y,w,h,'LIVE PHYSIOLOGY / NIGHT DIRECTOR');const fb=state.feedback||{},meter=Math.min(1,Math.max(0,fb.intensity||0));
  text(fb.bpm?Math.round(fb.bpm):'--',x+18,y+90,70,fb.valid?'#91f2ce':'#70858a','Barlow Condensed');text('BPM',x+148,y+82,15,'#91aaa7');text(fb.baseline?`DELTA ${fb.delta>=0?'+':''}${Math.round(fb.delta)} BPM`:'BASELINE ...',x+148,y+106,8,'#efc66d');
  text(fb.valid?'PULSE LINKED':'NEUTRAL / SIGNAL LOST',x+18,y+126,8,fb.valid?'#91f2ce':'#efc66d');rect(x+18,y+141,w-36,7,'#1c292e');rect(x+18,y+141,(w-36)*meter,7,'#ff5960');text('DIRECTOR PRESSURE',x+18,y+164,8,'#718984');text(`${mission.radius.toFixed(2)}x HEARING`,x+w-18,y+164,8,'#efc66d','IBM Plex Mono','right');
  chart(x+18,y+180,w-36,125,graphForPulse(rppgHistory),'#91f2ce','rPPG / LIVE PULSE',40,140);chart(x+18,y+320,w-36,94,graphForPulse(bcgHistory),'#efc66d','rBCG / GUIDED MOTION',40,140);
  text(`LEVEL ${levels[mission.level-1].roman} / MISSION STATE`,x+18,y+444,8,'#718984');text(mission.stage===3?'REACH EXTRACTION':`RESTORE RELAY  ${mission.stage+1}/3`,x+18,y+468,13,mission.stage===3?'#91f2ce':'#dceae6','Barlow Condensed');
  [['INTEGRITY',`${mission.health}/3`,mission.health===1?'#ff5960':'#dceae6'],['FLASHLIGHT',`${Math.round(mission.battery)}%`,mission.battery<20?'#ff5960':'#dceae6'],['FLARES',String(mission.flares),'#efc66d']].forEach((s,i)=>{const yy=y+500+i*31;text(s[0],x+18,yy,8,'#718984');text(s[1],x+w-18,yy,9,s[2],'IBM Plex Mono','right');});
  rect(x+18,y+605,w-36,58,'#081118','#263e3d');text(soundOn&&fb.bpm?`AUDIO SYNC / ${Math.round(fb.bpm)} BPM`:'AUDIO MUTED',x+30,y+627,8,soundOn?'#91f2ce':'#718984');text('EACH BEAT REVEALS IT',x+30,y+645,8,'#899d98');text('AND REVEALS YOU',x+w-30,y+645,8,'#ff5960','IBM Plex Mono','right');
}
function fmt(v){return`${String(Math.floor(v/60)).padStart(2,'0')}:${String(Math.floor(v%60)).padStart(2,'0')}`}
function draw(){if(phase==='game')drawGame();else if(phase==='scan')drawScan();else{background();text('TRACE / NIGHT SIGNAL',42,65,13,'#91f2ce');text('A camera sees the pulse in your face.',42,155,50,'#e4eeeb','Barlow Condensed');text('Then the pulse becomes part of the horror.',42,210,50,'#91aaa7','Barlow Condensed');text('Start with a live camera to see three rPPG methods and experimental camera BCG in one monitor.',42,270,13,'#8d9eaa');panel(42,345,570,260,'#0b151e');text('THE FLOW',67,380,10,'#91f2ce');[['01','CAMERA ACQUISITION','colour pulse + facial motion'],['02','SIGNAL CHECK','live BPM and graphs'],['03','NIGHT RUN','your measured response changes the danger']].forEach((a,i)=>{const yy=430+i*52;text(a[0],67,yy,11,'#efc66d');text(a[1],115,yy,11,'#dceae6');text(a[2],115,yy+17,9,'#7e9692');});text('Use simulation if a camera is unavailable.',42,658,10,'#687f7d');}}

function loop(now){const dt=Math.min(.05,(now-last)/1000);last=now;if(phase==='game')update(dt);draw();requestAnimationFrame(loop);}requestAnimationFrame(loop);
if(new URLSearchParams(location.search).has('demo'))begin('demo');
