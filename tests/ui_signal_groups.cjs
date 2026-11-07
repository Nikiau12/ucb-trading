// Local-only fixtures. All account, market and Telegram requests are intercepted.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const origin=process.env.UI_TEST_URL||'http://127.0.0.1:8769';
assert.ok(['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Local server only');
const profile={first_name:'Demo',language:'ru',deposit:400,risk_pct:1,leverage:10,margin:'cross',trial_left:5,trial_total:5,has_paid_access:false,signal_groups:null,bingx_account:{connected:false}};
const feed=['BTC_USDT','ETH_USDT','SOL_USDT'].map((symbol,i)=>({id:i+1,symbol,side:'LONG',source:'scanner',entry:100,price:100,stop:97,tp1:103,tp2:106,confidence:.8,timeframe:'4h',trade_status:'active',tracking_status:'none',created_at:new Date().toISOString()}));
const group=s=>({BTC_USDT:'core_btc',ETH_USDT:'core_eth',SOL_USDT:'core_sol'})[s.symbol];
const visible=()=>feed.filter(s=>s.tracking_status==='active'||profile.signal_groups===null||profile.signal_groups.includes(group(s)));
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[],writes=[];
  let failGroups=false,failAccount=false,failProfile=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url()),body=req.postDataJSON();
   if(req.method()!=='GET')writes.push({path:url.pathname,method:req.method(),body});
   if(url.pathname==='/api/me')return failProfile?route.fulfill({status:503,json:{detail:'unavailable'}}):route.fulfill({json:profile});
   if(url.pathname==='/api/signals')return route.fulfill({json:visible()});
   if(url.pathname==='/api/settings'){
    if(failGroups)return route.fulfill({status:503,json:{detail:'unavailable'}});
    Object.assign(profile,body);return route.fulfill({json:{ok:true}});
   }
   if(url.pathname==='/api/bingx-account'){
    if(failAccount)return route.fulfill({status:503,json:{detail:'unavailable'}});
    if(req.method()==='DELETE'){profile.bingx_account={connected:false};return route.fulfill({json:{connected:false}});}
    profile.bingx_account={connected:true,key_hint:'1234',balance:550,checked_at:new Date().toISOString()};profile.deposit=550;
    return route.fulfill({json:profile.bingx_account});
   }
   const tracking=url.pathname.match(/^\/api\/signals\/(\d+)\/tracking$/);
   if(tracking){const s=feed.find(s=>s.id===Number(tracking[1]));s.tracking_status=body.active?'active':'exited';return route.fulfill({json:{tracking_status:s.tracking_status}});}
   if(url.pathname.startsWith('/api/market/'))return route.fulfill({json:[]});
   if(url.pathname.startsWith('/api/asset-icon/'))return route.fulfill({status:404,body:''});
   throw Error(`Unexpected request ${req.method()} ${url.pathname}`);
  });
  await page.goto(origin);
  await page.waitForFunction(()=>document.querySelectorAll('#signal-history .signal-row').length===3);
  await page.click('[data-target=signals]');
  assert.equal(await page.locator('[data-filter=SCALP],[data-filter=SMC]').count(),0);
  await page.click('.signal-group-field summary');
  assert.equal(await page.locator('#signal-group input').count(),18);
  await page.check('[data-group-id=core_btc]');
  await page.waitForFunction(()=>document.querySelectorAll('#signal-history .signal-row').length===1);
  await page.check('[data-group-id=core_eth]');
  await page.waitForFunction(()=>document.querySelectorAll('#signal-history .signal-row').length===2);
  await page.check('[data-group-id=core_sol]');
  await page.waitForFunction(()=>document.querySelectorAll('#signal-history .signal-row').length===3);
  assert.deepEqual(profile.signal_groups,['core_btc','core_eth','core_sol']);
  await page.reload();
  await page.waitForFunction(()=>document.querySelectorAll('#signal-history .signal-row').length===3);
  await page.click('[data-target=signals]');await page.click('.signal-group-field summary');
  for(const id of profile.signal_groups)assert.equal(await page.locator(`[data-group-id=${id}]`).isChecked(),true);
  failGroups=true;
  await page.click('[data-group-id=core_sol]');
  await page.waitForFunction(()=>!document.querySelector('[data-group-id=core_sol]').disabled);
  assert.equal(await page.locator('[data-group-id=core_sol]').isChecked(),true,'failed save rolls back the selection');
  failGroups=false;
  await page.click('#signal-history [data-signal-id="1"]');
  await page.click('#tracking-button');
  await page.waitForFunction(()=>document.querySelector('#tracking-button').textContent==='Я вышел');
  assert.equal(feed[0].tracking_status,'active');
  await page.click('[data-target=signals]');
  await page.uncheck('[data-group-id=core_btc]');
  await page.waitForFunction(()=>!document.querySelector('[data-group-id=core_btc]').disabled);
  assert.equal(await page.locator('#signal-history [data-signal-id="1"]').count(),1,'active trade survives group change');
  await page.click('#signal-history [data-signal-id="1"]');await page.click('#tracking-button');
  await page.waitForFunction(()=>document.querySelector('#tracking-button').disabled);
  assert.equal(feed[0].tracking_status,'exited');
  await page.click('[data-target=settings]');
  assert.equal(await page.locator('[data-target=settings]').textContent(),'Аккаунт');
  assert.equal(await page.locator('#manual-deposit-field').isVisible(),true);
  await page.click('#account-connection summary');
  await page.fill('#account-key','fake-key-1234');await page.fill('#account-secret','fake-secret-5678');
  await page.click('#account-connect');
  await page.waitForFunction(()=>document.querySelector('#account-disconnect').hidden===false);
  assert.equal(await page.locator('#account-key').inputValue(),'');
  assert.equal(await page.locator('#account-secret').inputValue(),'');
  assert.equal(await page.locator('#deposit-input').isDisabled(),true);
  assert.equal(await page.locator('#deposit-input').inputValue(),'550');
  assert.equal(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}).includes('fake-secret')),false);
  assert.equal(await page.locator('#manual-deposit-field').isVisible(),false);
  assert.equal(await page.locator('#account-connection').evaluate(el=>el.open),false);
  assert.equal(await page.locator('#account-balance').textContent(),'550,00');
  await page.fill('#risk-input','2');
  await page.fill('#leverage-input','20');
  assert.match(await page.locator('#account-risk-amount').textContent(),/11,00 USDT/);
  await page.selectOption('#language','de');
  assert.equal(await page.locator('#risk-input').inputValue(),'2','language change keeps the draft');
  await page.selectOption('#language','ru');
  profile.deposit=600;profile.bingx_account.balance=600;
  await page.click('#account-refresh');
  await page.waitForFunction(()=>!document.querySelector('#account-refresh').disabled);
  assert.equal(await page.locator('#risk-input').inputValue(),'2','refresh keeps unsaved risk');
  assert.equal(await page.locator('#leverage-input').inputValue(),'20','refresh keeps unsaved leverage');
  assert.equal(await page.locator('#account-balance').textContent(),'600,00');
  assert.match(await page.locator('#account-risk-amount').textContent(),/12,00 USDT/);
  failGroups=true;await page.click('#account-save');
  await page.waitForFunction(()=>document.querySelector('#form-status').classList.contains('error'));
  assert.equal(await page.locator('#risk-input').inputValue(),'2','failed save keeps draft');
  failGroups=false;
  await page.click('#settings-form button[type=submit]');
  await page.waitForFunction(()=>document.querySelector('#form-status').textContent==='Изменения сохранены'&&!document.querySelector('#account-save').disabled);
  const settingsWrite=writes.filter(x=>x.path==='/api/settings').at(-1);
  assert.equal('deposit' in settingsWrite.body,false,'API balance cannot be overridden by manual settings');
  assert.equal(profile.risk_pct,2);assert.equal(profile.leverage,20);
  await page.fill('#risk-input','3');await page.click('#account-discard');
  assert.equal(await page.locator('#risk-input').inputValue(),'2');
  profile.deposit=0;profile.bingx_account.balance=0;
  await page.click('#account-refresh');await page.waitForFunction(()=>!document.querySelector('#account-refresh').disabled);
  assert.equal(await page.locator('#account-balance').textContent(),'0,00','zero is a real balance');
  assert.match(await page.locator('#account-balance-note').textContent(),/нулевой/);
  failProfile=true;await page.click('#account-refresh');await page.waitForFunction(()=>!document.querySelector('#account-refresh').disabled);
  assert.equal(await page.locator('#account-balance').textContent(),'—','API failure must not display zero or a stale balance');
  assert.equal(await page.locator('#account-connection-badge').getAttribute('data-state'),'unavailable');
  failProfile=false;
  await page.click('#account-connection summary');
  await page.click('#account-disconnect');
  await page.waitForFunction(()=>document.querySelector('#account-disconnect').hidden===true);
  assert.equal(await page.locator('#deposit-input').isDisabled(),false);
  failAccount=true;
  await page.fill('#account-key','invalid-key-1234');await page.fill('#account-secret','invalid-secret');await page.click('#account-connect');
  await page.waitForFunction(()=>!document.querySelector('#account-connect').disabled);
  assert.equal(await page.locator('#account-secret').inputValue(),'');
  for(const lang of ['en','ru','de','fr','es']){
   await page.selectOption('#language',lang);
   await page.waitForFunction(v=>document.documentElement.lang===v,lang);
   for(const [width,height] of [[320,640],[390,844],[844,390],[1280,800]]){
    await page.setViewportSize({width,height});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`settings overflow ${lang} ${width}`);
    await page.click('[data-target=signals]');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`groups overflow ${lang} ${width}`);
    await page.click('[data-target=settings]');
   }
  }
  await page.selectOption('#language','ru');
  // Restore a connected fixture for visual review; no real account is used.
  profile.deposit=550;profile.bingx_account={connected:true,balance:550,key_hint:'1234',checked_at:new Date().toISOString()};
  await page.reload();await page.waitForFunction(()=>document.querySelector('#account-balance').textContent==='550,00');
  await page.waitForFunction(()=>!document.querySelector('#toast').classList.contains('show'));
  if(process.env.UI_SCREENSHOT_DIR){
   fs.mkdirSync(process.env.UI_SCREENSHOT_DIR,{recursive:true});
   for(const [name,width,height] of [['mobile',390,844],['desktop',1280,800]]){
    await page.setViewportSize({width,height});
    await page.click('[data-target=settings]');await page.mouse.move(0,0);await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,`account-${name}.png`),fullPage:true});
    await page.evaluate(()=>window.scrollTo({top:document.querySelector('#trade-preferences-title').getBoundingClientRect().top+scrollY-25,behavior:'instant'}));
    await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,`account-trading-${name}.png`)});
    await page.click('[data-target=signals]');await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,`groups-${name}.png`),fullPage:true});
   }
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({ok:true,groupWrites:writes.filter(x=>x.body?.signal_groups!==undefined).length,trackingWrites:writes.filter(x=>x.path.endsWith('/tracking')).length,languages:5,viewports:4}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
