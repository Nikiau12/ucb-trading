/* Explicit instrument identity mapping; never load a user-supplied image URL. */
(()=>{
  const coins=Object.fromEntries('BTC ETH SOL XRP DOGE ADA BNB LTC LINK AVAX DOT TRX BCH ZEC UNI AAVE ATOM ETC XLM FIL ALGO VET ICP USDT USDC'.split(' ').map(symbol=>[symbol,symbol.toLowerCase()+'.svg']));
  const stocks={AAPL:'apple',NVDA:'nvidia',TSLA:'tesla',GOOG:'google',GOOGL:'google',META:'meta',NFLX:'netflix',COIN:'coinbase',INTC:'intel',AMD:'amd'};
  const bingxStocks={NCSKAAPL2USD:'AAPL',NCSKNVDA2USD:'NVDA',NCSKTSLA2USD:'TSLA',NCSKGOOGL2USD:'GOOGL',NCSKMETA2USD:'META',NCSKNFLX2USD:'NFLX',NCSKCOIN2USD:'COIN',NCSKINTC2USD:'INTC',NCSKAMD2USD:'AMD'};
  function base(symbol){
    const value=String(symbol||'').trim().toUpperCase();
    if(!/^(?:[A-Z0-9]{1,40}|[A-Z0-9]{1,35}(?:_|\/|-)USDT(?::USDT)?)$/.test(value))return '';
    const raw=value.split(':')[0];
    return raw.replace(/(?:_|\/|-)USDT$/,'').replace(/^([A-Z0-9]+)USDT$/,'$1');
  }
  function resolve(symbol,assetType='crypto'){
    const key=base(symbol);
    if(!/^[A-Z0-9]{1,40}$/.test(key))return null;
    const stock=Object.hasOwn(bingxStocks,key)?bingxStocks[key]:assetType==='stock'||assetType==='equity'?key:null;
    if(stock&&Object.hasOwn(stocks,stock))return '/static/icons/stock-'+stocks[stock]+'.svg';
    if(stock||assetType==='stock'||assetType==='equity')return null;
    return Object.hasOwn(coins,key)?'/static/icons/'+coins[key]:'/api/asset-icon/'+key;
  }
  window.AssetIcons=Object.freeze({base,resolve});
})();
