const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root,'miniapp/static/asset-groups.js'),'utf8'),context);
const catalog=context.window.AssetGroups;

test('the display snapshot retains 16 groups and 89 unique contracts',()=>{
  assert.equal(catalog.version,'2026-11-07-v1');
  assert.equal(catalog.groups.length,16);
  assert.deepEqual(Array.from(catalog.groups.slice(0,3),group=>group.id),['core_btc','core_eth','core_sol']);
  const symbols=Array.from(catalog.groups).flatMap(group=>Array.from(group.symbols));
  assert.equal(symbols.length,89);
  assert.equal(new Set(symbols).size,89);
  for(const group of catalog.groups)for(const symbol of group.symbols)assert.equal(catalog.classify(symbol),group.id);
});
test('supported exchange formats normalize without losing contract units',()=>{
  for(const symbol of ['BTC_USDT','BTC-USDT','BTC/USDT:USDT','BTCUSDT',' btc_usdt '])assert.equal(catalog.classify(symbol),'core_btc');
  assert.equal(catalog.classify('1000PEPE_USDT'),'meme');
  assert.equal(catalog.classify('1000BONK-USDT'),'meme');
  assert.equal(catalog.classify('PEPE_USDT'),'ungrouped');
  assert.equal(catalog.classify('BONK_USDT'),'ungrouped');
  assert.equal(catalog.classify('BTC_USDC'),'ungrouped');
});
test('approved primary groups are not replaced by secondary tags',()=>{
  for(const [symbol,group] of Object.entries({INJ_USDT:'l1',TIA_USDT:'scaling',BEAM_USDT:'games',PENGU_USDT:'meme',UNI_USDT:'trading',XAUT_USDT:'rwa'}))assert.equal(catalog.classify(symbol),group);
});
test('unknown and hostile tickers stay ungrouped without heuristic matches',()=>{
  for(const symbol of [null,undefined,42,{},'', '__proto__','<img src=x onerror=alert(1)>','https://BTC_USDT','BTC_USDT_PERP','NEWCOIN_USDT','AAPL_USDT'])assert.equal(catalog.classify(symbol),'ungrouped');
  assert.equal(catalog.classify('BTC_USDT','stock'),'ungrouped');
  assert.equal(catalog.matches({symbol:'NEWCOIN_USDT'},'ALL'),true);
  assert.equal(catalog.matches({symbol:'NEWCOIN_USDT'},'ungrouped'),true);
  assert.equal(catalog.matches({symbol:'NEWCOIN_USDT'},'meme'),false);
  assert.equal(catalog.matches({symbol:'BTC_USDT'},'__proto__'),false);
});
test('every group and fallback has all five app languages',()=>{
  for(const group of [...catalog.groups,{id:'ungrouped'}])for(const lang of ['en','ru','de','fr','es']){
    const label=catalog.label(group.id,lang);
    assert.equal(typeof label,'string');
    assert.ok(label.length>0);
    assert.ok(!label.includes('<'));
  }
  assert.equal(catalog.label('missing','ru'),'Без группы');
  assert.equal(catalog.label('meme','unknown'),catalog.label('meme','en'));
});
test('filtering does not mutate signals, levels, order or the catalog',()=>{
  const signals=Object.freeze([Object.freeze({id:1,symbol:'AAVE_USDT',entry:100,stop:95}),Object.freeze({id:2,symbol:'BTC_USDT'}),Object.freeze({id:3,symbol:'ENA_USDT'})]);
  assert.deepEqual(signals.filter(signal=>catalog.matches(signal,'defi')).map(signal=>signal.id),[1,3]);
  assert.equal(signals[0].entry,100);
  assert.equal(signals[0].stop,95);
  assert.ok(Object.isFrozen(catalog));
  assert.ok(Object.isFrozen(catalog.groups));
  assert.ok(catalog.groups.every(group=>Object.isFrozen(group)&&Object.isFrozen(group.symbols)&&Object.isFrozen(group.labels)));
});
test('display catalog is loaded before the app and new assets are versioned',()=>{
  const html=fs.readFileSync(path.join(root,'miniapp/static/index.html'),'utf8');
  assert.ok(html.indexOf('/static/asset-groups.js?')<html.indexOf('/static/app.js?'));
  assert.match(html,/id="signal-group"/);
  assert.match(html,/id="reset-signal-filters"/);
  assert.match(html,/id="signal-filter-count" role="status"/);
  assert.match(html,/home-dark.css\?v=20261107-signal-groups-1/);
});
