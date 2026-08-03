const tg = window.Telegram?.WebApp;
tg?.ready(); tg?.expand();

const translations = {
  en:{workspace:'PRIVATE WORKSPACE',hello:'Hello',marketLive:'MEXC LIVE',deposit:'Deposit',riskTrade:'Risk / trade',leverage:'Leverage',access:'Access',cross:'Cross',isolated:'Isolated',scanner:'MARKET SCANNER',latestSignals:'Latest signals',viewAll:'View all',signalHistory:'Signal history',all:'All',riskProfile:'RISK PROFILE',settings:'Settings',depositUsdt:'Deposit, USDT',riskPercent:'Risk per trade, %',leverageX:'Leverage',marginMode:'Margin mode',saveSettings:'Save settings',subscription:'SUBSCRIPTION',monthlyAccess:'Monthly access',subscriptionCopy:'Automatic signals, scanner and full position plans.',paymentInstructions:'Payment instructions',overview:'Overview',signals:'Signals',trial:'Trial',signalsLeft:'signals left',active:'Active',inactive:'Inactive',entry:'Entry',stop:'Stop',confidence:'Confidence',saved:'Settings saved',paymentHelp:'Opening payment instructions in the bot...',paymentUnavailable:'Could not open the bot. Close the app and send /subscribe.',noSignals:'No signals yet',currentPrice:'Current price',tp1:'TP1',tp2:'TP2',positionSize:'Position size',marginRequired:'Required margin',stopRisk:'Stop risk',backToSignals:'Back to signals',tradeSetup:'TRADE SETUP',livePrice:'LIVE PRICE',signalLevels:'SIGNAL LEVELS',executionPlan:'Execution plan',personalSizing:'PERSONAL SIZING',positionPlan:'Position plan',trialComplete:'Free trial completed',trialCompleteCopy:'You used 5 free signals. Subscribe to continue receiving new setups.',unlockSignals:'Unlock signals'},
  ru:{workspace:'ЛИЧНЫЙ КАБИНЕТ',hello:'Привет',marketLive:'MEXC ОНЛАЙН',deposit:'Депозит',riskTrade:'Риск / сделку',leverage:'Плечо',access:'Доступ',cross:'Кросс',isolated:'Изолированная',scanner:'СКАНЕР РЫНКА',latestSignals:'Последние сигналы',viewAll:'Все сигналы',signalHistory:'История сигналов',all:'Все',riskProfile:'РИСК-ПРОФИЛЬ',settings:'Настройки',depositUsdt:'Депозит, USDT',riskPercent:'Риск на сделку, %',leverageX:'Кредитное плечо',marginMode:'Режим маржи',saveSettings:'Сохранить',subscription:'ПОДПИСКА',monthlyAccess:'Месячный доступ',subscriptionCopy:'Автосигналы, сканер и полные торговые планы.',paymentInstructions:'Инструкция по оплате',overview:'Обзор',signals:'Сигналы',trial:'Пробный доступ',signalsLeft:'сигналов осталось',active:'Активна',inactive:'Неактивна',entry:'Вход',stop:'Стоп',confidence:'Уверенность',saved:'Настройки сохранены',paymentHelp:'Открываю инструкцию по оплате в боте...',paymentUnavailable:'Не удалось открыть бота. Закрой приложение и отправь /subscribe.',noSignals:'Сигналов пока нет',currentPrice:'Цена сейчас',tp1:'TP1',tp2:'TP2',positionSize:'Объём позиции',marginRequired:'Нужно маржи',stopRisk:'Риск по стопу',backToSignals:'Назад к сигналам',tradeSetup:'ТОРГОВЫЙ СЕТАП',livePrice:'ЦЕНА ОНЛАЙН',signalLevels:'УРОВНИ СИГНАЛА',executionPlan:'План исполнения',personalSizing:'ПЕРСОНАЛЬНЫЙ РАСЧЁТ',positionPlan:'План позиции',trialComplete:'Пробный доступ завершён',trialCompleteCopy:'Ты использовал 5 бесплатных сигналов. Оформи подписку, чтобы получать новые сетапы.',unlockSignals:'Открыть доступ'},
  de:{workspace:'PRIVATER ARBEITSBEREICH',hello:'Hallo',marketLive:'MEXC LIVE',deposit:'Kapital',riskTrade:'Risiko / Trade',leverage:'Hebel',access:'Zugang',cross:'Cross',isolated:'Isoliert',scanner:'MARKTSCANNER',latestSignals:'Neueste Signale',viewAll:'Alle anzeigen',signalHistory:'Signalverlauf',all:'Alle',riskProfile:'RISIKOPROFIL',settings:'Einstellungen',depositUsdt:'Kapital, USDT',riskPercent:'Risiko pro Trade, %',leverageX:'Hebel',marginMode:'Margin-Modus',saveSettings:'Speichern',subscription:'ABONNEMENT',monthlyAccess:'Monatlicher Zugang',subscriptionCopy:'Automatische Signale, Scanner und vollständige Pläne.',paymentInstructions:'Zahlungsanleitung',overview:'Übersicht',signals:'Signale',trial:'Testzugang',signalsLeft:'Signale übrig',active:'Aktiv',inactive:'Inaktiv',entry:'Einstieg',stop:'Stop',confidence:'Konfidenz',saved:'Einstellungen gespeichert',paymentHelp:'Zahlungsanleitung wird im Bot geöffnet...',paymentUnavailable:'Der Bot konnte nicht geöffnet werden. Schließe die App und sende /subscribe.',noSignals:'Noch keine Signale',currentPrice:'Aktueller Preis',tp1:'TP1',tp2:'TP2',positionSize:'Positionsgröße',marginRequired:'Benötigte Margin',stopRisk:'Stop-Risiko',backToSignals:'Zurück zu Signalen',tradeSetup:'TRADE-SETUP',livePrice:'LIVE-PREIS',signalLevels:'SIGNALNIVEAUS',executionPlan:'Ausführungsplan',personalSizing:'PERSÖNLICHE GRÖSSE',positionPlan:'Positionsplan',trialComplete:'Testphase beendet',trialCompleteCopy:'Du hast 5 kostenlose Signale genutzt. Abonniere, um neue Setups zu erhalten.',unlockSignals:'Signale freischalten'},
  fr:{workspace:'ESPACE PRIVÉ',hello:'Bonjour',marketLive:'MEXC EN DIRECT',deposit:'Dépôt',riskTrade:'Risque / trade',leverage:'Levier',access:'Accès',cross:'Cross',isolated:'Isolée',scanner:'SCANNER DU MARCHÉ',latestSignals:'Derniers signaux',viewAll:'Tout voir',signalHistory:'Historique des signaux',all:'Tous',riskProfile:'PROFIL DE RISQUE',settings:'Paramètres',depositUsdt:'Dépôt, USDT',riskPercent:'Risque par trade, %',leverageX:'Levier',marginMode:'Mode de marge',saveSettings:'Enregistrer',subscription:'ABONNEMENT',monthlyAccess:'Accès mensuel',subscriptionCopy:'Signaux automatiques, scanner et plans complets.',paymentInstructions:'Instructions de paiement',overview:'Aperçu',signals:'Signaux',trial:'Essai',signalsLeft:'signaux restants',active:'Actif',inactive:'Inactif',entry:'Entrée',stop:'Stop',confidence:'Confiance',saved:'Paramètres enregistrés',paymentHelp:'Ouverture des instructions de paiement dans le bot...',paymentUnavailable:'Impossible d\'ouvrir le bot. Ferme l\'application et envoie /subscribe.',noSignals:'Aucun signal',currentPrice:'Prix actuel',tp1:'TP1',tp2:'TP2',positionSize:'Taille de position',marginRequired:'Marge requise',stopRisk:'Risque au stop',backToSignals:'Retour aux signaux',tradeSetup:'CONFIGURATION',livePrice:'PRIX EN DIRECT',signalLevels:'NIVEAUX DU SIGNAL',executionPlan:'Plan d\'exécution',personalSizing:'TAILLE PERSONNELLE',positionPlan:'Plan de position',trialComplete:'Essai terminé',trialCompleteCopy:'Tu as utilisé 5 signaux gratuits. Abonne-toi pour continuer à recevoir de nouveaux setups.',unlockSignals:'Débloquer les signaux'},
  es:{workspace:'ESPACIO PRIVADO',hello:'Hola',marketLive:'MEXC EN VIVO',deposit:'Depósito',riskTrade:'Riesgo / operación',leverage:'Apalancamiento',access:'Acceso',cross:'Cruzado',isolated:'Aislado',scanner:'ESCÁNER DE MERCADO',latestSignals:'Últimas señales',viewAll:'Ver todas',signalHistory:'Historial de señales',all:'Todas',riskProfile:'PERFIL DE RIESGO',settings:'Ajustes',depositUsdt:'Depósito, USDT',riskPercent:'Riesgo por operación, %',leverageX:'Apalancamiento',marginMode:'Modo de margen',saveSettings:'Guardar',subscription:'SUSCRIPCIÓN',monthlyAccess:'Acceso mensual',subscriptionCopy:'Señales automáticas, escáner y planes completos.',paymentInstructions:'Instrucciones de pago',overview:'Resumen',signals:'Señales',trial:'Prueba',signalsLeft:'señales restantes',active:'Activo',inactive:'Inactivo',entry:'Entrada',stop:'Stop',confidence:'Confianza',saved:'Ajustes guardados',paymentHelp:'Abriendo las instrucciones de pago en el bot...',paymentUnavailable:'No se pudo abrir el bot. Cierra la aplicación y envía /subscribe.',noSignals:'Aún no hay señales',currentPrice:'Precio actual',tp1:'TP1',tp2:'TP2',positionSize:'Tamaño de posición',marginRequired:'Margen necesario',stopRisk:'Riesgo al stop',backToSignals:'Volver a señales',tradeSetup:'CONFIGURACIÓN',livePrice:'PRECIO EN VIVO',signalLevels:'NIVELES DE SEÑAL',executionPlan:'Plan de ejecución',personalSizing:'TAMAÑO PERSONAL',positionPlan:'Plan de posición',trialComplete:'Prueba finalizada',trialCompleteCopy:'Has usado 5 señales gratis. Suscríbete para seguir recibiendo nuevos setups.',unlockSignals:'Desbloquear señales'}
};

const taglines={
  en:'Setups, risk and execution — one screen.',
  ru:'Сетапы, риск и исполнение — на одном экране.',
  de:'Setups, Risiko und Ausführung — auf einem Bildschirm.',
  fr:'Setups, risque et exécution — sur un seul écran.',
  es:'Setups, riesgo y ejecución — en una sola pantalla.'
};

let profile=null,signals=[],language='en',activeFilter='ALL',selectedSignal=null;
let overviewSymbol='BTC_USDT',overviewTimeframe='1h',detailTimeframe='1h';
let overviewChart=null,detailChart=null;
const initData=tg?.initData||'';
const headers={'Content-Type':'application/json','X-Telegram-Init-Data':initData};
const $=selector=>document.querySelector(selector);
const tr=key=>key==='tagline'?(taglines[language]||taglines.en):(translations[language]?.[key]||translations.en[key]||key);
const fmt=value=>value==null||!Number.isFinite(Number(value))?'—':Number(value).toLocaleString(language,{maximumFractionDigits:Math.abs(Number(value))<1?8:2});
const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const clamp=(value,min,max)=>Math.min(Math.max(Number(value)||0,min),max);
const displaySymbol=symbol=>String(symbol||'').replace('_',' / ');
const isUsdtPair=symbol=>String(symbol||'').toUpperCase().split(':',1)[0].replace(/[/-]/g,'_').endsWith('_USDT');
const coinBase=symbol=>String(symbol||'').toUpperCase().split('_',1)[0].replace(/[^A-Z0-9]/g,'').slice(0,16);
const coinIconUrl=symbol=>`https://assets.coincap.io/assets/icons/${coinBase(symbol).toLowerCase()}@2x.png`;

function coinIconMarkup(symbol){
  const base=coinBase(symbol);
  return `<span class="coin-fallback">${escapeHtml(base.slice(0,2))}</span><img src="${escapeHtml(coinIconUrl(symbol))}" alt="${escapeHtml(base)}" loading="lazy">`;
}

function hydrateCoinIcons(scope=document){
  scope.querySelectorAll('.coin-dot img').forEach(image=>{
    const avatar=image.closest('.coin-dot');
    const markLoaded=()=>avatar.classList.remove('no-image');
    const markMissing=()=>avatar.classList.add('no-image');
    image.addEventListener('load',markLoaded,{once:true});
    image.addEventListener('error',markMissing,{once:true});
    if(image.complete)(image.naturalWidth?markLoaded:markMissing)();
  });
}

function applyLanguage(){
  document.documentElement.lang=language;
  document.querySelectorAll('[data-i18n]').forEach(element=>element.textContent=tr(element.dataset.i18n));
  $('#language').value=language;
  renderProfile();
  renderSignals();
  if(selectedSignal)renderSignalDetail(selectedSignal);
  lucide.createIcons();
}

function renderProfile(){
  if(!profile)return;
  $('#first-name').textContent=profile.first_name||'Trader';
  $('#deposit-metric').textContent=fmt(profile.deposit);
  $('#risk-metric').textContent=fmt(profile.risk_pct);
  $('#leverage-metric').textContent=`x${fmt(profile.leverage)}`;
  $('#deposit-input').value=profile.deposit??'';
  $('#risk-input').value=profile.risk_pct;
  $('#leverage-input').value=profile.leverage;
  const margin=profile.margin==='isolated'?'isolated':'cross';
  document.querySelector(`input[name=margin][value="${margin}"]`).checked=true;
  const paid=Boolean(profile.has_paid_access)||(profile.paid_until&&new Date(profile.paid_until)>new Date());
  const paywalled=!paid&&Number(profile.trial_left)<=0;
  $('#access-metric').textContent=paid?tr('active'):paywalled?tr('inactive'):tr('trial');
  $('#access-detail').textContent=paid?new Date(profile.paid_until).toLocaleDateString(language):`${profile.trial_left} ${tr('signalsLeft')}`;
  document.querySelectorAll('.trial-paywall').forEach(element=>element.hidden=!paywalled);
}

function signalMetrics(signal){
  const deposit=Number(profile?.deposit||0);
  const riskPct=Number(profile?.risk_pct||0);
  const leverage=Math.max(Number(profile?.leverage||1),1);
  const entry=Number(signal.entry);
  const stop=Number(signal.stop);
  const distance=Math.abs(entry-stop);
  const riskUsdt=deposit*riskPct/100;
  const position=distance?riskUsdt/distance*entry:0;
  return{riskUsdt,position,margin:position/leverage,stopPct:entry?distance/entry*100:0,leverage};
}

function signalCard(signal){
  const requestedSide=String(signal.side||'').toUpperCase();
  const side=requestedSide==='SHORT'?'SHORT':'LONG';
  const date=new Date(signal.created_at);
  const metrics=signalMetrics(signal);
  const confidence=clamp(signal.confidence,0,1);
  const signalId=Number.isSafeInteger(Number(signal.id))?Number(signal.id):0;
  const symbol=escapeHtml(displaySymbol(signal.symbol));
  const timestamp=escapeHtml(Number.isNaN(date.valueOf())?'—':date.toLocaleString(language,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}));
  return `<button type="button" class="signal-card" data-signal-id="${signalId}" data-side="${side}" aria-label="${symbol} ${side}"><header><div class="signal-symbol"><span class="coin-dot">${coinIconMarkup(signal.symbol)}</span><div><strong>${symbol}</strong><small>${timestamp}</small></div></div><span class="side ${side.toLowerCase()}">${side}</span><div class="signal-confidence"><span>${escapeHtml(tr('confidence'))}</span><b>${Math.round(confidence*100)}%</b></div></header><div class="trade-levels"><div><span>${escapeHtml(tr('currentPrice'))}</span><b>${fmt(signal.price)}</b></div><div><span>${escapeHtml(tr('entry'))}</span><b>${fmt(signal.entry)}</b></div><div><span>${escapeHtml(tr('stop'))}</span><b>${fmt(signal.stop)}</b><small>${metrics.stopPct.toFixed(1)}%</small></div><div><span>${escapeHtml(tr('tp1'))}</span><b>${fmt(signal.tp1)}</b></div><div><span>${escapeHtml(tr('tp2'))}</span><b>${fmt(signal.tp2)}</b></div></div><div class="position-plan"><div><span>${escapeHtml(tr('deposit'))}</span><b>${fmt(profile?.deposit)} USDT</b></div><div><span>${escapeHtml(tr('positionSize'))}</span><b>${fmt(metrics.position)} USDT</b></div><div><span>${escapeHtml(tr('marginRequired'))} x${fmt(metrics.leverage)}</span><b>${fmt(metrics.margin)} USDT</b></div><div><span>${escapeHtml(tr('stopRisk'))} (${fmt(profile?.risk_pct)}%)</span><b>${fmt(metrics.riskUsdt)} USDT</b></div></div><div class="confidence"><i style="width:${confidence*100}%"></i></div><span class="card-open"><i data-lucide="chevron-right"></i></span></button>`;
}

function renderSignals(){
  const filtered=signals.filter(signal=>activeFilter==='ALL'||signal.side===activeFilter);
  $('#signal-preview').innerHTML=signals.length?signals.slice(0,3).map(signalCard).join(''):`<div class="empty-state">${tr('noSignals')}</div>`;
  $('#signal-history').innerHTML=filtered.length?filtered.map(signalCard).join(''):`<div class="empty-state">${tr('noSignals')}</div>`;
  hydrateCoinIcons();
  lucide.createIcons();
}

function chartBundle(container,height){
  const chart=LightweightCharts.createChart(container,{width:container.clientWidth,height,layout:{background:{type:'solid',color:'#0d1118'},textColor:'#778295',fontFamily:'-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',fontSize:10},grid:{vertLines:{color:'#171d27'},horzLines:{color:'#171d27'}},rightPriceScale:{borderColor:'#252d3b',scaleMargins:{top:.08,bottom:.25}},timeScale:{borderColor:'#252d3b',timeVisible:true,secondsVisible:false,rightOffset:5,barSpacing:7,minBarSpacing:3},crosshair:{mode:LightweightCharts.CrosshairMode.Normal,vertLine:{color:'#53627a',width:1,style:2,labelBackgroundColor:'#273247'},horzLine:{color:'#53627a',width:1,style:2,labelBackgroundColor:'#273247'}},handleScale:{axisPressedMouseMove:true},handleScroll:{vertTouchDrag:false}});
  const candles=chart.addCandlestickSeries({upColor:'#17c89b',downColor:'#f05d6f',borderVisible:false,wickUpColor:'#17c89b',wickDownColor:'#f05d6f',priceLineVisible:true,lastValueVisible:true});
  const volume=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'volume',lastValueVisible:false,priceLineVisible:false});
  const ema20=chart.addLineSeries({color:'#2f8cff',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  const ema50=chart.addLineSeries({color:'#f2b84b',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  chart.priceScale('volume').applyOptions({scaleMargins:{top:.82,bottom:0}});
  return{chart,candles,volume,ema20,ema50,lines:[]};
}

function emaData(data,period){
  const multiplier=2/(period+1);
  let value=null;
  return data.map(candle=>{value=value==null?Number(candle.close):(Number(candle.close)-value)*multiplier+value;return{time:candle.time,value}});
}

function setChartData(bundle,data){
  bundle.candles.setData(data);
  bundle.volume.setData(data.map(candle=>({time:candle.time,value:candle.volume||0,color:candle.close>=candle.open?'rgba(23,200,155,.18)':'rgba(240,93,111,.18)'})));
  bundle.ema20.setData(emaData(data,20));
  bundle.ema50.setData(emaData(data,50));
  bundle.chart.timeScale().fitContent();
}

function clearPriceLines(bundle){
  bundle.lines.forEach(line=>bundle.candles.removePriceLine(line));
  bundle.lines=[];
}

function addSignalLines(bundle,signal){
  clearPriceLines(bundle);
  const levels=[{key:'entry',title:'ENTRY',color:'#2f8cff'},{key:'stop',title:'STOP',color:'#f05d6f'},{key:'tp1',title:'TP1',color:'#17c89b'},{key:'tp2',title:'TP2',color:'#17c89b'}];
  const levelPrices=levels.map(level=>Number(signal[level.key])).filter(Number.isFinite);
  bundle.candles.applyOptions({autoscaleInfoProvider:original=>{
    const info=original();
    if(!info?.priceRange||!levelPrices.length)return info;
    const minValue=Math.min(info.priceRange.minValue,...levelPrices);
    const maxValue=Math.max(info.priceRange.maxValue,...levelPrices);
    const padding=Math.max((maxValue-minValue)*.035,Math.abs(maxValue)*.001);
    return{...info,priceRange:{minValue:minValue-padding,maxValue:maxValue+padding}};
  }});
  levels.forEach(level=>{
    const price=Number(signal[level.key]);
    if(Number.isFinite(price))bundle.lines.push(bundle.candles.createPriceLine({price,color:level.color,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:level.title}));
  });
  bundle.chart.timeScale().fitContent();
}

async function api(path,options={}){
  const response=await fetch(path,{...options,headers:{...headers,...options.headers}});
  if(!response.ok)throw new Error(await response.text());
  return response.json();
}

async function loadOverviewChart(){
  $('#chart-symbol').textContent=displaySymbol(overviewSymbol);
  const icons={BTC_USDT:'btc',ETH_USDT:'eth',SOL_USDT:'sol'};
  $('#coin-icon').src=`https://assets.coincap.io/assets/icons/${icons[overviewSymbol]||'btc'}@2x.png`;
  const data=await api(`/api/market/${overviewSymbol}?timeframe=${overviewTimeframe}`);
  if(!overviewChart)overviewChart=chartBundle($('#chart'),310);
  setChartData(overviewChart,data);
  const last=data.at(-1),first=data.at(0);
  const change=first?.open?((last.close-first.open)/first.open)*100:0;
  $('#chart-price').textContent=`${fmt(last?.close)} USDT  ${change>=0?'+':''}${change.toFixed(2)}%`;
  $('#chart-price').classList.toggle('negative',change<0);
  $('#chart-trend').textContent=change>=0?'BULLISH':'BEARISH';
  $('#chart-trend').className=change>=0?'positive':'negative';
  $('#chart-timeframe').textContent=overviewTimeframe.toUpperCase();
  const setup=signals.find(signal=>String(signal.symbol).toUpperCase()===overviewSymbol);
  if(setup){
    addSignalLines(overviewChart,setup);
    $('#chart-setup').textContent=`${String(setup.side).toUpperCase()} · ${Math.round(clamp(setup.confidence,0,1)*100)}%`;
    $('#chart-setup').className=String(setup.side).toUpperCase()==='SHORT'?'negative':'positive';
  }else{
    clearPriceLines(overviewChart);
    $('#chart-setup').textContent='MARKET VIEW';
    $('#chart-setup').className='';
  }
}

function detailMetric(label,value,accent=''){
  return `<div class="detail-metric ${escapeHtml(accent)}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderSignalDetail(signal){
  const side=String(signal.side||'').toUpperCase()==='SHORT'?'SHORT':'LONG';
  const metrics=signalMetrics(signal);
  $('#detail-coin').innerHTML=coinIconMarkup(signal.symbol);
  hydrateCoinIcons($('#detail-coin'));
  $('#detail-symbol').textContent=displaySymbol(signal.symbol);
  $('#detail-date').textContent=new Date(signal.created_at).toLocaleString(language,{dateStyle:'medium',timeStyle:'short'});
  $('#detail-side').textContent=side;
  $('#detail-side').className=`side ${side.toLowerCase()}`;
  $('#detail-confidence').textContent=`${Math.round(signal.confidence*100)}%`;
  $('#detail-levels').innerHTML=[detailMetric(tr('entry'),fmt(signal.entry),'entry'),detailMetric(tr('stop'),fmt(signal.stop),'stop'),detailMetric(tr('tp1'),fmt(signal.tp1),'tp'),detailMetric(tr('tp2'),fmt(signal.tp2),'tp')].join('');
  $('#detail-position').innerHTML=[detailMetric(tr('deposit'),`${fmt(profile.deposit)} USDT`),detailMetric(tr('positionSize'),`${fmt(metrics.position)} USDT`),detailMetric(`${tr('marginRequired')} x${fmt(metrics.leverage)}`,`${fmt(metrics.margin)} USDT`),detailMetric(`${tr('stopRisk')} (${fmt(profile.risk_pct)}%)`,`${fmt(metrics.riskUsdt)} USDT`,'risk')].join('');
}

async function loadDetailChart(){
  if(!selectedSignal)return;
  const data=await api(`/api/market/${selectedSignal.symbol}?timeframe=${detailTimeframe}`);
  if(!detailChart)detailChart=chartBundle($('#detail-chart'),390);
  setChartData(detailChart,data);
  addSignalLines(detailChart,selectedSignal);
  const last=data.at(-1),first=data.at(0);
  const change=first?.open?((last.close-first.open)/first.open)*100:0;
  $('#detail-live-price').textContent=`${fmt(last?.close)} USDT`;
  $('#detail-price-change').textContent=`${change>=0?'+':''}${change.toFixed(2)}% / ${detailTimeframe}`;
  $('#detail-price-change').className=change<0?'negative':'positive';
}

async function openSignalDetail(signalId){
  selectedSignal=signals.find(signal=>String(signal.id)===String(signalId));
  if(!selectedSignal)return;
  renderSignalDetail(selectedSignal);
  showView('signal-detail','signals');
  tg?.BackButton?.show();
  try{await loadDetailChart()}catch(error){showToast(error.message||'Market data unavailable')}
}

function closeSignalDetail(){
  selectedSignal=null;
  tg?.BackButton?.hide();
  showView('signals');
}

function showView(name,navTarget=name){
  document.querySelectorAll('.view').forEach(view=>view.classList.toggle('active',view.dataset.view===name));
  document.querySelectorAll('.bottom-nav button').forEach(button=>button.classList.toggle('active',button.dataset.target===navTarget));
  window.scrollTo({top:0,behavior:'smooth'});
}

function showToast(text){
  const toast=$('#toast');
  toast.textContent=text;
  toast.classList.add('show');
  setTimeout(()=>toast.classList.remove('show'),2600);
}

async function load(){
  try{
    [profile,signals]=await Promise.all([api('/api/me'),api('/api/signals')]);
    signals=signals.filter(signal=>isUsdtPair(signal.symbol));
    language=profile.language||'en';
    applyLanguage();
    await loadOverviewChart();
  }catch(error){showToast(error.message||'Connection error')}
}

async function refreshLiveData(){
  if(document.hidden)return;
  try{
    [profile,signals]=await Promise.all([api('/api/me'),api('/api/signals')]);
    signals=signals.filter(signal=>isUsdtPair(signal.symbol));
    renderProfile();
    renderSignals();
    if(selectedSignal){
      selectedSignal=signals.find(signal=>String(signal.id)===String(selectedSignal.id))||selectedSignal;
      renderSignalDetail(selectedSignal);
    }
  }catch(error){}
}

document.querySelectorAll('.bottom-nav button').forEach(button=>button.addEventListener('click',()=>{selectedSignal=null;tg?.BackButton?.hide();showView(button.dataset.target)}));
document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.go)));
document.querySelectorAll('.filter').forEach(button=>button.addEventListener('click',()=>{activeFilter=button.dataset.filter;document.querySelectorAll('.filter').forEach(item=>item.classList.toggle('selected',item===button));renderSignals()}));
document.querySelectorAll('#symbol-picker button').forEach(button=>button.addEventListener('click',async()=>{overviewSymbol=button.dataset.symbol;document.querySelectorAll('#symbol-picker button').forEach(item=>item.classList.toggle('selected',item===button));await loadOverviewChart()}));
document.querySelectorAll('#overview-timeframe button').forEach(button=>button.addEventListener('click',async()=>{overviewTimeframe=button.dataset.timeframe;document.querySelectorAll('#overview-timeframe button').forEach(item=>item.classList.toggle('selected',item===button));await loadOverviewChart()}));
document.querySelectorAll('#detail-timeframe button').forEach(button=>button.addEventListener('click',async()=>{detailTimeframe=button.dataset.timeframe;document.querySelectorAll('#detail-timeframe button').forEach(item=>item.classList.toggle('selected',item===button));await loadDetailChart()}));
['#signal-preview','#signal-history'].forEach(selector=>$(selector).addEventListener('click',event=>{const card=event.target.closest('[data-signal-id]');if(card)openSignalDetail(card.dataset.signalId)}));
$('#signal-back').addEventListener('click',closeSignalDetail);
tg?.BackButton?.onClick(closeSignalDetail);
$('#language').addEventListener('change',async event=>{language=event.target.value;applyLanguage();await api('/api/settings',{method:'PATCH',body:JSON.stringify({language})})});
$('#settings-form').addEventListener('submit',async event=>{event.preventDefault();const payload={deposit:Number($('#deposit-input').value),risk_pct:Number($('#risk-input').value),leverage:Number($('#leverage-input').value),margin:document.querySelector('input[name=margin]:checked').value};await api('/api/settings',{method:'PATCH',body:JSON.stringify(payload)});Object.assign(profile,payload);renderProfile();renderSignals();if(selectedSignal)renderSignalDetail(selectedSignal);$('#form-status').textContent=tr('saved');showToast(tr('saved'))});
async function requestPayment(){showToast(tr('paymentHelp'));try{await api('/api/payment-instructions',{method:'POST'});tg?.close()}catch(error){if(!profile?.bot_username){showToast(tr('paymentUnavailable'));tg?.showAlert?.(tr('paymentUnavailable'));return}const url=`https://t.me/${profile.bot_username}?start=subscribe_${language}`;if(tg?.openTelegramLink)tg.openTelegramLink(url);else window.location.href=url}}
$('#payment-button').addEventListener('click',requestPayment);
document.querySelectorAll('.paywall-button').forEach(button=>button.addEventListener('click',requestPayment));
$('#refresh').addEventListener('click',async()=>{await load();if(selectedSignal)await loadDetailChart()});
window.addEventListener('resize',()=>{overviewChart?.chart.applyOptions({width:$('#chart').clientWidth});detailChart?.chart.applyOptions({width:$('#detail-chart').clientWidth})});
lucide.createIcons();
load();
setInterval(refreshLiveData,60000);
