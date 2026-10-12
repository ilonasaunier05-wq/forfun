// Real local backend + Chromium; no voice, provider, or hardware responses are fabricated.
const {chromium}=require('playwright');
const {spawn}=require('child_process');
const {mkdtempSync,rmSync,readFileSync,mkdirSync}=require('fs');
const {tmpdir}=require('os');const {join}=require('path');const assert=require('assert/strict');
const directory=mkdtempSync(join(tmpdir(),'jarvis-hud-'));
const artifacts=process.env.JARVIS_ARTIFACTS_DIR||join(directory,'screenshots');mkdirSync(artifacts,{recursive:true});
const python=process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python';
const server=spawn(python,['main.py','--text','--no-browser','--port','8765'],{env:{...process.env,NOTES_DIR:join(directory,'notes'),PROJECTS_WRITE_DIR:join(directory,'workspace'),GROQ_API_KEY:'',JARVIS_PASSWORD:'ui-test-password'},stdio:['pipe','pipe','pipe']});
let logs='';server.stderr.on('data',d=>logs+=d);server.stdout.on('data',d=>logs+=d);
(async()=>{let browser;try{
 for(let i=0;i<120;i++){try{if((await fetch('http://localhost:8765/')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));if(i===119)throw Error(logs);}
 browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8765/');await page.locator('#login-dialog').waitFor({state:'visible'});await page.fill('#password','ui-test-password');await page.locator('#login-form button').click();
 await page.waitForFunction(()=>document.querySelector('#telemetry').textContent.includes('Hôte Python'));
 await page.waitForFunction(()=>document.querySelector('#jarvis-orb')?.dataset.energy!==undefined);
 assert(await page.locator('#jarvis-orb').isVisible());
 // Component-level visual input test, not a claim of physical audio playback.
 await page.evaluate(()=>window.jarvisOrb.speech(.8,true));
 await page.waitForFunction(()=>Number(document.querySelector('#jarvis-orb').dataset.energy)>.2);
 await page.evaluate(()=>window.jarvisOrb.speech(0,false));
 await page.waitForFunction(()=>Number(document.querySelector('#jarvis-orb').dataset.energy)<.05);
 await page.screenshot({path:join(artifacts,'JARVIS_ORB_CYAN.png')});
 await page.click('#theme');assert.equal(await page.locator('body').getAttribute('data-theme'),'feminine');
 await page.waitForTimeout(100);await page.screenshot({path:join(artifacts,'JARVIS_ORB_PINK.png')});
 await page.click('#settings-open');assert.equal(await page.locator('#voice').inputValue(),'en-GB-RyanNeural');await page.selectOption('#language','fr');assert.equal(await page.locator('#voice').inputValue(),'en-GB-RyanNeural');await page.uncheck('#spoken');await page.click('[data-close="settings-dialog"]');
 await page.fill('#input','Hello');await page.locator('#form button').click();await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('GROQ_API_KEY is missing'));
 await page.click('#run-pc');await page.locator('#confirm-dialog').waitFor({state:'visible'});assert((await page.locator('#confirm-text').innerText()).includes('open_app'));await page.click('#confirm-no');await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('cancelled'));
 await page.click('#memory-open');await page.locator('#memory-dialog').waitFor({state:'visible'});await page.fill('#memory-content','Real browser-confirmed note for this test');await page.click('#memory-add');
 await page.locator('#confirm-dialog').waitFor({state:'visible'});assert((await page.locator('#confirm-text').innerText()).includes('remember'));await page.click('#confirm-yes');
 await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('Saved to memory.md'));
 await page.click('#memory-open');await page.locator('#memory-dialog').waitFor({state:'visible'});assert((await page.locator('#memory-markdown').innerText()).includes('Real browser-confirmed'));await page.click('[data-close="memory-dialog"]');
 await page.evaluate(async()=>{const r=await fetch('/api/tool',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'create_file',arguments:{path:'School/browser.txt',content:'Original browser file\n'}})});if(!r.ok)throw Error(await r.text());});
 await page.locator('#confirm-dialog').waitFor({state:'visible'});assert((await page.locator('#confirm-text').innerText()).includes('+Original browser file'));await page.click('#confirm-yes');
 await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('Actual file write verified'));
 const target=join(directory,'workspace','School','browser.txt');assert.equal(readFileSync(target,'utf8'),'Original browser file\n');
 const expected=require('crypto').createHash('sha256').update(readFileSync(target)).digest('hex');
 await page.evaluate(async hash=>{const r=await fetch('/api/tool',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'edit_file',arguments:{path:'School/browser.txt',old_text:'Original browser file',new_text:'Updated browser file',expected_sha256:hash}})});if(!r.ok)throw Error(await r.text());},expected);
 await page.locator('#confirm-dialog').waitFor({state:'visible'});assert((await page.locator('#confirm-text').innerText()).includes('-Original browser file'));await page.click('#confirm-yes');
 await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('browser.txt.bak'));assert.equal(readFileSync(target,'utf8'),'Updated browser file\n');
 await page.click('#emergency');await page.waitForFunction(()=>document.querySelector('#tools-status').textContent.includes('disabled'));
 for(const [name,width,height] of [['desktop',1440,1000],['tablet',800,1280],['phone',390,844]]){await page.setViewportSize({width,height});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name+' overflow');assert(await page.locator('#reactor svg').isVisible());}
 assert.deepEqual(errors,[]);const stopped=new Promise(r=>server.once('exit',r));server.stdin.write('/quit\n');await Promise.race([stopped,new Promise((_,reject)=>setTimeout(()=>reject(Error('Quit hung with HUD stream still connected')),7000))]);console.log('PASS: real authenticated HUD, native voice configuration, missing-key failure, actually confirmed Markdown write/read-back, emergency stop, desktop/tablet/phone. No hardware/API success is inferred.');
}finally{if(browser)await browser.close();if(server.exitCode===null){server.stdin.write('/quit\n');const timeout=setTimeout(()=>server.kill('SIGTERM'),3000);await new Promise(r=>server.once('exit',r));clearTimeout(timeout);}rmSync(directory,{recursive:true,force:true});}})().catch(e=>{console.error(e);process.exitCode=1;});
