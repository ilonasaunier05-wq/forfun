// Optional browser smoke test: npm install --prefix /tmp/jarvis-browser playwright
// NODE_PATH=/tmp/jarvis-browser/node_modules node tests/ui_smoke.cjs
const {chromium}=require('playwright');
const {spawn}=require('child_process');
const {mkdtempSync,rmSync}=require('fs');
const {tmpdir}=require('os');
const {join}=require('path');
const assert=require('assert/strict');
const directory=mkdtempSync(join(tmpdir(),'jarvis-ui-'));
const python=process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python';
const server=spawn(python,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8765','--no-proxy-headers'],{env:{...process.env,JARVIS_DATA_DIR:directory,JARVIS_PASSWORD:'ui-test-password',JARVIS_DRY_RUN:'true',JARVIS_FREE_MODE:'true',AI_BASE_URL:'https://api.groq.com/openai/v1',GROQ_API_KEY:'',OPENAI_API_KEY:'',JARVIS_OPENAI_KEY:'',AI_API_KEY:'',HA_URL:'',HA_TOKEN:''},stdio:'pipe'});
let logs='';server.stderr.on('data',chunk=>logs+=chunk);
(async()=>{
 let browser;
 try{
  for(let i=0;i<100;i++){try{if((await fetch('http://localhost:8765/')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));if(i===99)throw new Error(logs);}
  browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://localhost:8765/');await page.locator('#login-dialog').waitFor({state:'visible'});
  await page.fill('#password','ui-test-password');await page.locator('#login-form button').click();
  await page.waitForFunction(()=>document.querySelector('#telemetry').textContent.includes('Python host:'));
  assert(await page.locator('#devices').innerText().then(t=>t.includes('DEMO DEVICES')));
  assert((await page.context().cookies()).find(c=>c.name==='jarvis_session').httpOnly);
  await page.click('#theme');assert.equal(await page.locator('body').getAttribute('data-theme'),'feminine');
  await page.click('#settings-open');assert.equal(await page.locator('#provider').inputValue(),'compatible');assert(await page.locator('#web-search').isDisabled());assert.equal(await page.locator('#provider option').count(),1);await page.uncheck('#spoken');await page.check('#reduced');await page.click('[data-close="settings-dialog"]');
  await page.fill('#input','Remember that I study physics');await page.locator('#form button').click();
  await page.locator('#memory-dialog').waitFor({state:'visible'});assert.equal(await page.locator('#memory-content').inputValue(),'I study physics');
  await page.click('#memory-add');await page.locator('#confirm-dialog').waitFor({state:'visible'});await page.click('#confirm-yes');
  await page.waitForFunction(()=>document.querySelector('#memory-list').textContent.includes('I study physics'));
  await page.click('[data-close="memory-dialog"]');await page.reload();
  await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('Remember that I study physics'));
  await page.click('#memory-open');await page.locator('#memory-dialog').waitFor({state:'visible'});assert((await page.locator('#memory-list').innerText()).includes('I study physics'));
  await page.locator('#memory-list button').filter({hasText:'DELETE'}).click();await page.click('#confirm-yes');
  await page.waitForFunction(()=>document.querySelector('#memory-list').textContent.includes('No matching memories'));
  await page.click('[data-close="memory-dialog"]');
  await page.fill('#input','Hello');await page.locator('#form button').click();
  await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('API key is missing'));
  assert.equal(await page.locator('#reactor').getAttribute('data-state'),'error');
  await page.click('#run-pc');await page.locator('#confirm-dialog').waitFor({state:'visible'});assert((await page.locator('#confirm-text').innerText()).includes('DRY RUN'));await page.click('#confirm-yes');
  await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('No PC or home command was sent'));
  await page.click('#emergency');await page.waitForFunction(()=>document.querySelector('#tools-status').textContent.includes('disabled'));
  await page.click('#emergency');await page.waitForFunction(()=>document.querySelector('#tools-status').textContent.includes('enabled'));
  // Provider protocol is tested separately in Python; this fixture exercises streamed HUD rendering.
  await page.route('**/api/chat',route=>route.fulfill({status:200,contentType:'text/event-stream',body:'data: {"type":"token","data":"Streamed "}\n\ndata: {"type":"token","data":"answer"}\n\ndata: {"type":"done","data":true}\n\n'}));
  await page.fill('#input','Streaming fixture');await page.locator('#form button').click();await page.waitForFunction(()=>document.querySelector('#messages').textContent.includes('Streamed answer'));
  await page.waitForFunction(()=>document.querySelector('#reactor').dataset.state==='idle');
  for(const [name,width,height] of [['desktop',1440,1000],['tablet',800,1280],['phone',390,844]]){
   await page.setViewportSize({width,height});await page.screenshot({path:join(directory,name+'.png'),fullPage:true});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name+' has horizontal overflow');
   assert(await page.locator('#reactor svg').isVisible());
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: authenticated HUD, themes, confirmed memory CRUD/reload, missing-key error, dry-run PC action, emergency stop, streamed rendering, desktop/tablet/phone layouts.');
 } finally {
  if(browser)await browser.close();server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));rmSync(directory,{recursive:true,force:true});
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
