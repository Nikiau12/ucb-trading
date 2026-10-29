const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root,'miniapp/static/asset-icons.js'),'utf8'),context);
const icons=context.window.AssetIcons;
test('exchange symbol formats resolve to the same local icon',()=>{
  for(const symbol of ['BTC_USDT','BTC-USDT','BTC/USDT:USDT','BTCUSDT',' btc '])assert.equal(icons.resolve(symbol),'/static/icons/btc.svg');
  assert.equal(icons.resolve('ETH_USDT'),'/static/icons/eth.svg');
  assert.equal(icons.resolve('SOL_USDT'),'/static/icons/sol.svg');
});
test('stock identities are explicit, not guessed from crypto tickers',()=>{
  assert.equal(icons.resolve('META_USDT'),'/api/asset-icon/META');
  assert.equal(icons.resolve('META','stock'),'/static/icons/stock-meta.svg');
  assert.equal(icons.resolve('NCSKNVDA2USD_USDT'),'/static/icons/stock-nvidia.svg');
  assert.equal(icons.resolve('BTC','stock'),null);
});
test('valid crypto symbols use the same-origin BingX icon proxy',()=>{
  assert.equal(icons.resolve('SUI_USDT'),'/api/asset-icon/SUI');
  assert.equal(icons.resolve('1000BONK_USDT'),'/api/asset-icon/1000BONK');
  assert.equal(icons.resolve('UNKNOWN_USDT'),'/api/asset-icon/UNKNOWN');
});
test('hostile symbols fall back without creating an image request',()=>{
  for(const value of ['../../btc','<img src=x>','https://example.com','__proto__',''])assert.equal(icons.resolve(value),null);
});
test('all catalog paths exist',()=>{
  for(const symbol of 'BTC ETH SOL XRP DOGE ADA BNB LTC LINK AVAX DOT TRX BCH ZEC UNI AAVE ATOM ETC XLM FIL ALGO VET ICP USDT USDC'.split(' '))assert.ok(fs.existsSync(path.join(root,'miniapp',icons.resolve(symbol))));
  for(const symbol of 'AAPL NVDA TSLA GOOG GOOGL META NFLX COIN INTC AMD'.split(' '))assert.ok(fs.existsSync(path.join(root,'miniapp',icons.resolve(symbol,'stock'))));
});
