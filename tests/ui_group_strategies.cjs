// All network data is synthetic. No real account, trade or notification.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const origin=process.env.UI_TEST_URL||'http://127.0.0.1:8776';
assert.ok(['127.0.0.1','localhost'].includes(new URL(origin).hostname));
const groups=JSON.parse(fs.readFileSync(path.join(root,'evaluation/asset_groups.v1.json'),'utf8')).groups;
const profile={first_name:'Test',language:'ru',deposit:300,risk_pct:1,leverage:10,margin:'cross',trial_left:5,trial_total:5,has_paid_access:true};
const signals=groups.map((group,i)=>({id:i+1,symbol:group.symbols[0],side:'LONG',source:'scanner',confidence:1,
  price:99,entry:100,stop:95,tp1:108,tp2:112,trade_status:'waiting_entry',created_at:new Date().toISOString(),
  strategy:{version:'test',group:group.id,entry_type:'stop',experimental:true},
  sizing:{risk_usdt:3,position_usdt:60,margin_usdt:6,effective_leverage:10}
}));
signals.push({...signals[0],id:99,confidence:.8,strategy:null});
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',route=>{
   const p=new URL(route.request().url()).pathname;
   if(p==='/api/me')return route.fulfill({json:profile});
   if(p==='/api/signals')return route.fulfill({json:signals});
   if(p==='/api/settings'){Object.assign(profile,route.request().postDataJSON());return route.fulfill({json:profile});}
   if(p.startsWith('/api/market/'))return route.fulfill({json:[]});
   if(p.startsWith('/api/asset-icon/'))return route.fulfill({status:404,body:''});
   throw Error(p);
  });
  await page.goto(origin);
  await page.waitForFunction(()=>document.querySelectorAll('#signal-history .signal-row').length===17);
  for(const [lang,label] of [['ru','Экспериментальная стратегия'],['en','Experimental strategy'],['de','Experimentelle Strategie'],['fr','Stratégie expérimentale'],['es','Estrategia experimental']]){
   await page.click('[data-target=settings]');
   await page.selectOption('#language',lang);
   await page.waitForFunction(l=>document.documentElement.lang===l,lang);
   await page.click('[data-target=signals]');
   for(let i=1;i<=16;i++){
    const row=page.locator(`#signal-history [data-signal-id="${i}"]`);
    assert.ok((await row.textContent()).includes(label));
   }
   await page.locator('#signal-history [data-signal-id="1"]').click();
   assert.ok((await page.locator('#plan-confidence').textContent()).includes(label));
   assert.ok((await page.locator('#plan-confidence').textContent()).includes('STOP'));
   assert.ok(!(await page.locator('#plan-confidence').textContent()).includes('100%'));
   await page.click('[data-target=signals]');
   await page.locator('#signal-history [data-signal-id="99"]').click();
   assert.ok((await page.locator('#plan-confidence').textContent()).includes('80%'),'legacy score unchanged');
  }
  await page.click('[data-target=settings]');await page.selectOption('#language','ru');
  await page.waitForFunction(()=>document.documentElement.lang==='ru');
  await page.click('[data-target=signals]');
  for(const [width,height] of [[320,640],[390,844],[844,390],[1280,800]]){
   await page.setViewportSize({width,height});
   await page.waitForTimeout(100);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow');
   if(process.env.UI_SCREENSHOT_DIR){
    fs.mkdirSync(process.env.UI_SCREENSHOT_DIR,{recursive:true});
    await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,`strategy-${width}.png`)});
   }
  }
  await page.locator('#signal-history [data-signal-id="1"]').click();
  signals[0].trade_status='cancelled_before_entry';
  await page.evaluate(()=>refreshLiveData());
  await page.click('[data-target=signals]');
  await page.locator('#signal-history [data-signal-id="1"]').click();
  const action=await page.locator('#plan-action').textContent();
  assert.ok(action.includes('порядок касаний'));
  assert.ok(!action.includes('Цена достигла TP1 раньше входа'));
  profile.scanner_live=true;
  profile.last_scan_at=new Date().toISOString();
  signals.splice(0);
  await page.evaluate(()=>refreshLiveData());
  for(const [lang,fragment] of [
   ['ru','сканер публикует только сетапы'],['en','scanner publishes only setups'],
   ['de','Scanner veröffentlicht nur Setups'],['fr','scanner ne publie que les setups'],
   ['es','escáner solo publica setups']
  ]){
   await page.click('[data-target=settings]');
   await page.selectOption('#language',lang);
   await page.waitForFunction(l=>document.documentElement.lang===l,lang);
   await page.click('[data-target=signals]');
   assert.ok((await page.locator('#signal-history').textContent()).includes(fragment));
  }
  if(process.env.UI_SCREENSHOT_DIR){
   await page.setViewportSize({width:390,height:844});
   await page.click('[data-target=settings]');
   await page.selectOption('#language','ru');
   await page.waitForFunction(()=>document.documentElement.lang==='ru');
   await page.click('[data-target=signals]');
   await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'strategy-empty-390.png')});
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: 16 group labels, 5 languages, legacy score, STOP entry, cancellation, 4 viewports');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
