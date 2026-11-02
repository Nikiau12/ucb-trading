// Local-only browser regression: every market must own its price scale and levels.
// API responses are synthetic; no exchange, Telegram, database, or payment calls.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const origin=process.env.UI_TEST_URL||'http://127.0.0.1:8765';
assert.ok(['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Local server only');

const prices={BTC_USDT:68000,ETH_USDT:3500,SOL_USDT:160,LTC_USDT:80,XRP_USDT:2.5,HBAR_USDT:0.2,DOGE_USDT:0.15,SHIB_USDT:0.000012};
const interval=14400;
const end=Math.floor(Date.now()/1000/interval)*interval;
const candles=Object.fromEntries(Object.entries(prices).map(([symbol,base])=>[
  symbol,Array.from({length:180},(_,index)=>{
    const close=base*(1+Math.sin(index/8)*0.008+index*0.00003);
    const open=close*(1+Math.sin(index)*0.001);
    return{time:end-(179-index)*interval,open,close,high:Math.max(open,close)*1.002,low:Math.min(open,close)*0.998,volume:100+index};
  })
]));
const profile={first_name:'Demo',language:'ru',deposit:300,risk_pct:1,leverage:10,margin:'cross',trial_left:5,trial_total:5,has_paid_access:false,subscription_price_usdt:'29.99',subscription_days:30};
const signals=Object.entries(prices).map(([symbol,price],index)=>({
  id:index+1,symbol,side:'LONG',confidence:0.8,price,entry:price,stop:price*0.97,
  tp1:price*1.03,tp2:price*1.06,created_at:new Date().toISOString(),
  source:'scanner',timeframe:'4h',trade_status:'active',regime:'1d=up;4h=up;regime=trend'
}));

(async()=>{
  const browser=await chromium.launch({headless:true,channel:'chrome'});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2});
    const errors=[];
    let delayEth=false;
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/api/**',async route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/api/me')return route.fulfill({json:profile});
      if(url.pathname==='/api/signals')return route.fulfill({json:signals});
      if(url.pathname.startsWith('/api/asset-icon/'))return route.fulfill({status:404,body:''});
      const symbol=url.pathname.match(/^\/api\/market\/([A-Z0-9_]+)$/)?.[1];
      if(symbol&&candles[symbol]){
        if(symbol==='ETH_USDT'&&delayEth)await new Promise(resolve=>setTimeout(resolve,300));
        return route.fulfill({json:candles[symbol]});
      }
      throw Error(`Unexpected API ${url.pathname}`);
    });
    await page.goto(origin);
    await page.waitForFunction(()=>overviewChart?.key==='BTC_USDT:4h:latest');
    let manuallyScaled=false;
    for(const symbol of ['ETH_USDT','BTC_USDT','SOL_USDT','LTC_USDT','XRP_USDT','HBAR_USDT','DOGE_USDT','SHIB_USDT','ETH_USDT','BTC_USDT']){
      const id=signals.find(signal=>signal.symbol===symbol).id;
      await page.click('[data-target=signals]');
      await page.locator(`#signal-history [data-signal-id="${id}"]`).click();
      await page.waitForFunction(expected=>overviewChart?.key===`${expected}:4h:latest`,symbol);
      const chart=await page.evaluate(()=>{
        const last=overviewChart.data.at(-1).close;
        return{
          key:overviewChart.key,
          last,
          coordinate:overviewChart.candles.priceToCoordinate(last),
          height:overviewChart.container.clientHeight,
          precision:overviewChart.candles.options().priceFormat?.precision,
          levels:overviewChart.levels.map(level=>level.price),
          title:document.querySelector('#chart-title').textContent,
          readout:document.querySelector('#chart-price').textContent
        };
      });
      assert.ok(Math.abs(chart.last-prices[symbol])/prices[symbol]<0.03,`${symbol}: wrong candles`);
      assert.ok(chart.coordinate>=0&&chart.coordinate<=chart.height,`${symbol}: price scale belongs to prior market: ${JSON.stringify(chart)}`);
      assert.ok(chart.levels.every(level=>Math.abs(level/prices[symbol]-1)<0.1),`${symbol}: stale trade levels`);
      assert.ok(chart.title.includes(symbol.split('_')[0]),`${symbol}: stale title`);
      const expectedPrecision=Math.max(2,Math.min(12,Math.ceil(-Math.log10(prices[symbol]))+3));
      assert.equal(chart.precision,expectedPrecision,`${symbol}: wrong price precision`);
      if(symbol==='BTC_USDT'&&manuallyScaled&&process.env.UI_SCREENSHOT_DIR){
        fs.mkdirSync(process.env.UI_SCREENSHOT_DIR,{recursive:true});
        await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'btc-after-eth.png')});
      }
      if(symbol==='ETH_USDT'&&!manuallyScaled){
        await page.evaluate(()=>overviewChart.chart.priceScale('right').applyOptions({autoScale:false}));
        manuallyScaled=true;
      }
    }
    delayEth=true;
    await page.click('[data-target=signals]');
    await page.locator('#signal-history [data-signal-id="2"]').click();
    await page.click('[data-target=signals]');
    await page.locator('#signal-history [data-signal-id="1"]').click();
    await page.waitForFunction(()=>overviewChart?.key==='BTC_USDT:4h:latest');
    await page.waitForTimeout(350);
    assert.equal(await page.evaluate(()=>overviewChart.key),'BTC_USDT:4h:latest','late ETH response must not replace BTC');
    assert.ok((await page.evaluate(()=>overviewChart.candles.priceToCoordinate(overviewChart.data.at(-1).close)))>=0);
    assert.deepEqual(errors,[]);
    console.log('PASS 8 markets from BTC to SHIB keep prices, axis, levels and labels isolated; late ETH cannot replace BTC');
  }finally{
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
