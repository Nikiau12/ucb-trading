// Local-only regression: informational alerts remain distinct from executable plans.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const origin=process.env.UI_TEST_URL||'http://127.0.0.1:8765';
assert.ok(['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Local server only');
const now=new Date().toISOString();
const profile={first_name:'Demo',language:'ru',deposit:300,risk_pct:1,leverage:10,margin:'cross',trial_left:5,trial_total:5,has_paid_access:false};
const alerts=[
  {id:101,symbol:'ETH_USDT',source:'spike',side:'LONG',price:3500,entry:3500,stop:null,tp1:null,tp2:null,timeframe:'15m',created_at:now,sizing:null},
  {id:102,symbol:'SOL_USDT',source:'smc',side:'SHORT',price:160,entry:160,stop:166,tp1:150,tp2:null,timeframe:'4h',created_at:now,sizing:null},
  {id:103,symbol:'XRP_USDT',source:'listing',side:'LONG',price:null,entry:null,stop:null,tp1:null,tp2:null,timeframe:'4h',created_at:now,sizing:null},
  {id:104,symbol:'BTC_USDT',source:'scanner',side:'LONG',price:68000,entry:68000,stop:66000,tp1:71000,tp2:74000,timeframe:'4h',created_at:now,trade_status:'active',sizing:{position_usdt:100,margin_usdt:10,risk_usdt:3}}
];
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'chrome'});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/api/**',route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/api/me')return route.fulfill({json:profile});
      if(url.pathname==='/api/settings'){
        Object.assign(profile,route.request().postDataJSON());
        return route.fulfill({json:profile});
      }
      if(url.pathname==='/api/signals')return route.fulfill({json:alerts});
      if(url.pathname.startsWith('/api/market/'))return route.fulfill({json:[]});
      if(url.pathname.startsWith('/api/asset-icon/'))return route.fulfill({status:404,body:''});
      throw Error(`Unexpected API ${url.pathname}`);
    });
    await page.goto(`${origin}?signal_id=101`);
    await page.waitForSelector('#alert-body:not([hidden])');
    assert.equal(await page.locator('#alert-type').textContent(),'Скальп');
    assert.match(await page.locator('#alert-reference').textContent(),/#101.*15M/);
    assert.equal(await page.locator('#plan-body').isVisible(),false);
    assert.equal(await page.locator('#alert-levels .detail-metric').count(),1);
    assert.match(await page.locator('#alert-note').textContent(),/не готовый торговый план/);
    assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(11, 16, 25)');
    assert.equal(await page.evaluate(()=>getComputedStyle(document.querySelector('#chart')).touchAction),'none');
    assert.equal(await page.locator('.brand-credit').textContent(),'Mini App разработано диджитал бюро YO!BIG');
    await page.click('[data-target=signals]');
    for(const [filter,count] of [['ALL',4],['SETUP',1],['SCALP',1],['SMC',1],['LISTING',1],['LONG',3],['SHORT',1]]){
      await page.click(`[data-filter="${filter}"]`);
      assert.equal(await page.locator('#signal-history .signal-row').count(),count,filter);
    }
    await page.click('[data-filter="SMC"]');
    await page.locator('#signal-history [data-signal-id="102"]').click();
    await page.waitForSelector('#alert-body:not([hidden])');
    assert.equal(await page.locator('#alert-type').textContent(),'SMC-сетап');
    assert.equal(await page.locator('#alert-levels .detail-metric').count(),3);
    await page.setViewportSize({width:320,height:640});
    await page.click('[data-target=signals]');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.click('[data-target=settings]');
    for(const [lang,copy] of Object.entries({
      ru:'Mini App разработано диджитал бюро YO!BIG',
      en:'Mini App developed by YO!BIG Digital Bureau',
      de:'Mini App entwickelt vom Digitalbüro YO!BIG',
      fr:'Mini App développée par le bureau digital YO!BIG',
      es:'Mini App desarrollada por el estudio digital YO!BIG'
    })){
      await page.selectOption('#language',lang);
      await page.waitForFunction(value=>document.documentElement.lang===value,lang);
      assert.equal(await page.locator('.brand-credit').textContent(),copy);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      assert.equal(await page.locator('.brand-credit').evaluate(node=>node.scrollHeight<=node.clientHeight+1),true,`${lang}: credit clipped`);
    }
    assert.deepEqual(errors,[]);
    console.log('PASS dark theme, linked alerts, all filters, localized footer, 320px');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
