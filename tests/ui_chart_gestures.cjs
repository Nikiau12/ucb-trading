// Run against a local Mini App server with Playwright and Chrome available.
// All API calls are mocked; no exchange, Telegram, database, or payment writes.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');

const origin=process.env.UI_TEST_URL||'http://127.0.0.1:8765';
assert.ok(['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Local server only');

const intervalSeconds=14400;
const lastTime=Math.floor(Date.now()/1000/intervalSeconds)*intervalSeconds;
const candles=Array.from({length:180},(_,index)=>{
  const close=100+index*.04+Math.sin(index/6)*2;
  const open=close-Math.sin(index)*.6;
  return{time:lastTime-(179-index)*intervalSeconds,open,close,high:Math.max(open,close)+.8,low:Math.min(open,close)-.8,volume:100+index};
});
const profile={first_name:'Demo',language:'ru',deposit:300,risk_pct:1,leverage:10,margin:'cross',trial_left:5,trial_total:5,has_paid_access:false,subscription_price_usdt:'29.99',subscription_days:30};
const oldSignal={id:7,symbol:'SOL_USDT',side:'LONG',confidence:.8,price:101,entry:100,stop:95,tp1:105,tp2:110,created_at:new Date(Date.now()-200*intervalSeconds*1000).toISOString(),source:'scanner',timeframe:'4h',trade_status:'active',regime:'1d=up;4h=up;regime=trend'};
const signalTime=Math.floor(Date.parse(oldSignal.created_at)/1000/intervalSeconds)*intervalSeconds;
const historicalCandles=candles.map((candle,index)=>({...candle,time:signalTime+(index-119)*intervalSeconds}));

async function touch(cdp,type,points){
  await cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map(([x,y])=>({x:Math.round(x),y:Math.round(y)}))});
}
async function zoomState(page){
  return page.evaluate(()=>{
    const bundle=overviewChart;
    const zoom=bundle.chart.getOption().dataZoom[0];
    return{start:Number(zoom.start),end:Number(zoom.end),key:bundle.key};
  });
}

(async()=>{
  const browser=await chromium.launch({headless:true,channel:'chrome'});
  try{
    const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:2,hasTouch:true,isMobile:true});
    const page=await context.newPage();
    const errors=[];
    const marketRequests=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/api/**',async route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/api/me')return route.fulfill({json:profile});
      if(url.pathname==='/api/signals')return route.fulfill({json:[oldSignal]});
      if(url.pathname.startsWith('/api/market/')){
        marketRequests.push(url.pathname+url.search);
        if(url.searchParams.get('timeframe')==='15m')await new Promise(resolve=>setTimeout(resolve,350));
        return route.fulfill({json:url.searchParams.has('at')?historicalCandles:candles});
      }
      throw Error(`Unexpected API ${url.pathname}`);
    });
    await page.goto(origin);
    await page.waitForFunction(()=>overviewChart?.data?.length===180);
    assert.equal(await page.locator('#chart-zoom-in,#chart-zoom-out').count(),0);
    const bounds=await page.locator('#chart').boundingBox();
    const cdp=await context.newCDPSession(page);
    const centerX=bounds.x+bounds.width/2;
    const centerY=bounds.y+bounds.height/2;
    const before=await zoomState(page);

    await touch(cdp,'touchStart',[[centerX-35,centerY],[centerX+35,centerY]]);
    for(let step=1;step<=8;step++){
      await touch(cdp,'touchMove',[[centerX-35-step*8,centerY],[centerX+35+step*8,centerY]]);
      await page.waitForTimeout(20);
    }
    await touch(cdp,'touchEnd',[]);
    const pinched=await zoomState(page);
    assert.ok(pinched.end-pinched.start<before.end-before.start-2,'two-finger pinch must zoom in');

    await touch(cdp,'touchStart',[[centerX,centerY]]);
    for(let step=1;step<=8;step++){
      await touch(cdp,'touchMove',[[centerX+step*12,centerY]]);
      await page.waitForTimeout(20);
    }
    await touch(cdp,'touchEnd',[]);
    const moved=await zoomState(page);
    assert.ok(Math.abs(moved.start-pinched.start)>1,'one-finger drag must pan');

    await page.click('#refresh');
    await page.waitForFunction(()=>!document.querySelector('#chart-frame').classList.contains('loading'));
    const refreshed=await zoomState(page);
    assert.ok(Math.abs(refreshed.start-moved.start)<1,'refresh must preserve the viewport');
    assert.ok(Math.abs(refreshed.end-moved.end)<1,'refresh must preserve zoom');

    await page.click('#chart-expand');
    assert.equal(await page.locator('.chart-section.chart-expanded').count(),1);
    const expandedBounds=await page.locator('#chart').boundingBox();
    assert.ok(expandedBounds.height>bounds.height*1.5,'expanded chart must use the viewport');
    await page.click('#chart-expand');
    for(const timeframe of ['15m','1h','1d'])await page.click(`#overview-timeframe button[data-timeframe="${timeframe}"]`);
    await page.waitForFunction(()=>overviewChart?.key==='BTC_USDT:1d:latest');
    await page.waitForTimeout(400);
    assert.equal((await zoomState(page)).key,'BTC_USDT:1d:latest','late responses must not replace the selected timeframe');

    await page.click('[data-target=signals]');
    await page.locator('#signal-history [data-signal-id="7"]').click();
    await page.waitForFunction(()=>overviewChart?.key?.startsWith('SOL_USDT:4h:'));
    assert.ok(marketRequests.some(value=>value.includes('SOL_USDT?timeframe=4h&at=')),'old trade must load historical candles');
    assert.match(await page.locator('#chart-price').textContent(),/история/);
    assert.equal(await page.evaluate(()=>overviewChart.levels.length),4);
    const selectedBounds=await page.locator('#chart').boundingBox();
    const selectedX=selectedBounds.x+selectedBounds.width/2;
    const selectedY=selectedBounds.y+selectedBounds.height/2;
    const selectedBefore=await zoomState(page);
    await touch(cdp,'touchStart',[[selectedX-35,selectedY],[selectedX+35,selectedY]]);
    for(let step=1;step<=8;step++){
      await touch(cdp,'touchMove',[[selectedX-35-step*8,selectedY],[selectedX+35+step*8,selectedY]]);
      await page.waitForTimeout(20);
    }
    await touch(cdp,'touchEnd',[]);
    const selectedPinched=await zoomState(page);
    assert.ok(selectedPinched.end-selectedPinched.start<selectedBefore.end-selectedBefore.start-2,'selected trade chart must support pinch');

    oldSignal.entry=200;
    await page.goto(origin+'?signal_id=7');
    await page.waitForFunction(()=>overviewChart?.key?.startsWith('SOL_USDT:4h:'));
    await page.waitForFunction(()=>document.querySelector('#chart-regime').classList.contains('warning'));
    assert.equal(await page.evaluate(()=>overviewChart.levels.length),0,'mismatched levels must not flatten the candles');
    assert.match(await page.locator('#chart-regime').textContent(),/не совпадают/);
    for(const width of [320,390,768,1280]){
      await page.setViewportSize({width,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`no horizontal overflow at ${width}px`);
      await page.click('#chart-expand');
      const expanded=await page.locator('.chart-section.chart-expanded').boundingBox();
      assert.ok(expanded.x>=0&&expanded.x+expanded.width<=width+1,`expanded chart fits ${width}px`);
      await page.click('#chart-expand');
    }
    assert.deepEqual(errors,[]);
    console.log('PASS mobile pinch, drag, refresh viewport, expansion, timeframe race, selected historical trade, mismatch guard, 4 widths');
  }finally{
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
