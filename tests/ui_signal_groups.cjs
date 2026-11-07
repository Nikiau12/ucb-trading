// Local-only fixtures: no real users, payments, notifications or exchange calls.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const origin=process.env.UI_TEST_URL||'http://127.0.0.1:8765';
assert.ok(['127.0.0.1','localhost'].includes(new URL(origin).hostname),'Local server only');
const context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root,'miniapp/static/asset-groups.js'),'utf8'),context);
const catalog=context.window.AssetGroups;
const profile={first_name:'Demo',language:'ru',deposit:300,risk_pct:1,leverage:10,margin:'cross',trial_left:5,trial_total:5,has_paid_access:false};
const symbols=[...Array.from(catalog.groups).flatMap(group=>Array.from(group.symbols)),'UNCLASSIFIED_USDT'];
const initialSignals=symbols.map((symbol,index)=>({id:100+index,symbol,side:index%2?'SHORT':'LONG',source:['scanner','spike','smc','listing'][index%4],entry:100,price:100,stop:97,tp1:103,tp2:106,confidence:0.8,timeframe:'4h',trade_status:'active',created_at:new Date().toISOString()}));
let feed=initialSignals;
const typeMatches=(signal,type)=>type==='ALL'||signal.side===type||(type==='SETUP'&&signal.source==='scanner')||(type==='SCALP'&&signal.source==='spike')||signal.source===type.toLowerCase();
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'chrome'});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844}});
    const errors=[],writes=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/api/**',route=>{
      const request=route.request(),url=new URL(request.url());
      if(request.method()!=='GET')writes.push(url.pathname);
      if(url.pathname==='/api/me')return route.fulfill({json:profile});
      if(url.pathname==='/api/signals')return route.fulfill({json:feed});
      if(url.pathname==='/api/settings'){
        Object.assign(profile,request.postDataJSON());
        return route.fulfill({json:profile});
      }
      if(url.pathname.startsWith('/api/market/'))return route.fulfill({json:[]});
      if(url.pathname.startsWith('/api/asset-icon/'))return route.fulfill({status:404,body:''});
      throw Error(`Unexpected request: ${request.method()} ${url.pathname}`);
    });
    await page.goto(origin);
    await page.waitForFunction(()=>document.querySelectorAll('#signal-history .signal-row').length===90);
    await page.click('[data-target=signals]');
    assert.equal(await page.locator('#signal-group option').count(),18);
    assert.equal(await page.locator('#reset-signal-filters').isVisible(),false);
    for(const group of [...Array.from(catalog.groups,group=>group.id),'ungrouped']){
      await page.selectOption('#signal-group',group);
      for(const type of ['ALL','SETUP','SCALP','SMC','LISTING','LONG','SHORT']){
        await page.click(`[data-filter="${type}"]`);
        const expected=feed.filter(signal=>catalog.matches(signal,group)&&typeMatches(signal,type)).map(signal=>signal.id);
        const actual=await page.locator('#signal-history .signal-row').evaluateAll(rows=>rows.map(row=>Number(row.dataset.signalId)));
        assert.deepEqual(actual,expected,`${group} + ${type}`);
        assert.match(await page.locator('#signal-filter-count').textContent(),new RegExp(`Показано ${expected.length} из 90`));
        assert.equal(await page.locator(`[data-filter="${type}"]`).getAttribute('aria-pressed'),'true');
      }
    }
    assert.deepEqual(writes,[],'filtering must not write settings or change notifications');
    await page.click('#reset-signal-filters');
    assert.equal(await page.locator('#signal-group').inputValue(),'ALL');
    assert.equal(await page.locator('#signal-history .signal-row').count(),90);
    assert.equal(await page.locator('#reset-signal-filters').isVisible(),false);
    await page.selectOption('#signal-group','defi');
    await page.click('[data-filter=LONG]');
    const before=await page.locator('#signal-history .signal-row').count();
    const first=page.locator('#signal-history .signal-row').first();
    const id=await first.getAttribute('data-signal-id');
    const symbol=initialSignals.find(signal=>String(signal.id)===id).symbol;
    await first.click();
    assert.ok((await page.locator('#chart-title').textContent()).includes(symbol.split('_')[0]));
    await page.click('[data-target=signals]');
    assert.equal(await page.locator('#signal-group').inputValue(),'defi');
    assert.equal(await page.locator('#signal-history .signal-row').count(),before);
    await page.evaluate(()=>refreshLiveData());
    assert.equal(await page.locator('#signal-group').inputValue(),'defi');
    assert.equal(await page.locator('#signal-history .signal-row').count(),before);
    for(const lang of ['en','ru','de','fr','es']){
      await page.click('[data-target=settings]');
      await page.selectOption('#language',lang);
      await page.waitForFunction(value=>document.documentElement.lang===value,lang);
      await page.click('[data-target=signals]');
      assert.equal(await page.locator('#signal-group').inputValue(),'defi');
      assert.equal(await page.locator('#signal-group option:checked').textContent(),catalog.label('defi',lang));
      assert.equal(await page.locator('.signal-group-badge').first().textContent(),catalog.label('defi',lang));
      for(const [width,height] of [[320,640],[390,844],[844,390],[1280,800]]){
        await page.setViewportSize({width,height});
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${lang} ${width}: overflow`);
        assert.equal(await page.locator('#signal-group').evaluate(node=>node.getBoundingClientRect().right<=innerWidth),true);
        assert.equal(await page.locator('.signal-group-badge').first().evaluate(node=>node.scrollWidth<=node.clientWidth+1),true,`${lang}: clipped badge`);
        assert.ok(await page.locator('.signal-group-badge').first().evaluate(node=>node.getBoundingClientRect().height<=54),`${lang}: group label must stay compact`);
      }
    }
    await page.click('[data-target=settings]');
    await page.selectOption('#language','ru');
    await page.click('[data-target=signals]');
    await page.click('#reset-signal-filters');
    if(process.env.UI_SCREENSHOT_DIR){
      fs.mkdirSync(process.env.UI_SCREENSHOT_DIR,{recursive:true});
      for(const [name,width,height] of [['groups-mobile',390,844],['groups-desktop',1280,800]]){
        await page.setViewportSize({width,height});
        await page.evaluate(()=>window.scrollTo(0,0));
        await page.waitForTimeout(250);
        await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,`${name}.png`)});
      }
      await page.setViewportSize({width:320,height:640});
      await page.selectOption('#signal-group','defi');
      await page.waitForTimeout(250);
      await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'groups-defi-narrow.png')});
      await page.evaluate(()=>window.scrollTo(0,window.scrollY+document.querySelector('#signal-history .signal-row').getBoundingClientRect().top-90));
      await page.waitForTimeout(250);
      await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'groups-defi-card-narrow.png')});
    }
    feed=[];
    await page.evaluate(()=>refreshLiveData());
    assert.equal(await page.locator('#signal-history .signal-row').count(),0);
    assert.match(await page.locator('#signal-history').textContent(),/По выбранным фильтрам сигналов нет/);
    await page.click('#reset-signal-filters');
    assert.match(await page.locator('#signal-history').textContent(),/Сканер молчал/);
    assert.equal(await page.locator('#signal-history [data-empty-action]').count(),1);
    feed=[initialSignals[0]];
    await page.selectOption('#signal-group','privacy');
    await page.evaluate(()=>refreshLiveData());
    assert.equal(await page.locator('#signal-history .signal-row').count(),0);
    feed.push(initialSignals.find(signal=>signal.symbol==='ZEC_USDT'));
    await page.evaluate(()=>refreshLiveData());
    assert.equal(await page.locator('#signal-history .signal-row').count(),1,'new matching signal appears without clearing the group');
    assert.deepEqual(errors,[]);
    assert.ok(writes.every(url=>url==='/api/settings'));
    console.log('PASS 89 contracts, 17 group choices x 7 existing filters, reset, details, refresh, empty states, 5 languages and 4 viewport sizes');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
