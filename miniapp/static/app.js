const tg = window.Telegram?.WebApp;
tg?.ready(); tg?.expand();

const translations = {
  en:{workspace:'PRIVATE WORKSPACE',hello:'Hello',marketLive:'MEXC LIVE',deposit:'Deposit',riskTrade:'Risk / trade',leverage:'Leverage',access:'Access',cross:'Cross',isolated:'Isolated',scanner:'MARKET SCANNER',latestSignals:'Latest signals',viewAll:'View all',signalHistory:'Signal history',all:'All',riskProfile:'RISK PROFILE',settings:'Settings',depositUsdt:'Deposit, USDT',riskPercent:'Risk per trade, %',leverageX:'Leverage',marginMode:'Margin mode',saveSettings:'Save settings',subscription:'SUBSCRIPTION',monthlyAccess:'Monthly access',subscriptionCopy:'Automatic signals, scanner and full position plans.',paymentInstructions:'Payment instructions',overview:'Overview',signals:'Signals',trial:'Trial',signalsLeft:'signals left',active:'Active',inactive:'Inactive',entry:'Entry',stop:'Stop',confidence:'Confidence',saved:'Settings saved',paymentHelp:'Opening payment instructions in the bot...',paymentUnavailable:'Could not open the bot. Close the app and send /subscribe.',noSignals:'No signals yet',currentPrice:'Current price',tp1:'TP1',tp2:'TP2',positionSize:'Position size',marginRequired:'Margin required',stopRisk:'Stop risk',backToSignals:'Back to signals',tradeSetup:'TRADE SETUP',livePrice:'LIVE PRICE',signalLevels:'SIGNAL LEVELS',executionPlan:'Execution plan',personalSizing:'PERSONAL SIZING',positionPlan:'Position plan',trialComplete:'Free trial completed',trialCompleteCopy:'You used 5 free signals. Subscribe to continue receiving new setups.',unlockSignals:'Unlock signals',marketOffline:'MEXC OFFLINE',bullish:'BULLISH',bearish:'BEARISH',marketView:'MARKET VIEW',legendEntry:'Entry',legendStop:'Stop',legendTargets:'TP1 / TP2',trendLabel:'TREND',setupLabel:'SETUP',timeframeLabel:'TIMEFRAME',requestPlan:'Request a plan',payExact:'Exact amount',copyAddress:'Copy',txHash:'Transaction hash',submitHash:'Submit hash',paymentFailed:'Payment was not confirmed. Check the hash and try again.',retryPayment:'Try again',accessOpen:'Access open',accessOpenCopy:'Access is open on this screen.',listing:'Listing',copied:'Address copied',filterEmpty:'No {side} signals in this filter.',saveFailed:'Could not save settings.',settingsAccessCopy:'Access is open. You do not need to pay again.',levCapped:'Leverage was reduced to the MEXC maximum for this market.',minContract:'The minimum MEXC contract is too large for this risk. Do not open the trade.',sizeDisclaimer:'The bot calculates the size. You place the order.',regimeLabel:'Regime',network:'Network',flat:'Flat',regimeTrend:'Trend',regimeRange:'Range',needAccess:'Need access',openMexc:'Copy setup',copiedSetup:'Setup copied',confidenceNote:'Rules estimate, not a probability.',tf1d:'1D trend',tf4h:'4H trend',tfStruct:'4H structure',languageLabel:'Language',paymentWaiting:'Waiting for the check',paymentMismatch:'It did not match.',accessOpenUntil:'Access is open until {date}.',scannerSilent:'The scanner was silent.',lastScan:'Last scan {time}.',scanNever:'not yet',ageMinute:'m',ageHour:'h',ageDay:'d'},
  ru:{workspace:'ЛИЧНЫЙ КАБИНЕТ',hello:'Привет',marketLive:'MEXC ОНЛАЙН',deposit:'Депозит',riskTrade:'Риск / сделку',leverage:'Плечо',access:'Доступ',cross:'Кросс',isolated:'Изолированная',scanner:'СКАНЕР РЫНКА',latestSignals:'Последние сигналы',viewAll:'Все сигналы',signalHistory:'История сигналов',all:'Все',riskProfile:'РИСК-ПРОФИЛЬ',settings:'Настройки',depositUsdt:'Депозит, USDT',riskPercent:'Риск на сделку, %',leverageX:'Кредитное плечо',marginMode:'Режим маржи',saveSettings:'Сохранить',subscription:'ПОДПИСКА',monthlyAccess:'Месячный доступ',subscriptionCopy:'Автосигналы, сканер и полные торговые планы.',paymentInstructions:'Инструкция по оплате',overview:'Обзор',signals:'Сигналы',trial:'Пробный доступ',signalsLeft:'сигналов осталось',active:'Активна',inactive:'Неактивна',entry:'Вход',stop:'Стоп',confidence:'Уверенность',saved:'Настройки сохранены',paymentHelp:'Открываю инструкцию по оплате в боте...',paymentUnavailable:'Не удалось открыть бота. Закрой приложение и отправь /subscribe.',noSignals:'Сигналов пока нет',currentPrice:'Цена сейчас',tp1:'TP1',tp2:'TP2',positionSize:'Объём позиции',marginRequired:'Нужно маржи',stopRisk:'Риск по стопу',backToSignals:'Назад к сигналам',tradeSetup:'ТОРГОВЫЙ СЕТАП',livePrice:'ЦЕНА ОНЛАЙН',signalLevels:'УРОВНИ СИГНАЛА',levelsTitle:'Уровни',personalSizing:'ПЕРСОНАЛЬНЫЙ РАСЧЁТ',positionPlan:'План позиции',trialComplete:'Пробный доступ завершён',trialCompleteCopy:'Ты использовал 5 бесплатных сигналов. Оформи подписку, чтобы получать новые сетапы.',unlockSignals:'Открыть доступ',marketOffline:'MEXC НЕ В СЕТИ',bullish:'РОСТ',bearish:'ПАДЕНИЕ',marketView:'ОБЗОР РЫНКА',legendEntry:'Вход',legendStop:'Стоп',legendTargets:'TP1 / TP2',trendLabel:'ТРЕНД',setupLabel:'СЕТАП',timeframeLabel:'ТАЙМФРЕЙМ',requestPlan:'Запросить план',payExact:'Точная сумма',copyAddress:'Копировать',txHash:'Хеш транзакции',submitHash:'Отправить хеш',paymentFailed:'Платёж не подтверждён. Проверь хеш и повтори.',retryPayment:'Повторить',accessOpen:'Доступ открыт',accessOpenCopy:'Доступ открыт на этом экране.',listing:'Листинг',copied:'Адрес скопирован',filterEmpty:'В фильтре {side} пусто.',saveFailed:'Не удалось сохранить настройки.',settingsAccessCopy:'Доступ открыт. Повторная оплата не нужна.',levCapped:'Плечо снижено до максимума MEXC для этой монеты.',minContract:'Минимальный контракт MEXC слишком велик для этого риска. Сделку открывать не нужно.',sizeDisclaimer:'Бот считает размер. Ордер ставишь ты.',regimeLabel:'Режим',network:'Сеть',flat:'Флэт',regimeTrend:'Тренд',regimeRange:'Диапазон',needAccess:'Нужен доступ',openMexc:'Скопировать сетап',copiedSetup:'Сетап скопирован',confidenceNote:'Оценка правил, не вероятность.',tf1d:'Тренд 1Д',tf4h:'Тренд 4Ч',tfStruct:'Структура 4Ч',languageLabel:'Язык',paymentWaiting:'Ждём проверку',paymentMismatch:'Не сошлось.',accessOpenUntil:'Доступ открыт до {date}.',scannerSilent:'Сканер молчал.',lastScan:'Последний скан {time}.',scanNever:'ещё не было',ageMinute:'м',ageHour:'ч',ageDay:'д'},
  de:{workspace:'PRIVATER ARBEITSBEREICH',hello:'Hallo',marketLive:'MEXC LIVE',deposit:'Kapital',riskTrade:'Risiko / Trade',leverage:'Hebel',access:'Zugang',cross:'Cross',isolated:'Isoliert',scanner:'MARKTSCANNER',latestSignals:'Neueste Signale',viewAll:'Alle anzeigen',signalHistory:'Signalverlauf',all:'Alle',riskProfile:'RISIKOPROFIL',settings:'Einstellungen',depositUsdt:'Kapital, USDT',riskPercent:'Risiko pro Trade, %',leverageX:'Hebel',marginMode:'Margin-Modus',saveSettings:'Speichern',subscription:'ABONNEMENT',monthlyAccess:'Monatlicher Zugang',subscriptionCopy:'Automatische Signale, Scanner und vollständige Pläne.',paymentInstructions:'Zahlungsanleitung',overview:'Übersicht',signals:'Signale',trial:'Testzugang',signalsLeft:'Signale übrig',active:'Aktiv',inactive:'Inaktiv',entry:'Einstieg',stop:'Stop',confidence:'Konfidenz',saved:'Einstellungen gespeichert',paymentHelp:'Zahlungsanleitung wird im Bot geöffnet...',paymentUnavailable:'Der Bot konnte nicht geöffnet werden. Schließe die App und sende /subscribe.',noSignals:'Noch keine Signale',currentPrice:'Aktueller Preis',tp1:'TP1',tp2:'TP2',positionSize:'Positionsgröße',marginRequired:'Benötigte Margin',stopRisk:'Stop-Risiko',backToSignals:'Zurück zu Signalen',tradeSetup:'TRADE-SETUP',livePrice:'LIVE-PREIS',signalLevels:'SIGNALNIVEAUS',executionPlan:'Ausführungsplan',personalSizing:'PERSÖNLICHE GRÖSSE',positionPlan:'Positionsplan',trialComplete:'Testphase beendet',trialCompleteCopy:'Du hast 5 kostenlose Signale genutzt. Abonniere, um neue Setups zu erhalten.',unlockSignals:'Signale freischalten',marketOffline:'MEXC OFFLINE',bullish:'STEIGEND',bearish:'FALLEND',marketView:'MARKTÜBERBLICK',legendEntry:'Einstieg',legendStop:'Stop',legendTargets:'TP1 / TP2',trendLabel:'TREND',setupLabel:'SETUP',timeframeLabel:'ZEITRAHMEN',requestPlan:'Plan anfordern',payExact:'Genauer Betrag',copyAddress:'Kopieren',txHash:'Transaktions-Hash',submitHash:'Hash senden',paymentFailed:'Zahlung nicht bestätigt. Prüfe den Hash und versuche es erneut.',retryPayment:'Erneut versuchen',accessOpen:'Zugang offen',accessOpenCopy:'Der Zugang ist auf diesem Bildschirm offen.',listing:'Listing',copied:'Adresse kopiert',filterEmpty:'Keine {side}-Signale in diesem Filter.',saveFailed:'Einstellungen konnten nicht gespeichert werden.',settingsAccessCopy:'Der Zugang ist offen. Eine erneute Zahlung ist nicht nötig.',levCapped:'Der Hebel wurde auf das MEXC-Maximum für diesen Markt gesenkt.',minContract:'Der minimale MEXC-Kontrakt ist für dieses Risiko zu groß. Trade nicht eröffnen.',sizeDisclaimer:'Der Bot berechnet die Größe. Die Order setzt du.',regimeLabel:'Regime',network:'Netzwerk',flat:'Seitwärts',regimeTrend:'Trend',regimeRange:'Range',needAccess:'Zugang nötig',openMexc:'Setup kopieren',copiedSetup:'Setup kopiert',confidenceNote:'Regeleinschätzung, keine Wahrscheinlichkeit.',tf1d:'Trend 1D',tf4h:'Trend 4H',tfStruct:'Struktur 4H',languageLabel:'Sprache',paymentWaiting:'Warten auf die Prüfung',paymentMismatch:'Es hat nicht gepasst.',accessOpenUntil:'Zugang offen bis {date}.',scannerSilent:'Der Scanner war still.',lastScan:'Letzter Scan {time}.',scanNever:'noch keiner',ageMinute:'m',ageHour:'h',ageDay:'T'},
  fr:{workspace:'ESPACE PRIVÉ',hello:'Bonjour',marketLive:'MEXC EN DIRECT',deposit:'Dépôt',riskTrade:'Risque / trade',leverage:'Levier',access:'Accès',cross:'Cross',isolated:'Isolée',scanner:'SCANNER DU MARCHÉ',latestSignals:'Derniers signaux',viewAll:'Tout voir',signalHistory:'Historique des signaux',all:'Tous',riskProfile:'PROFIL DE RISQUE',settings:'Paramètres',depositUsdt:'Dépôt, USDT',riskPercent:'Risque par trade, %',leverageX:'Levier',marginMode:'Mode de marge',saveSettings:'Enregistrer',subscription:'ABONNEMENT',monthlyAccess:'Accès mensuel',subscriptionCopy:'Signaux automatiques, scanner et plans complets.',paymentInstructions:'Instructions de paiement',overview:'Aperçu',signals:'Signaux',trial:'Essai',signalsLeft:'signaux restants',active:'Actif',inactive:'Inactif',entry:'Entrée',stop:'Stop',confidence:'Confiance',saved:'Paramètres enregistrés',paymentHelp:'Ouverture des instructions de paiement dans le bot...',paymentUnavailable:'Impossible d\'ouvrir le bot. Ferme l\'application et envoie /subscribe.',noSignals:'Aucun signal',currentPrice:'Prix actuel',tp1:'TP1',tp2:'TP2',positionSize:'Taille de position',marginRequired:'Marge requise',stopRisk:'Risque au stop',backToSignals:'Retour aux signaux',tradeSetup:'CONFIGURATION',livePrice:'PRIX EN DIRECT',signalLevels:'NIVEAUX DU SIGNAL',executionPlan:'Plan d\'exécution',personalSizing:'TAILLE PERSONNELLE',positionPlan:'Plan de position',trialComplete:'Essai terminé',trialCompleteCopy:'Tu as utilisé 5 signaux gratuits. Abonne-toi pour continuer à recevoir de nouveaux setups.',unlockSignals:'Débloquer les signaux',marketOffline:'MEXC HORS LIGNE',bullish:'HAUSSIER',bearish:'BAISSIER',marketView:'VUE DU MARCHÉ',legendEntry:'Entrée',legendStop:'Stop',legendTargets:'TP1 / TP2',trendLabel:'TENDANCE',setupLabel:'SETUP',timeframeLabel:'UNITÉ DE TEMPS',requestPlan:'Demander un plan',payExact:'Montant exact',copyAddress:'Copier',txHash:'Hash de transaction',submitHash:'Envoyer le hash',paymentFailed:'Paiement non confirmé. Vérifie le hash et réessaie.',retryPayment:'Réessayer',accessOpen:'Accès ouvert',accessOpenCopy:'L\'accès est ouvert sur cet écran.',listing:'Listing',copied:'Adresse copiée',filterEmpty:'Aucun signal {side} dans ce filtre.',saveFailed:'Impossible d\'enregistrer les paramètres.',settingsAccessCopy:'L\'accès est ouvert. Un nouveau paiement n\'est pas nécessaire.',levCapped:'Le levier a été réduit au maximum MEXC de ce marché.',minContract:'Le contrat minimum MEXC est trop grand pour ce risque. N\'ouvre pas le trade.',sizeDisclaimer:'Le bot calcule la taille. Tu passes l\'ordre.',regimeLabel:'Régime',network:'Réseau',flat:'Plat',regimeTrend:'Tendance',regimeRange:'Range',needAccess:'Accès requis',openMexc:'Copier le setup',copiedSetup:'Setup copié',confidenceNote:'Estimation des règles, pas une probabilité.',tf1d:'Tendance 1J',tf4h:'Tendance 4H',tfStruct:'Structure 4H',languageLabel:'Langue',paymentWaiting:'En attente de la vérification',paymentMismatch:'Ça ne correspond pas.',accessOpenUntil:'Accès ouvert jusqu\'au {date}.',scannerSilent:'Le scanner est resté silencieux.',lastScan:'Dernier scan {time}.',scanNever:'pas encore',ageMinute:'min',ageHour:'h',ageDay:'j'},
  es:{workspace:'ESPACIO PRIVADO',hello:'Hola',marketLive:'MEXC EN VIVO',deposit:'Depósito',riskTrade:'Riesgo / operación',leverage:'Apalancamiento',access:'Acceso',cross:'Cruzado',isolated:'Aislado',scanner:'ESCÁNER DE MERCADO',latestSignals:'Últimas señales',viewAll:'Ver todas',signalHistory:'Historial de señales',all:'Todas',riskProfile:'PERFIL DE RIESGO',settings:'Ajustes',depositUsdt:'Depósito, USDT',riskPercent:'Riesgo por operación, %',leverageX:'Apalancamiento',marginMode:'Modo de margen',saveSettings:'Guardar',subscription:'SUSCRIPCIÓN',monthlyAccess:'Acceso mensual',subscriptionCopy:'Señales automáticas, escáner y planes completos.',paymentInstructions:'Instrucciones de pago',overview:'Resumen',signals:'Señales',trial:'Prueba',signalsLeft:'señales restantes',active:'Activo',inactive:'Inactivo',entry:'Entrada',stop:'Stop',confidence:'Confianza',saved:'Ajustes guardados',paymentHelp:'Abriendo las instrucciones de pago en el bot...',paymentUnavailable:'No se pudo abrir el bot. Cierra la aplicación y envía /subscribe.',noSignals:'Aún no hay señales',currentPrice:'Precio actual',tp1:'TP1',tp2:'TP2',positionSize:'Tamaño de posición',marginRequired:'Margen necesario',stopRisk:'Riesgo al stop',backToSignals:'Volver a señales',tradeSetup:'CONFIGURACIÓN',livePrice:'PRECIO EN VIVO',signalLevels:'NIVELES DE SEÑAL',executionPlan:'Plan de ejecución',personalSizing:'TAMAÑO PERSONAL',positionPlan:'Plan de posición',trialComplete:'Prueba finalizada',trialCompleteCopy:'Has usado 5 señales gratis. Suscríbete para seguir recibiendo nuevos setups.',unlockSignals:'Desbloquear señales',marketOffline:'MEXC SIN CONEXIÓN',bullish:'ALCISTA',bearish:'BAJISTA',marketView:'VISTA DEL MERCADO',legendEntry:'Entrada',legendStop:'Stop',legendTargets:'TP1 / TP2',trendLabel:'TENDENCIA',setupLabel:'SETUP',timeframeLabel:'MARCO TEMPORAL',requestPlan:'Pedir un plan',payExact:'Importe exacto',copyAddress:'Copiar',txHash:'Hash de la transacción',submitHash:'Enviar hash',paymentFailed:'El pago no se confirmó. Revisa el hash e inténtalo de nuevo.',retryPayment:'Reintentar',accessOpen:'Acceso abierto',accessOpenCopy:'El acceso está abierto en esta pantalla.',listing:'Listing',copied:'Dirección copiada',filterEmpty:'No hay señales {side} en este filtro.',saveFailed:'No se pudieron guardar los ajustes.',settingsAccessCopy:'El acceso está abierto. No hace falta pagar otra vez.',levCapped:'El apalancamiento se redujo al máximo de MEXC para este mercado.',minContract:'El contrato mínimo de MEXC es demasiado grande para este riesgo. No abras la operación.',sizeDisclaimer:'El bot calcula el tamaño. La orden la pones tú.',regimeLabel:'Régimen',network:'Red',flat:'Plano',regimeTrend:'Tendencia',regimeRange:'Rango',needAccess:'Hace falta acceso',openMexc:'Copiar el setup',copiedSetup:'Setup copiado',confidenceNote:'Estimación de reglas, no una probabilidad.',tf1d:'Tendencia 1D',tf4h:'Tendencia 4H',tfStruct:'Estructura 4H',languageLabel:'Idioma',paymentWaiting:'Esperando la comprobación',paymentMismatch:'No coincidió.',accessOpenUntil:'Acceso abierto hasta {date}.',scannerSilent:'El escáner estuvo en silencio.',lastScan:'Último escaneo {time}.',scanNever:'aún no',ageMinute:'min',ageHour:'h',ageDay:'d'}
};

const taglines={
  en:'Setups, risk and execution — one screen.',
  ru:'Сетапы и риск — на одном экране.',
  de:'Setups, Risiko und Ausführung — auf einem Bildschirm.',
  fr:'Setups, risque et exécution — sur un seul écran.',
  es:'Setups, riesgo y ejecución — en una sola pantalla.'
};

let profile=null,signals=[],language='en',activeFilter='ALL',selectedSignal=null;
let overviewSymbol='BTC_USDT',overviewTimeframe='4h',detailTimeframe='4h';
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
function coinIconMarkup(symbol){
  return `<span class="coin-fallback">${escapeHtml(coinBase(symbol).slice(0,2))}</span>`;
}

function hydrateCoinIcons(){}

function applyLanguage(){
  document.documentElement.lang=language;
  document.querySelectorAll('[data-i18n]').forEach(element=>element.textContent=tr(element.dataset.i18n));
  $('#language').value=language;
  renderProfile();
  renderSignals();
  renderHome();
  paintPaymentState();
  const current=homeSignal();
  if(overviewChart&&current)addSignalLines(overviewChart,current);
}

function paywalled(){
  if(!profile)return false;
  const paid=Boolean(profile.has_paid_access)||(profile.paid_until&&new Date(profile.paid_until)>new Date());
  return !paid&&Number(profile.trial_left)<=0;
}

function renderProfile(){
  if(!profile)return;
  const set=(selector,value)=>{const node=$(selector);if(node)node.textContent=value;};
  set('#first-name',profile.first_name||'Trader');
  set('#deposit-metric',fmt(profile.deposit));
  set('#risk-metric',fmt(profile.risk_pct));
  set('#leverage-metric',`x${fmt(profile.leverage)}`);
  if($('#deposit-input'))$('#deposit-input').value=profile.deposit??'';
  if($('#risk-input'))$('#risk-input').value=profile.risk_pct;
  if($('#leverage-input'))$('#leverage-input').value=profile.leverage;
  const margin=profile.margin==='isolated'?'isolated':'cross';
  const marginInput=document.querySelector(`input[name=margin][value="${margin}"]`);
  if(marginInput)marginInput.checked=true;
  const paid=Boolean(profile.has_paid_access)||(profile.paid_until&&new Date(profile.paid_until)>new Date());
  const locked=paywalled();
  set('#access-metric',paid?tr('active'):locked?tr('inactive'):tr('trial'));
  set('#access-detail',paid?new Date(profile.paid_until).toLocaleDateString(language):`${profile.trial_left} ${tr('signalsLeft')}`);
  document.querySelectorAll('.trial-paywall').forEach(element=>element.hidden=!locked);
  const market=$('#market-state');
  if(market){
    const live=Boolean(profile.scanner_live);
    market.classList.toggle('live',live);
    const label=$('#market-live-label');
    if(label)label.textContent=live?tr('marketLive'):tr('marketOffline');
  }
  const price=profile.payment_amount_usdt||profile.subscription_price_usdt||'—';
  const days=profile.subscription_days??'—';
  document.querySelectorAll('.subscription-price').forEach(node=>{node.textContent=price;});
  document.querySelectorAll('.subscription-days').forEach(node=>{node.textContent=days;});
  const title=$('#subscription-title');
  const copy=$('#subscription-copy');
  const pay=$('#payment-button');
  const priceBlock=$('#subscription-price-block');
  if(title&&copy&&pay&&priceBlock){
    title.textContent=paid?tr('accessOpen'):tr('monthlyAccess');
    copy.textContent=paid?tr('settingsAccessCopy'):tr('subscriptionCopy');
    pay.hidden=paid;
    priceBlock.hidden=paid;
  }
}

function signalMetrics(signal){
  const server=signal?.sizing;
  if(!server||!Number.isFinite(Number(server.position_usdt)))return null;
  return{riskUsdt:Number(server.risk_usdt),position:Number(server.position_usdt),margin:Number(server.margin_usdt),leverage:Number(server.effective_leverage)};
}

function confidenceLabel(signal){
  return `${Math.round(clamp(signal.confidence,0,1)*100)}%`;
}

function rewardRisk(signal){
  const entry=Number(signal.entry);
  const stop=Number(signal.stop);
  const target=Number(signal.tp1);
  const risk=Math.abs(entry-stop);
  const reward=Math.abs(target-entry);
  if(!Number.isFinite(risk)||!Number.isFinite(reward)||risk===0)return '—';
  return `${(reward/risk).toLocaleString(language,{maximumFractionDigits:2})}R`;
}

function signalAge(signal){
  const then=new Date(signal.created_at).valueOf();
  if(!Number.isFinite(then))return '—';
  const minutes=Math.max(0,Math.round((Date.now()-then)/60000));
  if(minutes<60)return `${minutes}${tr('ageMinute')}`;
  const hours=Math.round(minutes/60);
  if(hours<48)return `${hours}${tr('ageHour')}`;
  return `${Math.round(hours/24)}${tr('ageDay')}`;
}

function lastScanLine(){
  const raw=profile?.last_scan_at;
  const time=raw?new Date(raw).toLocaleString(language):tr('scanNever');
  return tr('lastScan').split('{time}').join(time);
}

function signalCard(signal){
  const side=String(signal.side||'').toUpperCase()==='SHORT'?'SHORT':'LONG';
  const signalId=Number.isSafeInteger(Number(signal.id))?Number(signal.id):0;
  const symbol=escapeHtml(displaySymbol(signal.symbol));
  return `<button type="button" class="signal-row" data-signal-id="${signalId}" data-side="${side}"><strong>${symbol}</strong><span class="side ${side.toLowerCase()}">${side}</span><b>${escapeHtml(rewardRisk(signal))}</b><small>${escapeHtml(signalAge(signal))}</small></button>`;
}

function emptySignals(filterOnly){
  const reason=filterOnly?tr('filterEmpty').split('{side}').join(activeFilter):tr('scannerSilent');
  const action=filterOnly?'':`<button type="button" class="primary-button empty-action" data-empty-action="plan">${escapeHtml(tr('requestPlan'))}</button>`;
  return `<div class="empty-state"><p>${escapeHtml(reason)}</p><p>${escapeHtml(lastScanLine())}</p>${action}</div>`;
}

const BASE_OVERVIEW_SYMBOLS=['BTC_USDT','ETH_USDT','SOL_USDT'];

function overviewSymbols(){
  const symbols=[];
  BASE_OVERVIEW_SYMBOLS.forEach(symbol=>{if(!symbols.includes(symbol))symbols.push(symbol);});
  if(isUsdtPair(overviewSymbol)&&!symbols.includes(overviewSymbol))symbols.push(overviewSymbol);
  signals.forEach(signal=>{
    const symbol=String(signal.symbol||'').toUpperCase();
    if(symbols.length>=8||!isUsdtPair(symbol)||symbols.includes(symbol))return;
    symbols.push(symbol);
  });
  return symbols.slice(0,8);
}

function syncSymbolPicker(){
  const picker=$('#symbol-picker');
  if(!picker)return;
  const symbols=overviewSymbols();
  if(!symbols.includes(overviewSymbol))overviewSymbol=symbols[0];
  picker.innerHTML=symbols.map(symbol=>`<button type="button" data-symbol="${escapeHtml(symbol)}" class="${symbol===overviewSymbol?'selected':''}">${escapeHtml(coinBase(symbol))}</button>`).join('');
}

function renderSignals(){
  const setups=signals.filter(isSetup);
  const filtered=setups.filter(signal=>activeFilter==='ALL'||signal.side===activeFilter);
  const filterOnly=activeFilter!=='ALL'&&setups.length>0;
  const history=$('#signal-history');
  if(history)history.innerHTML=filtered.length?filtered.map(signalCard).join(''):emptySignals(filterOnly);
  syncSymbolPicker();
  hydrateCoinIcons();
}

function chartBundle(container,height){
  const resolvedHeight=container.clientHeight||height;
  const chart=LightweightCharts.createChart(container,{width:container.clientWidth,height:resolvedHeight,layout:{background:{type:'solid',color:'#0d1118'},textColor:'#c5ceda',fontFamily:'-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif',fontSize:13},grid:{vertLines:{color:'#171d27'},horzLines:{color:'#171d27'}},rightPriceScale:{borderColor:'#252d3b',scaleMargins:{top:.08,bottom:.25}},timeScale:{borderColor:'#252d3b',timeVisible:true,secondsVisible:false,rightOffset:5,barSpacing:7,minBarSpacing:3},crosshair:{mode:LightweightCharts.CrosshairMode.Normal,vertLine:{color:'#53627a',width:1,style:2,labelBackgroundColor:'#273247'},horzLine:{color:'#53627a',width:1,style:2,labelBackgroundColor:'#273247'}},handleScale:{axisPressedMouseMove:true},handleScroll:{vertTouchDrag:false}});
  const candles=chart.addCandlestickSeries({upColor:'#17c89b',downColor:'#f05d6f',borderVisible:false,wickUpColor:'#17c89b',wickDownColor:'#f05d6f',priceLineVisible:true,lastValueVisible:true});
  const volume=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'volume',lastValueVisible:false,priceLineVisible:false});
  const ema20=chart.addLineSeries({color:'#2f8cff',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  const ema50=chart.addLineSeries({color:'#f2b84b',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  chart.priceScale('volume').applyOptions({scaleMargins:{top:.82,bottom:0}});
  return{chart,candles,volume,ema20,ema50,lines:[],container};
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
  const levels=[{key:'entry',title:tr('legendEntry'),color:'#2f8cff'},{key:'stop',title:tr('legendStop'),color:'#f05d6f'},{key:'tp1',title:tr('tp1'),color:'#17c89b'},{key:'tp2',title:tr('tp2'),color:'#17c89b'}];
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

const ALERT_SOURCES=new Set(['spike','smc','listing']);
function isSetup(signal){
  return !ALERT_SOURCES.has(String(signal?.source||'').toLowerCase());
}
function homeSignal(){
  if(selectedSignal&&isSetup(selectedSignal))return selectedSignal;
  return signals.find(isSetup)||null;
}
function biasWord(value){
  const key=String(value||'').toLowerCase();
  if(key==='up')return tr('bullish');
  if(key==='down')return tr('bearish');
  if(key==='flat')return tr('flat');
  if(key==='trend')return tr('regimeTrend');
  if(key==='range')return tr('regimeRange');
  return '';
}
function regimeParts(raw){
  const found={};
  String(raw||'').split(';').forEach(piece=>{
    const index=piece.indexOf('=');
    if(index>0)found[piece.slice(0,index)]=piece.slice(index+1);
  });
  return found;
}
function regimeLine(signal){
  const parts=regimeParts(signal?.regime);
  const day=biasWord(parts['1d']);
  const hour=biasWord(parts['4h']);
  if(!day&&!hour)return '—';
  return `1D ${day} · 4H ${hour}`.trim();
}
function reasonLine(signal){
  const lines=[];
  String(signal?.reason||'').split(' · ').forEach(piece=>{
    const item=piece.trim();
    if(!item||/entry|midrange|deposit/i.test(item))return;
    const value=item.split('=').slice(1).join('=');
    let word='';
    if(item.startsWith('trend_1d='))word=biasWord(value),lines.push(word?`${tr('tf1d')}: ${word}`:'');
    else if(item.startsWith('trend_4h='))word=biasWord(value),lines.push(word?`${tr('tf4h')}: ${word}`:'');
    else if(item.startsWith('struct_4h='))word=biasWord(value),lines.push(word?`${tr('tfStruct')}: ${word}`:'');
    else if(item.startsWith('regime='))word=biasWord(value),lines.push(word?`${tr('regimeLabel')}: ${word}`:'');
    else if(item.startsWith('bos='))lines.push(`BOS/CHOCH: ${value}`);
  });
  return lines.filter(Boolean).join(' · ');
}
function selectTimeframe(value){
  const next=String(value||'4h').toLowerCase();
  if(['15m','1h','4h','1d'].includes(next))overviewTimeframe=next;
  document.querySelectorAll('#overview-timeframe button').forEach(button=>button.classList.toggle('selected',button.dataset.timeframe===overviewTimeframe));
}
function renderHome(){
  const signal=homeSignal();
  const empty=$('#plan-empty');
  const body=$('#plan-body');
  if(empty)empty.hidden=Boolean(signal);
  if(body)body.hidden=!signal;
  syncMainButton();
  if(!signal)return;
  overviewSymbol=String(signal.symbol||overviewSymbol).toUpperCase();
  const side=String(signal.side||'').toUpperCase()==='SHORT'?'SHORT':'LONG';
  const sideNode=$('#plan-side');
  if(sideNode){sideNode.textContent=side;sideNode.className=`side ${side.toLowerCase()}`;}
  const symbolNode=$('#plan-symbol');
  if(symbolNode)symbolNode.textContent=displaySymbol(signal.symbol);
  const priceNode=$('#plan-price');
  if(priceNode)priceNode.textContent=signal.price==null?'—':`${fmt(signal.price)} USDT`;
  const confidence=$('#plan-confidence');
  if(confidence)confidence.textContent=`${tr('confidence')} ${confidenceLabel(signal)} · ${tr('confidenceNote')}`;
  const regime=$('#chart-regime');
  if(regime)regime.textContent=regimeLine(signal);
  const frameLabel=$('#chart-timeframe');
  if(frameLabel)frameLabel.textContent=String(signal.timeframe||overviewTimeframe||'4h').toUpperCase();
  const coin=$('#plan-coin');
  if(coin){coin.innerHTML=coinIconMarkup(signal.symbol);hydrateCoinIcons(coin);}
  const chartSymbol=$('#chart-symbol');
  if(chartSymbol)chartSymbol.textContent=displaySymbol(signal.symbol);
  const sizing=signal.sizing||{};
  const notes=[];
  const requested=Number(sizing.requested_leverage);
  const effective=Number(sizing.effective_leverage);
  if(Number.isFinite(requested)&&Number.isFinite(effective)&&effective<requested)notes.push(tr('levCapped'));
  if(Array.isArray(sizing.errors)&&sizing.errors.includes('position_below_min_contract'))notes.push(tr('minContract'));
  const caveat=$('#plan-caveat');
  if(caveat){caveat.hidden=!notes.length;caveat.textContent=notes.join(' ');}
  const metrics=signalMetrics(signal);
  const numbers=$('#plan-numbers');
  if(numbers){
    numbers.innerHTML=[
      detailMetric(tr('positionSize'),metrics?`${fmt(metrics.position)} USDT`:'—'),
      detailMetric(tr('marginRequired'),metrics?`${fmt(metrics.margin)} USDT`:'—'),
      detailMetric(tr('stopRisk'),metrics?`${fmt(metrics.riskUsdt)} USDT`:'—','risk'),
    ].join('');
  }
  const reason=$('#plan-reason');
  if(reason)reason.textContent=reasonLine(signal);
}
async function loadHomeChart(){
  const frame=$('#chart-frame');
  const signal=homeSignal();
  if(!signal?.symbol){frame?.classList.remove('loading');return;}
  frame?.classList.add('loading');
  overviewSymbol=String(signal.symbol).toUpperCase();
  try{
    const data=await api(`/api/market/${overviewSymbol}?timeframe=${overviewTimeframe}`);
    if(!overviewChart)overviewChart=chartBundle($('#chart'),310);
    setChartData(overviewChart,data);
    if(signal)addSignalLines(overviewChart,signal);
    else clearPriceLines(overviewChart);
    const last=data.at(-1);
    const price=$('#chart-price');
    if(price){price.textContent=`${fmt(last?.close)} USDT`;price.classList.remove('negative');}
    const live=$('#plan-price');
    if(live&&last?.close!=null)live.textContent=`${fmt(last.close)} USDT`;
  }finally{
    frame?.classList.remove('loading');
  }
}
function detailMetric(label,value,accent=''){
  return `<div class="detail-metric ${escapeHtml(accent)}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}
async function openSignalDetail(signalId){
  selectedSignal=signals.find(signal=>String(signal.id)===String(signalId)&&isSetup(signal));
  if(!selectedSignal)return;
  selectTimeframe(selectedSignal.timeframe||'4h');
  renderHome();
  showView('overview');
  try{await loadHomeChart()}catch(error){showToast(error.message||'Market data unavailable')}
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
function signalIdFromLocation(){
  const id=Number(new URLSearchParams(window.location.search).get('signal_id')||'');
  return Number.isSafeInteger(id)&&id>0?id:0;
}
async function load(){
  try{
    [profile,signals]=await Promise.all([api('/api/me'),api('/api/signals')]);
    signals=signals.filter(signal=>isUsdtPair(signal.symbol)&&isSetup(signal));
    language=profile.language||'en';
    const requested=signalIdFromLocation();
    selectedSignal=requested?signals.find(signal=>Number(signal.id)===requested)||null:null;
    if(!selectedSignal)selectedSignal=signals.find(isSetup)||null;
    selectTimeframe(selectedSignal?.timeframe||'4h');
    applyLanguage();
    if(new URLSearchParams(window.location.search).get('view')==='settings')showView('settings');
    await loadHomeChart();
  }catch(error){showToast(error.message||'Connection error')}
}
async function refreshLiveData(){
  if(document.hidden)return;
  try{
    [profile,signals]=await Promise.all([api('/api/me'),api('/api/signals')]);
    signals=signals.filter(signal=>isUsdtPair(signal.symbol)&&isSetup(signal));
    if(selectedSignal)selectedSignal=signals.find(signal=>String(signal.id)===String(selectedSignal.id))||null;
    if(!selectedSignal)selectedSignal=signals.find(isSetup)||null;
    renderProfile();
    renderSignals();
    renderHome();
  }catch(error){}
}
document.querySelectorAll('.bottom-nav button').forEach(button=>button.addEventListener('click',()=>{showView(button.dataset.target)}));
document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.go)));
document.querySelectorAll('.filter').forEach(button=>button.addEventListener('click',()=>{activeFilter=button.dataset.filter;document.querySelectorAll('.filter').forEach(item=>item.classList.toggle('selected',item===button));renderSignals()}));
const symbolPicker=$('#symbol-picker');
if(symbolPicker)symbolPicker.addEventListener('click',async event=>{const button=event.target.closest('button[data-symbol]');if(!button)return;overviewSymbol=button.dataset.symbol;document.querySelectorAll('#symbol-picker button').forEach(item=>item.classList.toggle('selected',item===button));await loadHomeChart()});
document.querySelectorAll('#overview-timeframe button').forEach(button=>button.addEventListener('click',async()=>{overviewTimeframe=button.dataset.timeframe;document.querySelectorAll('#overview-timeframe button').forEach(item=>item.classList.toggle('selected',item===button));await loadHomeChart()}));
document.querySelectorAll('#detail-timeframe button').forEach(button=>button.addEventListener('click',async()=>{detailTimeframe=button.dataset.timeframe;document.querySelectorAll('#detail-timeframe button').forEach(item=>item.classList.toggle('selected',item===button));await loadHomeChart()}));
['#signal-preview','#signal-history','#overview-view'].forEach(selector=>{
  const node=$(selector);
  if(!node)return;
  node.addEventListener('click',event=>{
    if(event.target.closest('[data-empty-action]')){requestPlan();return}
    const card=event.target.closest('[data-signal-id]');
    if(card)openSignalDetail(card.dataset.signalId);
  });
});
const signalBack=$('#signal-back');
if(signalBack)signalBack.addEventListener('click',()=>showView('signals'));
$('#language').addEventListener('change',async event=>{const previous=language;const next=event.target.value;language=next;applyLanguage();try{await api('/api/settings',{method:'PATCH',body:JSON.stringify({language:next})})}catch(error){language=previous;applyLanguage();showToast(tr('saveFailed'))}});
$('#settings-form').addEventListener('submit',async event=>{event.preventDefault();const payload={deposit:Number($('#deposit-input').value),risk_pct:Number($('#risk-input').value),leverage:Number($('#leverage-input').value),margin:document.querySelector('input[name=margin]:checked').value};const status=$('#form-status');try{await api('/api/settings',{method:'PATCH',body:JSON.stringify(payload)});Object.assign(profile,payload);const selectedId=selectedSignal?.id;signals=(await api('/api/signals')).filter(signal=>isUsdtPair(signal.symbol)&&isSetup(signal));selectedSignal=selectedId?signals.find(signal=>Number(signal.id)===Number(selectedId))||signals.find(isSetup)||null:signals.find(isSetup)||null;renderProfile();renderSignals();renderHome();status.classList.remove('error');status.textContent=tr('saved');showToast(tr('saved'))}catch(error){status.classList.add('error');status.textContent=tr('saveFailed');showToast(tr('saveFailed'))}});
function setPaymentState(state, until=''){
  const node=$('#payment-state');
  if(!node)return;
  node.dataset.state=state;
  node.dataset.until=until||'';
  if(state==='waiting')node.textContent=tr('paymentWaiting');
  else if(state==='mismatch')node.textContent=tr('paymentMismatch');
  else if(state==='open')node.textContent=tr('accessOpenUntil').split('{date}').join(until||'—');
}
function paintPaymentState(){
  const node=$('#payment-state');
  if(node?.dataset.state)setPaymentState(node.dataset.state, node.dataset.until||'');
}
function showPaymentForm(){
  $('#payment-form').hidden=false;
  $('#payment-error').hidden=true;
  $('#payment-retry').hidden=true;
  $('#payment-success').hidden=true;
  setPaymentState('waiting');
}
function showPaymentError(message){
  $('#payment-error').textContent=message||tr('paymentFailed');
  $('#payment-error').hidden=false;
  $('#payment-form').hidden=true;
  $('#payment-retry').hidden=false;
  $('#payment-success').hidden=true;
  setPaymentState('mismatch');
}
function showPaymentSuccess(until){
  $('#payment-form').hidden=true;
  $('#payment-error').hidden=true;
  $('#payment-retry').hidden=true;
  $('#payment-success').hidden=false;
  const date=until?new Date(until):null;
  const label=date&&!Number.isNaN(date.valueOf())?date.toLocaleDateString(language):'—';
  setPaymentState('open', label);
}
function requestPlan(){
  const username=profile?.bot_username;
  if(username){
    const url=`https://t.me/${username}?start=plan`;
    if(tg?.openTelegramLink)tg.openTelegramLink(url);
    else window.open(url,'_blank','noopener');
    return;
  }
  showToast(tr('requestPlan'));
}
async function openPayment(){
  const sheet=$('#payment-sheet');
  if(!sheet)return;
  sheet.hidden=false;
  showPaymentForm();
  try{
    profile=await api('/api/me');
    renderProfile();
  }catch(error){}
  $('#payment-amount').textContent=profile?.payment_amount_usdt||'—';
  $('#payment-address').textContent=profile?.payment_wallet||'—';
  $('#payment-network').textContent=profile?.payment_network||'';
  if(!profile?.payment_wallet)showPaymentError(tr('paymentFailed'));
}
async function copyPaymentAddress(){
  const text=$('#payment-address').textContent||'';
  if(!text||text==='—')return;
  try{await navigator.clipboard.writeText(text)}
  catch(error){
    const input=document.createElement('textarea');
    input.value=text;
    document.body.append(input);
    input.select();
    document.execCommand('copy');
    input.remove();
  }
  showToast(tr('copied'));
}
async function copyText(text){
  try{await navigator.clipboard.writeText(text);return}
  catch(error){
    const input=document.createElement('textarea');
    input.value=text;
    document.body.append(input);
    input.select();
    document.execCommand('copy');
    input.remove();
  }
}
function setupClipboard(signal){
  const metrics=signalMetrics(signal);
  const lines=[
    displaySymbol(signal.symbol),
    String(signal.side||'').toUpperCase(),
    `${tr('entry')} ${fmt(signal.entry)}`,
    `${tr('stop')} ${fmt(signal.stop)}`,
    `TP1 ${fmt(signal.tp1)}`,
    `TP2 ${fmt(signal.tp2)}`,
  ];
  if(metrics)lines.push(`${tr('positionSize')} ${fmt(metrics.position)} USDT`);
  return lines.join('\n');
}
function syncMainButton(){
  const button=tg?.MainButton;
  if(!button)return;
  if(paywalled()){button.setText(tr('needAccess'));button.show();return;}
  if(!homeSignal()){button.hide();return;}
  button.setText(tr('openMexc'));
  button.show();
}
async function onMainButton(){
  if(paywalled()){await openPayment();return;}
  const signal=homeSignal();
  if(!signal)return;
  await copyText(setupClipboard(signal));
  showToast(tr('copiedSetup'));
}
async function submitPayment(event){
  event.preventDefault();
  const tx_hash=$('#payment-hash').value.trim();
  setPaymentState('waiting');
  try{
    const response=await fetch('/api/payment',{method:'POST',headers,body:JSON.stringify({tx_hash})});
    const body=await response.json().catch(()=>({}));
    if(!response.ok||body.access_open!==true){
      showPaymentError(tr('paymentFailed'));
      return;
    }
    const paidUntil=body.paid_until?new Date(body.paid_until*1000).toISOString():profile.paid_until;
    showPaymentSuccess(paidUntil);
    profile={...profile,has_paid_access:true,paid_until:paidUntil};
    renderProfile();
    syncMainButton();
  }catch(error){
    showPaymentError(tr('paymentFailed'));
  }
}
$('#payment-button').addEventListener('click',openPayment);
document.querySelectorAll('.paywall-button').forEach(button=>button.addEventListener('click',openPayment));
$('#payment-copy').addEventListener('click',copyPaymentAddress);
$('#payment-form').addEventListener('submit',submitPayment);
$('#payment-retry').addEventListener('click',()=>{showPaymentForm();$('#payment-hash').focus()});
$('#payment-sheet').addEventListener('click',event=>{if(event.target.id==='payment-sheet')event.currentTarget.hidden=true});
$('#refresh').addEventListener('click',async()=>{await load()});
window.addEventListener('resize',()=>{if(overviewChart)overviewChart.chart.applyOptions({width:overviewChart.container.clientWidth,height:overviewChart.container.clientHeight})});
tg?.setHeaderColor?.('#090b10');
tg?.setBackgroundColor?.('#090b10');
tg?.MainButton?.onClick(onMainButton);
load();
setInterval(refreshLiveData,60000);
