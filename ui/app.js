'use strict';
const $ = s => document.querySelector(s);
let config, session, controller, recognition, micStream, audioContext, micFrame, busy=false, micStarting=false, generation=0;
const speech = window.speechSynthesis;
let prefs={};try{prefs=JSON.parse(localStorage.getItem('jarvis-prefs')||'{}')||{};}catch{localStorage.removeItem('jarvis-prefs');}
const bars = [];
for (let i=0;i<33;i++) {const b=document.createElement('b');$('#freq').append(b);bars.push(b);}
const labels = {idle:'STANDBY',listening:'LISTENING',transcribing:'TRANSCRIBING',thinking:'PROCESSING',speaking:'SPEAKING',running_action:'EXECUTING',error:'ERROR'};
function setState(s, hint='') {
  $('#reactor').dataset.state=s;$('#state').textContent=labels[s];$('#sys').textContent=s.toUpperCase();
  $('#talk').textContent=s==='listening'||s==='transcribing'?'◉ STOP MICRO':'◎ ACTIVER MICRO';
  $('#hint').textContent=hint || {idle:'Speak or type. Space: microphone. Escape: interrupt.',listening:'Listening to your microphone…',transcribing:'Transcribing speech…',thinking:'Waiting for provider response…',speaking:'Browser voice is speaking…',running_action:'Executing confirmed action…',error:'Operation failed; see conversation.'}[s];
}
function clock() {$('#clock').textContent=new Date().toLocaleTimeString();}clock();setInterval(clock,1000);
function add(role, text) {
  const box=document.createElement('div');box.className='message '+(role==='user'?'you':'');
  const head=document.createElement('div');head.className='from';head.textContent=role==='user'?'● YOU':role==='error'?'⚠ SYSTEM':'◈ J.A.R.V.I.S.';
  const msg=document.createElement('div');msg.className='msg';msg.textContent=text;
  box.append(head,msg);$('#messages').append(box);$('#messages').scrollTop=$('#messages').scrollHeight;return msg;
}
function fail(error) {setState('error');add('error',error.message||String(error));}
async function api(path, options={}) {
  const response=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...options.headers}});
  if (response.status===401) {if (!$('#login-dialog').open) $('#login-dialog').showModal();throw new Error('Sign in to use this backend.');}
  if (!response.ok) {let info;try{info=await response.json();}catch{info={detail:response.statusText};}throw new Error(typeof info.detail==='string'?info.detail:JSON.stringify(info.detail));}
  return response.json();
}
function post(path, body={}) {return api(path,{method:'POST',body:JSON.stringify(body)});}
function guard(fn) {return (...args)=>Promise.resolve().then(()=>fn(...args)).catch(fail);}
let confirmationBusy=false;
async function confirm(text) {
  if(confirmationBusy) throw new Error('Finish the current confirmation first.');
  confirmationBusy=true;$('#confirm-text').textContent=text;$('#confirm-dialog').showModal();
  return new Promise(resolve=>{
    const done=value=>{confirmationBusy=false;$('#confirm-dialog').close();$('#confirm-yes').onclick=null;$('#confirm-no').onclick=null;$('#confirm-dialog').oncancel=null;resolve(value);};
    $('#confirm-yes').onclick=()=>done(true);$('#confirm-no').onclick=()=>done(false);$('#confirm-dialog').oncancel=e=>{e.preventDefault();done(false);};
  });
}
function savePrefs() {
  Object.assign(prefs,{theme:document.body.dataset.theme,provider:$('#provider').value,model:$('#model').value,language:$('#language').value,spoken:$('#spoken').checked,reduced:$('#reduced').checked});
  localStorage.setItem('jarvis-prefs',JSON.stringify(prefs));
}
function chooseModels() {
  $('#model').replaceChildren();
  for(const model of config.providers[$('#provider').value].models) $('#model').add(new Option(model,model));
  if([...$('#model').options].some(o=>o.value===prefs.model))$('#model').value=prefs.model;
}
async function sessions(selected) {
  const list=await api('/sessions');$('#sessions').replaceChildren();
  for(const s of list)$('#sessions').add(new Option(s.title,s.id));
  session=selected && list.some(s=>s.id===selected)?selected:list[0]?.id;
  if(!session){session=(await post('/sessions')).id;return sessions(session);}
  $('#sessions').value=session;localStorage.setItem('jarvis-session',session);
  $('#messages').replaceChildren();for(const m of await api('/sessions/'+session))add(m.role,m.content);
}
async function refreshUsage() {
  const daily=await api('/usage'), current=await api('/usage?session='+encodeURIComponent(session));
  $('#usage').textContent=config.free_mode?`Free-provider mode · ${daily.requests}/${config.daily_request_limit} daily requests · ${current.requests} this session. Stay on the provider’s Free Plan without paid billing. Quota limits stop requests; no paid fallback.`:`Today: ${daily.requests}/${config.daily_request_limit} API requests. Session: ${current.requests}. Reported tokens: ${daily.input_tokens} in / ${daily.output_tokens} out. Budget ledger: $${daily.budget_used_usd.toFixed(4)}${config.daily_budget_usd?' / $'+config.daily_budget_usd:''}. ${daily.requests_without_priced_usage||0} requests lack priced usage (may retain reservations). Set model rates on the server for dollar limits.`;
}
async function telemetry() {
  if(!config)return;
  try{const s=await api('/status');$('#telemetry').textContent=`Python host: ${s.host_os} · CPU ${s.cpu_percent}% · RAM ${s.memory_percent}%${s.battery_percent===null?'':' · battery '+s.battery_percent+'%'}`;$('#tools-status').textContent=`Tools ${s.tools_enabled?'enabled':'disabled'} · ${s.dry_run?'DEMO / DRY RUN: no control commands sent':'REAL actions require confirmation'}`;$('#emergency').textContent=s.tools_enabled?'DISABLE TOOLS':'ENABLE TOOLS';config.tools_enabled=s.tools_enabled;}catch(e){$('#telemetry').textContent='Telemetry unavailable: '+e.message;}
}
async function devices() {
  try{const result=await api('/devices');$('#devices').replaceChildren();const label=document.createElement('strong');label.textContent=result.mode==='demo'?'DEMO DEVICES — NOT CONNECTED':'HOME ASSISTANT — REAL STATES';$('#devices').append(label);
    for(const device of result.devices){const row=document.createElement('div');row.textContent=device.name+' · '+device.state;$('#devices').append(row);
      if(result.mode==='real' && /^(light|switch|scene)\./.test(device.entity_id)){
        for(const service of device.entity_id.startsWith('scene.')?['turn_on']:['turn_on','turn_off']) {const b=document.createElement('button');b.className='ghost';b.textContent=service.replace('_',' ').toUpperCase();b.onclick=guard(()=>action({kind:'home',operation:{entity_id:device.entity_id,service}}));row.append(b);}
      }
    }
  }catch(e){$('#devices').textContent='Home Assistant unavailable: '+e.message;}
}
async function action(payload) {
  const prepared=await post('/actions/prepare',payload);
  let summary=JSON.stringify({action:payload,plan:prepared.plan},null,2);
  if(!await confirm(`${prepared.dry_run?'DEMO / DRY RUN: no real commands will be sent.':'REAL ACTION: this can change your PC or home.'}\n${summary}\nConfirm within 60 seconds. Scenes may partially complete if a device fails.`))return;
  stop();setState('running_action');
  try{const result=await post('/actions/execute',{confirmation:prepared.confirmation});add('assistant',JSON.stringify(result,null,2));setState(result.status==='partial_failure'?'error':'idle');await devices();}catch(e){fail(e);}
}
function sources(entries, msg) {
  if(!entries.length)return;
  const container=document.createElement('div');container.className='tiny';container.textContent='Retrieved search sources (not a blanket verification):';
  for(const source of entries){try{const url=new URL(source.url);if(url.protocol!=='https:')continue;const a=document.createElement('a');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';a.textContent=source.title||url.hostname;container.append(document.createElement('br'),a);}catch{}}
  msg.parentNode.append(container);
}
async function send(text) {
  text=text.trim();if(!text || busy)return;
  stop();busy=true;const run=++generation;
  add('user',text);const target=add('assistant','');setState('thinking');controller=new AbortController();let completed=false;
  try {
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({session,text,provider:$('#provider').value,model:$('#model').value,search:$('#web-search').checked})});
    if(!response.ok){const err=await response.json();if(response.status===401)$('#login-dialog').showModal();throw new Error(typeof err.detail==='string'?err.detail:'Chat request rejected');}
    const reader=response.body.getReader(), decoder=new TextDecoder();let buffer='';
    while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let index;
      while((index=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,index);buffer=buffer.slice(index+2);if(!block.startsWith('data: '))continue;const event=JSON.parse(block.slice(6));
        if(event.type==='token')target.textContent+=event.data;
        if(event.type==='action_proposal'){const b=document.createElement('button');b.className='ghost';b.textContent='REVIEW ACTION';b.onclick=guard(()=>action(event.data));target.parentNode.append(b);}
        if(event.type==='sources')sources(event.data,target);
        if(event.type==='search_status')$('#hint').textContent=event.data;
        if(event.type==='notice')add('assistant',event.data);
        if(event.type==='error')throw new Error(event.data);
        if(event.type==='done')completed=true;
        if(event.type==='memory_proposal'){$('#memory-content').value=event.data;await loadMemories();$('#memory-dialog').showModal();}
        if(event.type==='open_memory'){await loadMemories();$('#memory-dialog').showModal();}
        $('#messages').scrollTop=$('#messages').scrollHeight;
      }
      if(done)break;
    }
    if(!completed)throw new Error('Response ended without completion.');
    if(run===generation){setState('idle');if($('#spoken').checked)say(target.textContent);}
    await refreshUsage();
    // Refresh titles without replacing the streaming transcript.
    const options=await api('/sessions');for(const item of options){const option=[...$('#sessions').options].find(o=>o.value===item.id);if(option)option.textContent=item.title;}
  }catch(e){if(e.name==='AbortError'){if(target.textContent)target.textContent+='\n[Interrupted]';}else fail(e);}
  finally{busy=false;controller=null;}
}
function releaseMic() {
  cancelAnimationFrame(micFrame);micStream?.getTracks().forEach(t=>t.stop());micStream=null;
  audioContext?.close().catch(()=>{});audioContext=null;bars.forEach(b=>b.style.height='5px');
}
function stop() {
  generation++;controller?.abort();recognition?.abort();recognition=null;micStarting=false;releaseMic();speech?.cancel();setState('idle');
}
function say(text) {
  if(!speech){$('#hint').textContent='Spoken output unavailable. Read the transcript.';return;}
  recognition?.abort();recognition=null;releaseMic();speech.cancel();
  const utterance=new SpeechSynthesisUtterance(text);utterance.lang=$('#language').value;
  utterance.voice=speech.getVoices().find(v=>v.lang.startsWith(utterance.lang.split('-')[0]))||null;
  const run=generation;
  utterance.onstart=()=>{if(run===generation)setState('speaking');};
  utterance.onend=()=>{if(run===generation)setState('idle');};
  utterance.onerror=e=>{if(run===generation && !['canceled','interrupted'].includes(e.error))fail(new Error('Browser speech: '+e.error));};speech.speak(utterance);
}
async function listen() {
  if(recognition || micStarting){stop();return;}
  stop();if(busy){$('#hint').textContent='Response interrupted. Try the microphone again once it stops.';return;}
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){fail(new Error('Speech recognition unavailable. Use text or Chrome/Edge. No local speech model is required.'));return;}
  if(!window.isSecureContext){fail(new Error('Microphone access requires localhost or trusted HTTPS on phone/tablet. Use text until HTTPS is configured.'));return;}
  micStarting=true;const run=generation;
  const rec=new SR();recognition=rec;rec.lang=$('#language').value;rec.interimResults=true;rec.continuous=false;let submitted=false;
  rec.onstart=()=>{if(run===generation)setState('listening',micStream?'Listening · real microphone levels':'Listening · audio levels unavailable');};
  rec.onspeechend=()=>{if(run===generation && !submitted)setState('transcribing');};
  rec.onresult=e=>{if(run!==generation)return;let phrase='';let final=false;for(let i=0;i<e.results.length;i++){phrase+=e.results[i][0].transcript;final||=e.results[i].isFinal;}$('#hint').textContent=phrase;if(final&&!submitted){submitted=true;rec.stop();recognition=null;releaseMic();send(phrase);}};
  rec.onerror=e=>{if(run===generation){recognition=null;releaseMic();fail(new Error('Microphone / recognition: '+e.error+'. You can use text.'));}};
  rec.onend=()=>{if(run===generation&&!submitted){recognition=null;releaseMic();setState('idle');}};
  try {
    try {
      const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
      if(run!==generation){stream.getTracks().forEach(t=>t.stop());return;}
      micStream=stream;audioContext=new (window.AudioContext||window.webkitAudioContext)();await audioContext.resume();
      if(run!==generation){releaseMic();return;}
      const analyser=audioContext.createAnalyser();analyser.fftSize=128;audioContext.createMediaStreamSource(stream).connect(analyser);const data=new Uint8Array(analyser.frequencyBinCount);
      const draw=()=>{analyser.getByteFrequencyData(data);bars.forEach((b,i)=>b.style.height=(3+data[i+2]/255*28)+'px');micFrame=requestAnimationFrame(draw);};draw();
    }catch(e){releaseMic();/* Recognition may still work without a separate Web Audio stream. */}
    if(run===generation)rec.start();
  }catch(e){recognition=null;releaseMic();fail(e);}finally{micStarting=false;}
}
async function loadMemories() {
  const list=await api('/memories?q='+encodeURIComponent($('#memory-query').value));$('#memory-list').replaceChildren();
  if(!list.length)$('#memory-list').textContent='No matching memories.';
  for(const memory of list){const row=document.createElement('div');row.className='memory-item';const text=document.createElement('div');text.textContent=memory.category+': '+memory.content;row.append(text);
    const edit=document.createElement('button');edit.className='ghost';edit.textContent='EDIT';edit.onclick=guard(async()=>{const content=prompt('Correct this memory:',memory.content);if(!content?.trim())return;if(await confirm('Store this corrected memory?\n'+content)){await api('/memories/'+memory.id,{method:'PUT',body:JSON.stringify({content,category:memory.category,confirmed:true})});await loadMemories();}});
    const del=document.createElement('button');del.className='ghost';del.textContent='DELETE';del.onclick=guard(async()=>{if(await confirm('Delete this memory and its Markdown export entry?\n'+memory.content)){await api('/memories/'+memory.id,{method:'DELETE'});await loadMemories();}});row.append(edit,del);$('#memory-list').append(row);
  }
}
async function init() {
  config=await api('/config');$('#provider').replaceChildren();
  for(const [name,p] of Object.entries(config.providers))$('#provider').add(new Option((config.free_mode?'Groq · Free Plan required':name)+(p.configured?'':' — key missing'),name));
  $('#provider').value=config.default_provider;if(config.providers[prefs.provider])$('#provider').value=prefs.provider;chooseModels();
  $('#modules').textContent='HUD online · SQLite memory online · '+Object.entries(config.providers).map(([name,p])=>name+': '+(p.configured?'configured (not yet verified)':'key missing')).join(' · ');
  $('#web-search').checked=false;$('#web-search').disabled=config.free_mode||!config.search_configured;$('#web-search').parentNode.lastChild.textContent=config.free_mode?' Web search disabled · no paid search':' Request real web search (optional API cost)';$('#scenes').replaceChildren();
  for(const name of config.scenes){const b=document.createElement('button');b.className='scene';b.textContent='✧ '+name+' · '+(config.dry_run?'DRY RUN':'REVIEW');b.onclick=guard(()=>action({kind:'scene',name}));$('#scenes').append(b);}
  await sessions(localStorage.getItem('jarvis-session'));await Promise.all([telemetry(),devices(),refreshUsage()]);
  if(!$('#messages').children.length)add('assistant','J.A.R.V.I.S. ready. Free setup: add a Groq Free Plan key as GROQ_API_KEY in .env for AI replies. Paid search and provider fallback are disabled. Memory and telemetry work without an API. Device controls start in dry run.');
}
$('#form').onsubmit=e=>{e.preventDefault();const text=$('#input').value;if(!busy){$('#input').value='';send(text);}};
$('#talk').onclick=guard(listen);$('#reactor').onclick=guard(listen);$('#reactor').onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();listen().catch(fail);}};
$('#stop').onclick=stop;$('#test').onclick=()=>{stop();say($('#language').value==='fr-FR'?'Bonsoir. J.A.R.V.I.S. en ligne. Ceci est un test de la voix du navigateur.':'J.A.R.V.I.S. online. This is a browser voice test.');};
$('#theme').onclick=()=>{document.body.dataset.theme=document.body.dataset.theme==='classic'?'feminine':'classic';savePrefs();};
$('#fullscreen').onclick=guard(async()=>{if(document.fullscreenElement)await document.exitFullscreen();else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();else throw new Error('Fullscreen is unavailable in this browser.');});
$('#settings-open').onclick=guard(async()=>{await refreshUsage();$('#settings-dialog').showModal();});
$('#memory-open').onclick=guard(async()=>{await loadMemories();$('#memory-dialog').showModal();});
for(const button of document.querySelectorAll('[data-close]'))button.onclick=()=>document.getElementById(button.dataset.close).close();
$('#provider').onchange=()=>{chooseModels();savePrefs();};
for(const id of ['model','language','spoken','reduced'])$('#'+id).onchange=()=>{document.body.dataset.reduced=String($('#reduced').checked);savePrefs();};
$('#memory-search').onclick=guard(loadMemories);
$('#memory-add').onclick=guard(async()=>{const content=$('#memory-content').value.trim();if(!content)return;if(await confirm('Save this as long-term memory? It stays on your PC, but may be included as context in cloud replies.\n'+content)){await post('/memories',{content,category:$('#memory-category').value,confirmed:true});$('#memory-content').value='';await loadMemories();}});
$('#run-pc').onclick=guard(()=>action({kind:'pc',name:$('#pc-action').value}));
$('#emergency').onclick=guard(async()=>{stop();await post('/tools',{enabled:!config.tools_enabled});await telemetry();});
$('#new-session').onclick=guard(async()=>{stop();if(busy)throw new Error('Wait for the interrupted response to stop.');await sessions((await post('/sessions')).id);});
$('#sessions').onchange=guard(async()=>{stop();if(busy)throw new Error('Wait for the interrupted response to stop.');await sessions($('#sessions').value);});
$('#delete-session').onclick=guard(async()=>{stop();if(await confirm('Permanently delete this conversation? Budget and action logs are retained.')){await api('/sessions/'+session,{method:'DELETE'});await sessions();}});
$('#export').onclick=guard(async()=>{const data=await api('/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='jarvis-export.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('#logout').onclick=guard(async()=>{stop();await post('/logout');$('#settings-dialog').close();$('#messages').replaceChildren();$('#login-dialog').showModal();});
$('#login-form').onsubmit=e=>{e.preventDefault();guard(async()=>{try{await post('/login',{password:$('#password').value});$('#password').value='';$('#login-dialog').close();await init();}catch(error){$('#login-error').textContent=error.message;}})();};
$('#login-dialog').oncancel=e=>e.preventDefault();
window.addEventListener('keydown',e=>{if(e.key==='Escape')stop();if(e.code==='Space'&&!['INPUT','TEXTAREA','SELECT','BUTTON'].includes(document.activeElement.tagName)&&!document.querySelector('dialog[open]')&&document.activeElement!==$('#reactor')){e.preventDefault();listen().catch(fail);}});
window.addEventListener('pagehide',stop);
document.body.dataset.theme=prefs.theme||'classic';$('#language').value=prefs.language||'fr-FR';$('#spoken').checked=prefs.spoken!==false;$('#reduced').checked=Boolean(prefs.reduced);document.body.dataset.reduced=String($('#reduced').checked);
init().catch(fail);setInterval(telemetry,5000);setInterval(()=>{if(config&&!document.hidden)devices();},30000);
