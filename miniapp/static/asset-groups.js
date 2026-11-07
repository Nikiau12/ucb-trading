/* Shared group catalog. Python/server counterpart: miniapp/asset_groups.json.
 * tests/asset_groups.test.cjs verifies exact parity; unknown coins stay ungrouped. */
(() => {
  'use strict';
  const groups = [
    {id:'core_btc',symbols:'BTC',labels:{ru:'BTC',en:'BTC',de:'BTC',fr:'BTC',es:'BTC'}},
    {id:'core_eth',symbols:'ETH',labels:{ru:'ETH',en:'ETH',de:'ETH',fr:'ETH',es:'ETH'}},
    {id:'core_sol',symbols:'SOL',labels:{ru:'SOL',en:'SOL',de:'SOL',fr:'SOL',es:'SOL'}},
    {id:'l1',symbols:'ADA APT ARK BNB CFX DOT ETC HBAR ICP INJ IOST KAS SEI SUI XPL',labels:{ru:'Базовые сети L1/L0',en:'L1/L0 networks',de:'L1/L0-Netzwerke',fr:'Réseaux L1/L0',es:'Redes L1/L0'}},
    {id:'scaling',symbols:'ALT DYM MERL OP SOON STRK STX TIA',labels:{ru:'L2 и модульная инфраструктура',en:'L2 and modular infrastructure',de:'L2 und modulare Infrastruktur',fr:'L2 et infrastructure modulaire',es:'L2 e infraestructura modular'}},
    {id:'privacy',symbols:'XMR ZEC',labels:{ru:'Приватные платежи',en:'Privacy payments',de:'Private Zahlungen',fr:'Paiements confidentiels',es:'Pagos privados'}},
    {id:'payments',symbols:'DASH LTC XLM XRP',labels:{ru:'Платёжные сети',en:'Payment networks',de:'Zahlungsnetzwerke',fr:'Réseaux de paiement',es:'Redes de pago'}},
    {id:'defi',symbols:'AAVE APR BR CAP ENA EVAA FLUID JTO PENDLE',labels:{ru:'Кредитование, стейкинг и доходность DeFi',en:'DeFi lending, staking and yield',de:'DeFi-Kredite, Staking und Erträge',fr:'Prêts, staking et rendement DeFi',es:'Préstamos, staking y rendimiento DeFi'}},
    {id:'trading',symbols:'1INCH ASTER BANANA COW CRV HYPE ORDER PUMP RUNE UNI',labels:{ru:'DEX, торговые сервисы и launchpad',en:'DEX, trading services and launchpads',de:'DEX, Handelsdienste und Launchpads',fr:'DEX, trading et plateformes de lancement',es:'DEX, servicios de trading y launchpads'}},
    {id:'ai',symbols:'AGT ATH DNA FET JCT RENDER UAI',labels:{ru:'AI и вычисления',en:'AI and computing',de:'KI und Rechenleistung',fr:'IA et calcul',es:'IA y computación'}},
    {id:'data',symbols:'FIL HOT IRYS JASMY NIL WAL',labels:{ru:'Хранение данных и распределённые сервисы',en:'Data storage and distributed services',de:'Datenspeicherung und verteilte Dienste',fr:'Stockage de données et services distribués',es:'Almacenamiento de datos y servicios distribuidos'}},
    {id:'oracles',symbols:'LINK ON PYTH QNT TRB',labels:{ru:'Оракулы и межсетевая инфраструктура',en:'Oracles and cross-chain infrastructure',de:'Orakel und Cross-Chain-Infrastruktur',fr:'Oracles et infrastructure interchaînes',es:'Oráculos e infraestructura entre cadenas'}},
    {id:'meme',symbols:'1000BONK 1000PEPE BULLA DOGE FARTCOIN PENGU PONS WIF',labels:{ru:'Мемы и community-токены',en:'Memes and community tokens',de:'Memes und Community-Token',fr:'Memes et tokens communautaires',es:'Memes y tokens de comunidad'}},
    {id:'games',symbols:'AKE BEAM BEAT BLUR DOOD IDOL NOT',labels:{ru:'Игры, NFT и развлечения',en:'Gaming, NFTs and entertainment',de:'Gaming, NFTs und Unterhaltung',fr:'Jeux, NFT et divertissement',es:'Juegos, NFT y entretenimiento'}},
    {id:'apps',symbols:'AVA BAT BMT WLD',labels:{ru:'Пользовательские приложения и аналитика',en:'Consumer apps and analytics',de:'Nutzeranwendungen und Analysen',fr:'Applications grand public et analyse',es:'Aplicaciones de usuario y análisis'}},
    {id:'rwa',symbols:'XAUT',labels:{ru:'Токенизированное золото',en:'Tokenized gold',de:'Tokenisiertes Gold',fr:'Or tokenisé',es:'Oro tokenizado'}}
  ].map(group => Object.freeze({
    ...group,
    symbols:Object.freeze(group.symbols.split(' ').map(symbol => `${symbol}_USDT`)),
    labels:Object.freeze(group.labels)
  }));
  const byId = new Map(groups.map(group => [group.id,group]));
  const bySymbol = new Map();
  for(const group of groups)for(const symbol of group.symbols){
    if(bySymbol.has(symbol))throw new Error(`Duplicate asset group: ${symbol}`);
    bySymbol.set(symbol,group.id);
  }
  const ungrouped = Object.freeze({ru:'Без группы',en:'Ungrouped',de:'Ohne Gruppe',fr:'Sans groupe',es:'Sin grupo'});
  function classify(symbol,assetType='crypto'){
    if(assetType && assetType!=='crypto')return 'ungrouped';
    if(typeof symbol!=='string' || symbol.length>64)return 'ungrouped';
    const match=symbol.trim().toUpperCase().match(/^([A-Z0-9]+?)[_/-]?USDT(?::USDT)?$/);
    return match ? bySymbol.get(`${match[1]}_USDT`)||'ungrouped' : 'ungrouped';
  }
  function label(id,language='en'){
    const labels=byId.get(id)?.labels||ungrouped;
    return labels[language]||labels.en;
  }
  function matches(signal,group='ALL'){
    return group==='ALL'||classify(signal?.symbol,signal?.asset_type)===group;
  }
  window.AssetGroups=Object.freeze({version:'2026-11-07-v1',groups:Object.freeze(groups),classify,label,matches});
})();
