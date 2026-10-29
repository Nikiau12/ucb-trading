// Run with Playwright installed and a local Mini App server. All API calls are
// intercepted: no payment, profile, database, or exchange writes are performed.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const origin=process.env.UI_TEST_URL||'http://127.0.0.1:8765';
assert.ok(['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Local server only');
const out=process.env.UI_SCREENSHOT_DIR||'/tmp/ucb-light-screens';
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const profile={first_name:'Demo',language:'ru',deposit:400,risk_pct:1,leverage:10,margin:'cross',trial_left:3,trial_total:5,has_paid_access:false,payment_wallet:'DEMO-NOT-A-PAYMENT-ADDRESS-1234567890',payment_network:'TRC20',payment_amount_usdt:'29.99',subscription_price_usdt:'29.99',subscription_days:30};
 const signals=['BTC','SOL','ETH'].map((coin,i)=>({id:i+1,symbol:coin+'_USDT',side:i===1?'SHORT':'LONG',confidence:.78,price:64120,entry:64000,stop:i===1?65200:62800,tp1:i===1?62500:65500,tp2:i===1?61000:67000,created_at:new Date(Date.now()-(i+1)*3600000).toISOString(),source:'scanner',timeframe:'4h',regime:'1d=up;4h=up;regime=trend',sizing:{position_usdt:213.33,margin_usdt:21.33,risk_usdt:4,effective_leverage:10}}));
 let paymentCalls=0;
 const marketRequests=[];
 await page.route('**/api/**',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname==='/api/me')return route.fulfill({json:profile});
  if(url.pathname==='/api/signals')return route.fulfill({json:signals});
  if(url.pathname==='/api/settings'){Object.assign(profile,route.request().postDataJSON());return route.fulfill({json:profile});}
  if(url.pathname==='/api/payment'){
   paymentCalls++;
   await new Promise(resolve=>setTimeout(resolve,150));
   return route.fulfill({status:paymentCalls===1?400:200,json:paymentCalls===1?{access_open:false}:{access_open:true,paid_until:Math.floor(Date.now()/1000)+2592000}});
  }
  if(url.pathname.startsWith('/api/market/')){marketRequests.push(url.pathname+url.search);return route.fulfill({json:[]});}
  throw Error('Unexpected API '+url.pathname);
 });
 await page.goto(origin);
 await page.waitForSelector('#plan-heading-coin .loaded');
 await page.waitForSelector('#chart-coin .loaded');
 assert.equal(await page.locator('#major-market-list .major-market-card').count(),3);
 assert.deepEqual(await page.locator('#overview-timeframe button').allTextContents(),['15m','1h','4h','1d']);
 assert.ok(marketRequests.some(value=>value.startsWith('/api/market/BTC_USDT?timeframe=4h')));
 await page.evaluate(()=>{const label=document.createElement('div');label.textContent='ДЕМО · тестовые данные';label.style.cssText='background:#eaf0ff;color:#526482;text-align:center;padding:8px;font:11px sans-serif';document.querySelector('.topbar').before(label);});
 const shot=async name=>{await page.mouse.move(0,0);await page.waitForTimeout(200);return page.screenshot({path:path.join(out,name+'.png'),fullPage:false});};
 const noOverflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await shot('overview-btc');
 await page.click('[data-target=signals]');
 await page.waitForFunction(()=>[...document.querySelectorAll('#signal-history img')].every(i=>i.complete&&i.naturalWidth>0));
 await shot('signals');
 await page.click('[data-filter=SHORT]');assert.equal(await page.locator('.signal-row:visible').count(),1);
 await page.click('[data-filter=LONG]');assert.equal(await page.locator('.signal-row:visible').count(),2);
 await page.click('[data-filter=ALL]');
 await page.click('[data-target=settings]');
 await page.fill('#deposit-input','500');await page.click('#settings-form button[type=submit]');
 await page.waitForFunction(()=>document.querySelector('#form-status').textContent.length>0);assert.equal(profile.deposit,500);
 await page.waitForFunction(()=>!document.querySelector('#toast').classList.contains('show'));
 const settingsHeight=await page.evaluate(()=>document.documentElement.scrollHeight);
 await page.setViewportSize({width:390,height:settingsHeight});
 await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
 await shot('settings');
 await page.setViewportSize({width:390,height:844});
 await page.locator('#payment-button').scrollIntoViewIfNeeded();await shot('subscription');
 await page.click('#payment-button');await page.waitForFunction(()=>document.querySelector('#payment-address').textContent.startsWith('DEMO-'));
 await shot('payment');
 assert.equal(await page.locator('#payment-close').evaluate(el=>el===document.activeElement),true);
 await page.keyboard.press('Shift+Tab');assert.equal(await page.locator('#payment-form button').evaluate(el=>el===document.activeElement),true);
 await page.keyboard.press('Tab');assert.equal(await page.locator('#payment-close').evaluate(el=>el===document.activeElement),true);
 await page.fill('#payment-hash','a'.repeat(64));await page.click('#payment-form button');
 await page.waitForSelector('#payment-error:not([hidden])');assert.equal(await page.locator('#payment-form').isVisible(),false);await shot('payment-error');
 await page.click('#payment-retry');await page.click('#payment-form button');
 await page.waitForSelector('#payment-success:not([hidden])');assert.equal(await page.locator('#payment-form').isVisible(),false);await shot('payment-success');
 await page.keyboard.press('Escape');assert.equal(await page.locator('#payment-sheet').isVisible(),false);
 for(const width of [320,390,768,1280]){
  await page.setViewportSize({width,height:844});
  for(const view of ['signals','settings']){await page.click('[data-target='+view+']');await noOverflow();}
  await page.evaluate(()=>openPayment());await noOverflow();
  const bounds=await page.locator('#payment-panel').boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=width+1);
  await page.click('#payment-close');
 }
 // Short-height viewport models the space available above a mobile keyboard.
 await page.setViewportSize({width:390,height:440});await page.evaluate(()=>openPayment());
 await page.locator('#payment-form button').scrollIntoViewIfNeeded();await noOverflow();
 await page.click('#payment-close');
 for(const lang of ['ru','en','de','fr','es']){
  await page.selectOption('#language',lang);
  await page.waitForFunction(value=>document.documentElement.lang===value,lang);
  await noOverflow();await page.evaluate(()=>openPayment());await noOverflow();await page.click('#payment-close');
 }
 assert.equal(paymentCalls,2);assert.deepEqual(errors,[]);
 console.log('PASS filters, settings, payment retry/success, focus, 4 widths, short viewport, 5 languages; only mocked API writes');
 await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
