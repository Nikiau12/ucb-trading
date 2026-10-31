const tg = window.Telegram?.WebApp;
tg?.ready(); tg?.expand();

const translations = {
  en:{btcChart:'BITCOIN MARKET',majorTrades:'BTC, ETH AND SOL TRADES',waitingSetup:'Waiting for a 4H/1D setup',workspace:'PRIVATE WORKSPACE',hello:'Hello',marketLive:'BingX LIVE',deposit:'Deposit',riskTrade:'Risk / trade',leverage:'Leverage',access:'Access',cross:'Cross',isolated:'Isolated',scanner:'MARKET SCANNER',latestSignals:'Latest signals',viewAll:'View all',signalHistory:'Signal history',all:'All',riskProfile:'RISK PROFILE',settings:'Settings',depositUsdt:'Deposit, USDT',riskPercent:'Risk per trade, %',leverageX:'Leverage',marginMode:'Margin mode',saveSettings:'Save settings',subscription:'SUBSCRIPTION',monthlyAccess:'Monthly access',subscriptionCopy:'Automatic signals, scanner and full position plans.',paymentInstructions:'Payment instructions',overview:'Overview',signals:'Signals',trial:'Trial',signalsLeft:'signals left',active:'Active',inactive:'Inactive',entry:'Entry',stop:'Stop',confidence:'Confidence',saved:'Settings saved',paymentHelp:'Opening payment instructions in the bot...',paymentUnavailable:'Could not open the bot. Close the app and send /subscribe.',noSignals:'No signals yet',noSetupFor:'No setup for {symbol}.',currentPrice:'Current price',tp1:'TP1',tp2:'TP2',positionSize:'Position size',marginRequired:'Margin required',stopRisk:'Stop risk',backToSignals:'Back to signals',tradeSetup:'TRADE SETUP',livePrice:'LIVE PRICE',signalLevels:'SIGNAL LEVELS',executionPlan:'Execution plan',personalSizing:'PERSONAL SIZING',positionPlan:'Position plan',trialComplete:'Free trial completed',trialCompleteCopy:'You used 5 free signals. Subscribe to continue receiving new setups.',unlockSignals:'Unlock signals',marketOffline:'BingX OFFLINE',bullish:'BULLISH',bearish:'BEARISH',marketView:'MARKET VIEW',legendEntry:'Entry',legendStop:'Stop',legendTargets:'TP1 / TP2',trendLabel:'TREND',setupLabel:'SETUP',timeframeLabel:'TIMEFRAME',requestPlan:'Request a plan',payExact:'Exact amount',copyAddress:'Copy',txHash:'Transaction hash',submitHash:'Submit hash',paymentFailed:'Payment was not confirmed. Check the hash and try again.',retryPayment:'Try again',accessOpen:'Access open',accessOpenCopy:'Access is open on this screen.',listing:'Listing',copied:'Address copied',filterEmpty:'No {side} signals in this filter.',saveFailed:'Could not save settings.',settingsAccessCopy:'Access is open. You do not need to pay again.',levCapped:'Leverage was reduced to the BingX maximum for this market.',minContract:'The minimum BingX contract is too large for this risk. Do not open the trade.',sizeDisclaimer:'The bot calculates the size. You place the order.',regimeLabel:'Regime',network:'Network',flat:'Flat',regimeTrend:'Trend',regimeRange:'Range',needAccess:'Need access',openMexc:'Copy setup',copiedSetup:'Setup copied',confidenceNote:'Rules estimate, not a probability.',tf1d:'1D trend',tf4h:'4H trend',tfStruct:'4H structure',languageLabel:'Language',paymentWaiting:'Waiting for the check',paymentMismatch:'It did not match.',accessOpenUntil:'Access is open until {date}.',scannerSilent:'The scanner was silent.',lastScan:'Last scan {time}.',scanNever:'not yet',ageMinute:'m',ageHour:'h',ageDay:'d'},
  ru:{btcChart:'ГРАФИК БИТКОИНА',majorTrades:'СДЕЛКИ BTC, ETH И SOL',waitingSetup:'Ожидаем сетап 4Ч/1Д',workspace:'ЛИЧНЫЙ КАБИНЕТ',hello:'Привет',marketLive:'BingX ОНЛАЙН',deposit:'Депозит',riskTrade:'Риск / сделку',leverage:'Плечо',access:'Доступ',cross:'Кросс',isolated:'Изолированная',scanner:'СКАНЕР РЫНКА',latestSignals:'Последние сигналы',viewAll:'Все сигналы',signalHistory:'История сигналов',all:'Все',riskProfile:'РИСК-ПРОФИЛЬ',settings:'Настройки',depositUsdt:'Депозит, USDT',riskPercent:'Риск на сделку, %',leverageX:'Кредитное плечо',marginMode:'Режим маржи',saveSettings:'Сохранить',subscription:'ПОДПИСКА',monthlyAccess:'Месячный доступ',subscriptionCopy:'Автосигналы, сканер и полные торговые планы.',paymentInstructions:'Инструкция по оплате',overview:'Обзор',signals:'Сигналы',trial:'Пробный доступ',signalsLeft:'сигналов осталось',active:'Активна',inactive:'Неактивна',entry:'Вход',stop:'Стоп',confidence:'Уверенность',saved:'Настройки сохранены',paymentHelp:'Открываю инструкцию по оплате в боте...',paymentUnavailable:'Не удалось открыть бота. Закрой приложение и отправь /subscribe.',noSignals:'Сигналов пока нет',noSetupFor:'Сетапа по {symbol} сейчас нет.',currentPrice:'Цена сейчас',tp1:'TP1',tp2:'TP2',positionSize:'Объём позиции',marginRequired:'Нужно маржи',stopRisk:'Риск по стопу',backToSignals:'Назад к сигналам',tradeSetup:'ТОРГОВЫЙ СЕТАП',livePrice:'ЦЕНА ОНЛАЙН',signalLevels:'УРОВНИ СИГНАЛА',levelsTitle:'Уровни',personalSizing:'ПЕРСОНАЛЬНЫЙ РАСЧЁТ',positionPlan:'План позиции',trialComplete:'Пробный доступ завершён',trialCompleteCopy:'Ты использовал 5 бесплатных сигналов. Оформи подписку, чтобы получать новые сетапы.',unlockSignals:'Открыть доступ',marketOffline:'BingX НЕ В СЕТИ',bullish:'РОСТ',bearish:'ПАДЕНИЕ',marketView:'ОБЗОР РЫНКА',legendEntry:'Вход',legendStop:'Стоп',legendTargets:'TP1 / TP2',trendLabel:'ТРЕНД',setupLabel:'СЕТАП',timeframeLabel:'ТАЙМФРЕЙМ',requestPlan:'Запросить план',payExact:'Точная сумма',copyAddress:'Копировать',txHash:'Хеш транзакции',submitHash:'Отправить хеш',paymentFailed:'Платёж не подтверждён. Проверь хеш и повтори.',retryPayment:'Повторить',accessOpen:'Доступ открыт',accessOpenCopy:'Доступ открыт на этом экране.',listing:'Листинг',copied:'Адрес скопирован',filterEmpty:'В фильтре {side} пусто.',saveFailed:'Не удалось сохранить настройки.',settingsAccessCopy:'Доступ открыт. Повторная оплата не нужна.',levCapped:'Плечо снижено до максимума BingX для этой монеты.',minContract:'Минимальный контракт BingX слишком велик для этого риска. Сделку открывать не нужно.',sizeDisclaimer:'Бот считает размер. Ордер ставишь ты.',regimeLabel:'Режим',network:'Сеть',flat:'Флэт',regimeTrend:'Тренд',regimeRange:'Диапазон',needAccess:'Нужен доступ',openMexc:'Скопировать сетап',copiedSetup:'Сетап скопирован',confidenceNote:'Оценка правил, не вероятность.',tf1d:'Тренд 1Д',tf4h:'Тренд 4Ч',tfStruct:'Структура 4Ч',languageLabel:'Язык',paymentWaiting:'Ждём проверку',paymentMismatch:'Не сошлось.',accessOpenUntil:'Доступ открыт до {date}.',scannerSilent:'Сканер молчал.',lastScan:'Последний скан {time}.',scanNever:'ещё не было',ageMinute:'м',ageHour:'ч',ageDay:'д'},
  de:{btcChart:'BITCOIN-MARKT',majorTrades:'BTC-, ETH- UND SOL-TRADES',waitingSetup:'Warten auf ein 4H/1D-Setup',workspace:'PRIVATER ARBEITSBEREICH',hello:'Hallo',marketLive:'BingX LIVE',deposit:'Kapital',riskTrade:'Risiko / Trade',leverage:'Hebel',access:'Zugang',cross:'Cross',isolated:'Isoliert',scanner:'MARKTSCANNER',latestSignals:'Neueste Signale',viewAll:'Alle anzeigen',signalHistory:'Signalverlauf',all:'Alle',riskProfile:'RISIKOPROFIL',settings:'Einstellungen',depositUsdt:'Kapital, USDT',riskPercent:'Risiko pro Trade, %',leverageX:'Hebel',marginMode:'Margin-Modus',saveSettings:'Speichern',subscription:'ABONNEMENT',monthlyAccess:'Monatlicher Zugang',subscriptionCopy:'Automatische Signale, Scanner und vollständige Pläne.',paymentInstructions:'Zahlungsanleitung',overview:'Übersicht',signals:'Signale',trial:'Testzugang',signalsLeft:'Signale übrig',active:'Aktiv',inactive:'Inaktiv',entry:'Einstieg',stop:'Stop',confidence:'Konfidenz',saved:'Einstellungen gespeichert',paymentHelp:'Zahlungsanleitung wird im Bot geöffnet...',paymentUnavailable:'Der Bot konnte nicht geöffnet werden. Schließe die App und sende /subscribe.',noSignals:'Noch keine Signale',noSetupFor:'Kein Setup für {symbol}.',currentPrice:'Aktueller Preis',tp1:'TP1',tp2:'TP2',positionSize:'Positionsgröße',marginRequired:'Benötigte Margin',stopRisk:'Stop-Risiko',backToSignals:'Zurück zu Signalen',tradeSetup:'TRADE-SETUP',livePrice:'LIVE-PREIS',signalLevels:'SIGNALNIVEAUS',executionPlan:'Ausführungsplan',personalSizing:'PERSÖNLICHE GRÖSSE',positionPlan:'Positionsplan',trialComplete:'Testphase beendet',trialCompleteCopy:'Du hast 5 kostenlose Signale genutzt. Abonniere, um neue Setups zu erhalten.',unlockSignals:'Signale freischalten',marketOffline:'BingX OFFLINE',bullish:'STEIGEND',bearish:'FALLEND',marketView:'MARKTÜBERBLICK',legendEntry:'Einstieg',legendStop:'Stop',legendTargets:'TP1 / TP2',trendLabel:'TREND',setupLabel:'SETUP',timeframeLabel:'ZEITRAHMEN',requestPlan:'Plan anfordern',payExact:'Genauer Betrag',copyAddress:'Kopieren',txHash:'Transaktions-Hash',submitHash:'Hash senden',paymentFailed:'Zahlung nicht bestätigt. Prüfe den Hash und versuche es erneut.',retryPayment:'Erneut versuchen',accessOpen:'Zugang offen',accessOpenCopy:'Der Zugang ist auf diesem Bildschirm offen.',listing:'Listing',copied:'Adresse kopiert',filterEmpty:'Keine {side}-Signale in diesem Filter.',saveFailed:'Einstellungen konnten nicht gespeichert werden.',settingsAccessCopy:'Der Zugang ist offen. Eine erneute Zahlung ist nicht nötig.',levCapped:'Der Hebel wurde auf das BingX-Maximum für diesen Markt gesenkt.',minContract:'Der minimale BingX-Kontrakt ist für dieses Risiko zu groß. Trade nicht eröffnen.',sizeDisclaimer:'Der Bot berechnet die Größe. Die Order setzt du.',regimeLabel:'Regime',network:'Netzwerk',flat:'Seitwärts',regimeTrend:'Trend',regimeRange:'Range',needAccess:'Zugang nötig',openMexc:'Setup kopieren',copiedSetup:'Setup kopiert',confidenceNote:'Regeleinschätzung, keine Wahrscheinlichkeit.',tf1d:'Trend 1D',tf4h:'Trend 4H',tfStruct:'Struktur 4H',languageLabel:'Sprache',paymentWaiting:'Warten auf die Prüfung',paymentMismatch:'Es hat nicht gepasst.',accessOpenUntil:'Zugang offen bis {date}.',scannerSilent:'Der Scanner war still.',lastScan:'Letzter Scan {time}.',scanNever:'noch keiner',ageMinute:'m',ageHour:'h',ageDay:'T'},
  fr:{btcChart:'MARCHÉ DU BITCOIN',majorTrades:'TRADES BTC, ETH ET SOL',waitingSetup:'En attente d’un setup 4H/1J',workspace:'ESPACE PRIVÉ',hello:'Bonjour',marketLive:'BingX EN DIRECT',deposit:'Dépôt',riskTrade:'Risque / trade',leverage:'Levier',access:'Accès',cross:'Cross',isolated:'Isolée',scanner:'SCANNER DU MARCHÉ',latestSignals:'Derniers signaux',viewAll:'Tout voir',signalHistory:'Historique des signaux',all:'Tous',riskProfile:'PROFIL DE RISQUE',settings:'Paramètres',depositUsdt:'Dépôt, USDT',riskPercent:'Risque par trade, %',leverageX:'Levier',marginMode:'Mode de marge',saveSettings:'Enregistrer',subscription:'ABONNEMENT',monthlyAccess:'Accès mensuel',subscriptionCopy:'Signaux automatiques, scanner et plans complets.',paymentInstructions:'Instructions de paiement',overview:'Aperçu',signals:'Signaux',trial:'Essai',signalsLeft:'signaux restants',active:'Actif',inactive:'Inactif',entry:'Entrée',stop:'Stop',confidence:'Confiance',saved:'Paramètres enregistrés',paymentHelp:'Ouverture des instructions de paiement dans le bot...',paymentUnavailable:'Impossible d\'ouvrir le bot. Ferme l\'application et envoie /subscribe.',noSignals:'Aucun signal',noSetupFor:'Pas de setup pour {symbol}.',currentPrice:'Prix actuel',tp1:'TP1',tp2:'TP2',positionSize:'Taille de position',marginRequired:'Marge requise',stopRisk:'Risque au stop',backToSignals:'Retour aux signaux',tradeSetup:'CONFIGURATION',livePrice:'PRIX EN DIRECT',signalLevels:'NIVEAUX DU SIGNAL',executionPlan:'Plan d\'exécution',personalSizing:'TAILLE PERSONNELLE',positionPlan:'Plan de position',trialComplete:'Essai terminé',trialCompleteCopy:'Tu as utilisé 5 signaux gratuits. Abonne-toi pour continuer à recevoir de nouveaux setups.',unlockSignals:'Débloquer les signaux',marketOffline:'BingX HORS LIGNE',bullish:'HAUSSIER',bearish:'BAISSIER',marketView:'VUE DU MARCHÉ',legendEntry:'Entrée',legendStop:'Stop',legendTargets:'TP1 / TP2',trendLabel:'TENDANCE',setupLabel:'SETUP',timeframeLabel:'UNITÉ DE TEMPS',requestPlan:'Demander un plan',payExact:'Montant exact',copyAddress:'Copier',txHash:'Hash de transaction',submitHash:'Envoyer le hash',paymentFailed:'Paiement non confirmé. Vérifie le hash et réessaie.',retryPayment:'Réessayer',accessOpen:'Accès ouvert',accessOpenCopy:'L\'accès est ouvert sur cet écran.',listing:'Listing',copied:'Adresse copiée',filterEmpty:'Aucun signal {side} dans ce filtre.',saveFailed:'Impossible d\'enregistrer les paramètres.',settingsAccessCopy:'L\'accès est ouvert. Un nouveau paiement n\'est pas nécessaire.',levCapped:'Le levier a été réduit au maximum BingX de ce marché.',minContract:'Le contrat minimum BingX est trop grand pour ce risque. N\'ouvre pas le trade.',sizeDisclaimer:'Le bot calcule la taille. Tu passes l\'ordre.',regimeLabel:'Régime',network:'Réseau',flat:'Plat',regimeTrend:'Tendance',regimeRange:'Range',needAccess:'Accès requis',openMexc:'Copier le setup',copiedSetup:'Setup copié',confidenceNote:'Estimation des règles, pas une probabilité.',tf1d:'Tendance 1J',tf4h:'Tendance 4H',tfStruct:'Structure 4H',languageLabel:'Langue',paymentWaiting:'En attente de la vérification',paymentMismatch:'Ça ne correspond pas.',accessOpenUntil:'Accès ouvert jusqu\'au {date}.',scannerSilent:'Le scanner est resté silencieux.',lastScan:'Dernier scan {time}.',scanNever:'pas encore',ageMinute:'min',ageHour:'h',ageDay:'j'},
  es:{btcChart:'MERCADO DE BITCOIN',majorTrades:'OPERACIONES BTC, ETH Y SOL',waitingSetup:'Esperando un setup 4H/1D',workspace:'ESPACIO PRIVADO',hello:'Hola',marketLive:'BingX EN VIVO',deposit:'Depósito',riskTrade:'Riesgo / operación',leverage:'Apalancamiento',access:'Acceso',cross:'Cruzado',isolated:'Aislado',scanner:'ESCÁNER DE MERCADO',latestSignals:'Últimas señales',viewAll:'Ver todas',signalHistory:'Historial de señales',all:'Todas',riskProfile:'PERFIL DE RIESGO',settings:'Ajustes',depositUsdt:'Depósito, USDT',riskPercent:'Riesgo por operación, %',leverageX:'Apalancamiento',marginMode:'Modo de margen',saveSettings:'Guardar',subscription:'SUSCRIPCIÓN',monthlyAccess:'Acceso mensual',subscriptionCopy:'Señales automáticas, escáner y planes completos.',paymentInstructions:'Instrucciones de pago',overview:'Resumen',signals:'Señales',trial:'Prueba',signalsLeft:'señales restantes',active:'Activo',inactive:'Inactivo',entry:'Entrada',stop:'Stop',confidence:'Confianza',saved:'Ajustes guardados',paymentHelp:'Abriendo las instrucciones de pago en el bot...',paymentUnavailable:'No se pudo abrir el bot. Cierra la aplicación y envía /subscribe.',noSignals:'Aún no hay señales',noSetupFor:'No hay setup para {symbol}.',currentPrice:'Precio actual',tp1:'TP1',tp2:'TP2',positionSize:'Tamaño de posición',marginRequired:'Margen necesario',stopRisk:'Riesgo al stop',backToSignals:'Volver a señales',tradeSetup:'CONFIGURACIÓN',livePrice:'PRECIO EN VIVO',signalLevels:'NIVELES DE SEÑAL',executionPlan:'Plan de ejecución',personalSizing:'TAMAÑO PERSONAL',positionPlan:'Plan de posición',trialComplete:'Prueba finalizada',trialCompleteCopy:'Has usado 5 señales gratis. Suscríbete para seguir recibiendo nuevos setups.',unlockSignals:'Desbloquear señales',marketOffline:'BingX SIN CONEXIÓN',bullish:'ALCISTA',bearish:'BAJISTA',marketView:'VISTA DEL MERCADO',legendEntry:'Entrada',legendStop:'Stop',legendTargets:'TP1 / TP2',trendLabel:'TENDENCIA',setupLabel:'SETUP',timeframeLabel:'MARCO TEMPORAL',requestPlan:'Pedir un plan',payExact:'Importe exacto',copyAddress:'Copiar',txHash:'Hash de la transacción',submitHash:'Enviar hash',paymentFailed:'El pago no se confirmó. Revisa el hash e inténtalo de nuevo.',retryPayment:'Reintentar',accessOpen:'Acceso abierto',accessOpenCopy:'El acceso está abierto en esta pantalla.',listing:'Listing',copied:'Dirección copiada',filterEmpty:'No hay señales {side} en este filtro.',saveFailed:'No se pudieron guardar los ajustes.',settingsAccessCopy:'El acceso está abierto. No hace falta pagar otra vez.',levCapped:'El apalancamiento se redujo al máximo de BingX para este mercado.',minContract:'El contrato mínimo BingX es demasiado grande para este riesgo. No abras la operación.',sizeDisclaimer:'El bot calcula el tamaño. La orden la pones tú.',regimeLabel:'Régimen',network:'Red',flat:'Plano',regimeTrend:'Tendencia',regimeRange:'Rango',needAccess:'Hace falta acceso',openMexc:'Copiar el setup',copiedSetup:'Setup copiado',confidenceNote:'Estimación de reglas, no una probabilidad.',tf1d:'Tendencia 1D',tf4h:'Tendencia 4H',tfStruct:'Estructura 4H',languageLabel:'Idioma',paymentWaiting:'Esperando la comprobación',paymentMismatch:'No coincidió.',accessOpenUntil:'Acceso abierto hasta {date}.',scannerSilent:'El escáner estuvo en silencio.',lastScan:'Último escaneo {time}.',scanNever:'aún no',ageMinute:'min',ageHour:'h',ageDay:'d'}
};

Object.assign(translations.en,{tradeNumber:'Trade',signalFrom:'Signal from',statusReplaying:'Restoring history',statusWaiting:'Waiting for entry',statusActive:'Trade active',statusTp1:'TP1 reached',statusTp2:'TP2 reached',statusStopped:'Stopped',statusExpired:'Expired',actionNow:'ACTION NOW',takeHalf:'Take profit on 50% of the position',moveBreakeven:'Move the Stop on the remainder to break-even',beReference:'Break-even reference',actualEntryNote:'If your actual fill differed, use your own entry price.'});
Object.assign(translations.ru,{tradeNumber:'Сделка',signalFrom:'Сигнал от',statusReplaying:'Восстанавливаем историю',statusWaiting:'Ожидает входа',statusActive:'Сделка активна',statusTp1:'TP1 достигнут',statusTp2:'TP2 достигнут',statusStopped:'Закрыта по Stop',statusExpired:'Сигнал истёк',actionNow:'ДЕЙСТВИЕ СЕЙЧАС',takeHalf:'Зафиксируйте 50% позиции',moveBreakeven:'Перенесите Stop оставшейся позиции в безубыток',beReference:'Ориентир БУ',actualEntryNote:'Если ваша фактическая цена входа отличалась, используйте свою цену.'});
Object.assign(translations.de,{tradeNumber:'Trade',signalFrom:'Signal vom',statusReplaying:'Verlauf wird rekonstruiert',statusWaiting:'Wartet auf Einstieg',statusActive:'Trade aktiv',statusTp1:'TP1 erreicht',statusTp2:'TP2 erreicht',statusStopped:'Am Stop beendet',statusExpired:'Abgelaufen',actionNow:'JETZT HANDELN',takeHalf:'50% der Position sichern',moveBreakeven:'Stop der Restposition auf Einstand setzen',beReference:'Einstand-Referenz',actualEntryNote:'Bei abweichender Ausführung den eigenen Einstieg verwenden.'});
Object.assign(translations.fr,{tradeNumber:'Trade',signalFrom:'Signal du',statusReplaying:'Historique en cours',statusWaiting:'En attente d’entrée',statusActive:'Trade actif',statusTp1:'TP1 atteint',statusTp2:'TP2 atteint',statusStopped:'Clôturé au Stop',statusExpired:'Expiré',actionNow:'ACTION MAINTENANT',takeHalf:'Prenez vos bénéfices sur 50% de la position',moveBreakeven:'Déplacez le Stop du solde au seuil de rentabilité',beReference:'Référence du seuil',actualEntryNote:'Si votre exécution diffère, utilisez votre prix d’entrée réel.'});
Object.assign(translations.es,{tradeNumber:'Operación',signalFrom:'Señal del',statusReplaying:'Restaurando historial',statusWaiting:'Esperando entrada',statusActive:'Operación activa',statusTp1:'TP1 alcanzado',statusTp2:'TP2 alcanzado',statusStopped:'Cerrada por Stop',statusExpired:'Expirada',actionNow:'ACCIÓN AHORA',takeHalf:'Asegura el 50% de la posición',moveBreakeven:'Mueve el Stop del resto al punto de equilibrio',beReference:'Referencia de equilibrio',actualEntryNote:'Si tu ejecución fue distinta, usa tu precio de entrada real.'});
Object.assign(translations.en,{tradeClosed:'TRADE CLOSED',tradeCancelled:'The setup is cancelled. Do not re-enter it.',waitNewSignal:'Wait for a new signal. Its new entry, Stop, TP1 and TP2 will appear here.'});
Object.assign(translations.ru,{tradeClosed:'СДЕЛКА ЗАКРЫТА',tradeCancelled:'Сетап аннулирован. Не входите повторно.',waitNewSignal:'Дождитесь нового сигнала. Здесь появятся его новые вход, Stop, TP1 и TP2.'});
Object.assign(translations.de,{tradeClosed:'TRADE GESCHLOSSEN',tradeCancelled:'Das Setup ist aufgehoben. Nicht erneut einsteigen.',waitNewSignal:'Warte auf ein neues Signal. Der neue Einstieg, Stop, TP1 und TP2 erscheinen hier.'});
Object.assign(translations.fr,{tradeClosed:'TRADE CLÔTURÉ',tradeCancelled:'Le setup est annulé. Ne rentrez pas à nouveau.',waitNewSignal:'Attendez un nouveau signal. Sa nouvelle entrée, son Stop, TP1 et TP2 apparaîtront ici.'});
Object.assign(translations.es,{tradeClosed:'OPERACIÓN CERRADA',tradeCancelled:'El setup queda anulado. No vuelvas a entrar.',waitNewSignal:'Espera una nueva señal. Aquí aparecerán su nueva entrada, Stop, TP1 y TP2.'});
Object.assign(translations.en,{referralOffer:'BINGX REFERRAL OFFER',referralTitle:'Access for 10 USDT',referralCopy:'Register through our BingX link, then submit your numeric UID. BingX verifies it automatically.',registerBingx:'Register on BingX',bingxUid:'BingX UID',submitReferral:'Verify UID',referralNone:'The discount is activated after automatic verification by BingX.',referralPending:'BingX is temporarily unavailable. Your UID is waiting for manual review.',referralVerified:'Referral verified. The 10 USDT price is active.',referralRejected:'UID was not found among our team’s direct referrals. Check it and submit again.',referralUidUsed:'This BingX UID is already linked to another Telegram account.',referralInvalid:'Enter a BingX UID containing 6–20 digits.',referralFailed:'Could not submit the UID. Try again.'});
Object.assign(translations.ru,{referralOffer:'ПРЕДЛОЖЕНИЕ ДЛЯ РЕФЕРАЛОВ BINGX',referralTitle:'Доступ за 10 USDT',referralCopy:'Зарегистрируйтесь по нашей ссылке BingX и отправьте цифровой UID. BingX проверит его автоматически.',registerBingx:'Регистрация на BingX',bingxUid:'BingX UID',submitReferral:'Проверить UID',referralNone:'Скидка включится после автоматической проверки BingX.',referralPending:'BingX временно недоступен. UID ожидает ручной проверки.',referralVerified:'Реферал подтверждён. Цена 10 USDT активна.',referralRejected:'UID не найден среди прямых рефералов нашей команды. Проверьте его и отправьте ещё раз.',referralUidUsed:'Этот BingX UID уже привязан к другому Telegram-аккаунту.',referralInvalid:'Введите BingX UID из 6–20 цифр.',referralFailed:'Не удалось отправить UID. Попробуйте ещё раз.'});
Object.assign(translations.de,{referralOffer:'BINGX-EMPFEHLUNG',referralTitle:'Zugang für 10 USDT',referralCopy:'Registriere dich über unseren BingX-Link und sende deine numerische UID. BingX prüft sie automatisch.',registerBingx:'Bei BingX registrieren',bingxUid:'BingX UID',submitReferral:'UID prüfen',referralNone:'Der Rabatt wird nach der automatischen BingX-Prüfung aktiviert.',referralPending:'BingX ist vorübergehend nicht verfügbar. Die UID wartet auf manuelle Prüfung.',referralVerified:'Empfehlung bestätigt. Der Preis von 10 USDT ist aktiv.',referralRejected:'Die UID wurde nicht unter den direkten Empfehlungen unseres Teams gefunden.',referralUidUsed:'Diese BingX UID ist bereits mit einem anderen Telegram-Konto verknüpft.',referralInvalid:'Gib eine BingX UID mit 6–20 Ziffern ein.',referralFailed:'UID konnte nicht gesendet werden.'});
Object.assign(translations.fr,{referralOffer:'OFFRE DE PARRAINAGE BINGX',referralTitle:'Accès pour 10 USDT',referralCopy:'Inscris-toi via notre lien BingX et envoie ton UID numérique. BingX le vérifiera automatiquement.',registerBingx:'S’inscrire sur BingX',bingxUid:'UID BingX',submitReferral:'Vérifier l’UID',referralNone:'La remise sera activée après vérification automatique par BingX.',referralPending:'BingX est temporairement indisponible. L’UID attend une vérification manuelle.',referralVerified:'Parrainage vérifié. Le tarif de 10 USDT est actif.',referralRejected:'L’UID ne figure pas parmi les filleuls directs de notre équipe.',referralUidUsed:'Cet UID BingX est déjà lié à un autre compte Telegram.',referralInvalid:'Saisis un UID BingX de 6 à 20 chiffres.',referralFailed:'Impossible d’envoyer l’UID.'});
Object.assign(translations.es,{referralOffer:'OFERTA PARA REFERIDOS DE BINGX',referralTitle:'Acceso por 10 USDT',referralCopy:'Regístrate mediante nuestro enlace de BingX y envía tu UID numérico. BingX lo verificará automáticamente.',registerBingx:'Registrarse en BingX',bingxUid:'UID de BingX',submitReferral:'Verificar UID',referralNone:'El descuento se activará tras la verificación automática de BingX.',referralPending:'BingX no está disponible temporalmente. El UID espera una revisión manual.',referralVerified:'Referido verificado. El precio de 10 USDT está activo.',referralRejected:'El UID no aparece entre los referidos directos de nuestro equipo.',referralUidUsed:'Este UID de BingX ya está vinculado a otra cuenta de Telegram.',referralInvalid:'Introduce un UID de BingX de 6–20 dígitos.',referralFailed:'No se pudo enviar el UID.'});

const taglines={
  en:'Setups, risk and execution — one screen.',
  ru:'Сетапы и риск — на одном экране.',
  de:'Setups, Risiko und Ausführung — auf einem Bildschirm.',
  fr:'Setups, risque et exécution — sur un seul écran.',
  es:'Setups, riesgo y ejecución — en una sola pantalla.'
};

let profile=null,signals=[],language='en',activeFilter='ALL',selectedSignal=null;
const pinnedNoSetup=(()=>{const raw=new URLSearchParams(window.location.search).get('no_setup')||'';const symbol=raw.trim().toUpperCase();return /^[A-Z0-9]{2,20}_USDT$/.test(symbol)?symbol:'';})();
const HOME_CHART_SYMBOL='BTC_USDT';
let overviewSymbol=HOME_CHART_SYMBOL,overviewTimeframe='4h',detailTimeframe='4h';
let chartFollowsSelectedSignal=false;
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
const coinBase=symbol=>AssetIcons.base(symbol).replace(/[^A-Z0-9]/g,'').slice(0,40);
function coinIconMarkup(symbol,assetType='crypto'){
  const path=AssetIcons.resolve(symbol,assetType);
  return `<span class="asset-icon"><span class="coin-fallback">${escapeHtml(coinBase(symbol).slice(0,2)||'?')}</span>${path?`<img data-asset-src="${escapeHtml(path)}" alt="" width="36" height="36" decoding="async">`:''}</span>`;
}

function hydrateCoinIcons(root=document){
  root.querySelectorAll('img[data-asset-src]').forEach(img=>{
    const path=img.dataset.assetSrc;
    delete img.dataset.assetSrc;
    img.addEventListener('load',()=>img.parentElement.classList.add('loaded'),{once:true});
    img.addEventListener('error',()=>img.remove(),{once:true});
    img.src=path;
  });
}

function applyLanguage(){
  document.documentElement.lang=language;
  document.querySelectorAll('[data-i18n]').forEach(element=>element.textContent=tr(element.dataset.i18n));
  $('#language').value=language;
  renderProfile();
  renderSignals();
  renderMajorMarkets();
  renderHome();
  paintPaymentState();
  const context=chartContext();
  syncChartIdentity(context.symbol);
  if(overviewChart){if(context.signal)addSignalLines(overviewChart,context.signal);else clearPriceLines(overviewChart);}
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
  const referralStatus=profile.bingx_referral_status||'none';
  const referralPending=referralStatus==='pending';
  if(title&&copy&&pay&&priceBlock){
    title.textContent=paid?tr('accessOpen'):tr('monthlyAccess');
    copy.textContent=paid?tr('settingsAccessCopy'):referralPending?tr('referralPending'):tr('subscriptionCopy');
    pay.hidden=paid||referralPending;
    priceBlock.hidden=paid||referralPending;
  }
  const referralForm=$('#referral-form');
  const referralNote=$('#referral-status');
  const referralInput=$('#bingx-uid');
  if(referralInput&&profile.bingx_referral_uid&&!referralInput.value)referralInput.value=profile.bingx_referral_uid;
  if(referralForm)referralForm.hidden=referralStatus==='pending'||referralStatus==='verified';
  if(referralNote){
    const key={pending:'referralPending',verified:'referralVerified',rejected:'referralRejected'}[referralStatus]||'referralNone';
    referralNote.textContent=tr(key);
    referralNote.dataset.status=referralStatus;
  }
}

function openBingxReferral(){
  const raw=String(profile?.bingx_referral_url||'');
  try{
    const url=new URL(raw);
    if(url.protocol!=='https:'||!(url.hostname==='bingx.com'||url.hostname.endsWith('.bingx.com')))throw new Error('unsafe referral URL');
    if(tg?.openLink)tg.openLink(url.toString());
    else window.open(url.toString(),'_blank','noopener');
  }catch(error){showToast(tr('referralFailed'))}
}

async function submitReferral(event){
  event.preventDefault();
  const input=$('#bingx-uid');
  const button=$('#referral-form button[type=submit]');
  const bingx_uid=input.value.trim();
  if(!/^\d{6,20}$/.test(bingx_uid)){showToast(tr('referralInvalid'));input.focus();return;}
  button.disabled=true;
  try{
    const response=await fetch('/api/bingx-referral',{method:'POST',headers,body:JSON.stringify({bingx_uid})});
    const body=await response.json().catch(()=>({}));
    if(!response.ok){showToast(tr(body.reason==='uid_used'?'referralUidUsed':'referralFailed'));return;}
    profile={...profile,bingx_referral_uid:bingx_uid,bingx_referral_status:body.status||'pending'};
    renderProfile();
    const toastKey={verified:'referralVerified',rejected:'referralRejected',pending:'referralPending'}[profile.bingx_referral_status]||'referralPending';
    showToast(tr(toastKey));
  }catch(error){showToast(tr('referralFailed'))}
  finally{button.disabled=false;}
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

function signalDate(signal){
  const value=new Date(signal?.created_at);
  if(!Number.isFinite(value.valueOf()))return '—';
  return `${value.toLocaleString(language,{timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false})} UTC`;
}

function signalStatus(signal){
  const status=String(signal?.trade_status||'untracked');
  const keys={replay_pending:'statusReplaying',waiting_entry:'statusWaiting',active:'statusActive',tp1_reached:'statusTp1',tp2_reached:'statusTp2',stopped:'statusStopped',expired:'statusExpired'};
  return{status,label:keys[status]?tr(keys[status]):''};
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
  const state=signalStatus(signal);
  return `<button type="button" class="signal-row" data-signal-id="${signalId}" data-side="${side}"><span class="instrument-identity"><span class="coin-dot" aria-hidden="true">${coinIconMarkup(signal.symbol,signal.asset_type)}</span><span class="instrument-copy"><strong>${symbol}</strong><small>#${signalId} · ${escapeHtml(signalDate(signal))}</small></span></span><span class="side ${side.toLowerCase()}">${side}</span><b>${escapeHtml(rewardRisk(signal))}</b><small class="trade-state ${escapeHtml(state.status)}">${escapeHtml(state.label||signalAge(signal))}</small></button>`;
}

function emptySignals(filterOnly){
  const reason=filterOnly?tr('filterEmpty').split('{side}').join(activeFilter):tr('scannerSilent');
  const action=filterOnly?'':`<button type="button" class="primary-button empty-action" data-empty-action="plan">${escapeHtml(tr('requestPlan'))}</button>`;
  return `<div class="empty-state"><p>${escapeHtml(reason)}</p><p>${escapeHtml(lastScanLine())}</p>${action}</div>`;
}

const BASE_OVERVIEW_SYMBOLS=['BTC_USDT','ETH_USDT','SOL_USDT'];
const ACTIVE_SETUP_MAX_AGE_MS=12*60*60*1000;

function latestMajorSignal(symbol,{activeOnly=false}={}){
  return signals.find(signal=>{
    if(!isSetup(signal)||String(signal.symbol||'').toUpperCase()!==symbol)return false;
    if(!activeOnly)return true;
    if(!isOpenSetup(signal))return false;
    const createdAt=new Date(signal.created_at).valueOf();
    return Number.isFinite(createdAt)&&Date.now()-createdAt<=ACTIVE_SETUP_MAX_AGE_MS;
  })||null;
}

function preferredSignal(){
  for(const symbol of BASE_OVERVIEW_SYMBOLS){
    const signal=latestMajorSignal(symbol,{activeOnly:true});
    if(signal)return signal;
  }
  return signals.find(isOpenSetup)||null;
}

function chartContext(){
  if(chartFollowsSelectedSignal&&selectedSignal&&isSetup(selectedSignal)){
    return{symbol:String(selectedSignal.symbol).toUpperCase(),signal:isOpenSetup(selectedSignal)?selectedSignal:null};
  }
  return{symbol:HOME_CHART_SYMBOL,signal:latestMajorSignal(HOME_CHART_SYMBOL,{activeOnly:true})};
}

function syncChartIdentity(symbol){
  const normalized=String(symbol||HOME_CHART_SYMBOL).toUpperCase();
  const title=$('#chart-title');
  if(title){title.removeAttribute('data-i18n');title.textContent=!chartFollowsSelectedSignal&&normalized===HOME_CHART_SYMBOL?tr('btcChart'):displaySymbol(normalized);}
  const coin=$('#chart-coin');
  if(coin&&coin.dataset.symbol!==normalized){coin.dataset.symbol=normalized;coin.innerHTML=coinIconMarkup(normalized);hydrateCoinIcons(coin);}
  const chart=$('#chart');
  if(chart)chart.setAttribute('aria-label',`${displaySymbol(normalized)} price chart`);
}

function renderMajorMarkets(){
  const list=$('#major-market-list');
  if(!list)return;
  list.innerHTML=BASE_OVERVIEW_SYMBOLS.map(symbol=>{
    const signal=latestMajorSignal(symbol,{activeOnly:true});
    const content=signal
      ? `<span class="side ${String(signal.side).toLowerCase()}">${escapeHtml(String(signal.side).toUpperCase())}</span><b>${escapeHtml(rewardRisk(signal))}</b><small>${escapeHtml(signalAge(signal))}</small>`
      : `<span class="major-waiting">${escapeHtml(tr('waitingSetup'))}</span>`;
    const signalId=signal&&Number.isSafeInteger(Number(signal.id))?` data-signal-id="${Number(signal.id)}"`:'';
    return `<button type="button" class="major-market-card${signal?' active-setup':' waiting'}"${signalId}${signal?'':' disabled'}><span class="instrument-identity"><span class="coin-dot" aria-hidden="true">${coinIconMarkup(symbol)}</span><strong>${escapeHtml(displaySymbol(symbol))}</strong></span>${content}</button>`;
  }).join('');
  hydrateCoinIcons(list);
}

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
  // The overview preview uses a light canvas, independently of other views.
  if(container.id==='chart'){
    chart.applyOptions({layout:{background:{type:'solid',color:'#ffffff'},textColor:'#65738a',fontSize:11},grid:{vertLines:{visible:false},horzLines:{color:'#f0f3f8'}},rightPriceScale:{borderVisible:false},timeScale:{borderColor:'#edf0f5'},crosshair:{vertLine:{color:'#aab6cb',labelBackgroundColor:'#526482'},horzLine:{color:'#aab6cb',labelBackgroundColor:'#526482'}}});
    candles.applyOptions({upColor:'#15977b',downColor:'#d65c70',wickUpColor:'#15977b',wickDownColor:'#d65c70'});
  }
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
const TERMINAL_TRADE_STATUSES=new Set(['stopped','tp2_reached','expired']);
function isSetup(signal){
  return !ALERT_SOURCES.has(String(signal?.source||'').toLowerCase());
}
function isOpenSetup(signal){
  return isSetup(signal)&&!TERMINAL_TRADE_STATUSES.has(String(signal?.trade_status||'untracked'));
}
function homeSignal(){
  if(selectedSignal&&isSetup(selectedSignal))return selectedSignal;
  if(pinnedNoSetup)return null;
  return preferredSignal();
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
  if(empty){
    empty.hidden=Boolean(signal);
    const note=empty.querySelector('p');
    const action=empty.querySelector('[data-empty-action]');
    if(!signal&&pinnedNoSetup){
      if(note)note.textContent=tr('noSetupFor').split('{symbol}').join(displaySymbol(pinnedNoSetup));
      if(action)action.hidden=true;
    }else if(!signal){
      if(note)note.textContent=tr('noSignals');
      if(action)action.hidden=false;
    }
  }
  if(body)body.hidden=!signal;
  if(!signal)return;
  const side=String(signal.side||'').toUpperCase()==='SHORT'?'SHORT':'LONG';
  const sideNode=$('#plan-side');
  if(sideNode){sideNode.textContent=side;sideNode.className=`side ${side.toLowerCase()}`;}
  const symbolNode=$('#plan-symbol');
  if(symbolNode)symbolNode.textContent=displaySymbol(signal.symbol);
  const priceNode=$('#plan-price');
  if(priceNode)priceNode.textContent=signal.price==null?'—':`${fmt(signal.price)} USDT`;
  const confidence=$('#plan-confidence');
  if(confidence)confidence.textContent=`${tr('confidence')} ${confidenceLabel(signal)} · ${tr('confidenceNote')}`;
  const reference=$('#plan-reference');
  if(reference)reference.textContent=`${tr('tradeNumber')} #${Number(signal.id)} · ${tr('signalFrom')} ${signalDate(signal)}`;
  const headingCoin=$('#plan-heading-coin');
  if(headingCoin){headingCoin.innerHTML=coinIconMarkup(signal.symbol,signal.asset_type);hydrateCoinIcons(headingCoin);}
  const sizing=signal.sizing||{};
  const notes=[];
  const requested=Number(sizing.requested_leverage);
  const effective=Number(sizing.effective_leverage);
  if(Number.isFinite(requested)&&Number.isFinite(effective)&&effective<requested)notes.push(tr('levCapped'));
  if(Array.isArray(sizing.errors)&&sizing.errors.includes('position_below_min_contract'))notes.push(tr('minContract'));
  const caveat=$('#plan-caveat');
  if(caveat){caveat.hidden=!notes.length;caveat.textContent=notes.join(' ');}
  const metrics=signalMetrics(signal);
  const levels=$('#plan-levels');
  if(levels)levels.innerHTML=[
    detailMetric(tr('entry'),fmt(signal.entry),'entry'),
    detailMetric(tr('stop'),fmt(signal.stop),'risk'),
    detailMetric(tr('tp1'),fmt(signal.tp1),'target'),
    detailMetric(tr('tp2'),fmt(signal.tp2),'target'),
  ].join('');
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
  const action=$('#plan-action');
  const state=signalStatus(signal);
  if(action){
    const stopped=state.status==='stopped';
    action.hidden=state.status!=='tp1_reached'&&!stopped;
    action.classList.toggle('cancelled',stopped);
    const kicker=action.querySelector(':scope>p');
    const status=$('#plan-action-status');
    const steps=$('#plan-action-steps');
    const note=$('#plan-action-note');
    if(kicker)kicker.textContent=stopped?tr('tradeClosed'):tr('actionNow');
    if(status)status.textContent=state.label;
    if(steps)steps.innerHTML=stopped
      ?`<li>${escapeHtml(tr('tradeCancelled'))}</li><li>${escapeHtml(tr('waitNewSignal'))}</li>`
      :`<li>${escapeHtml(tr('takeHalf'))}</li><li>${escapeHtml(tr('moveBreakeven'))}</li><li>${escapeHtml(tr('beReference'))}: <strong>${escapeHtml(fmt(signal.entry))}</strong></li>`;
    if(note){note.hidden=stopped;note.textContent=stopped?'':tr('actualEntryNote');}
  }
}
async function loadHomeChart(){
  const frame=$('#chart-frame');
  const context=chartContext();
  const signal=context.signal;
  frame?.classList.add('loading');
  overviewSymbol=context.symbol;
  syncChartIdentity(overviewSymbol);
  try{
    const data=await api(`/api/market/${overviewSymbol}?timeframe=${overviewTimeframe}`);
    if(!overviewChart)overviewChart=chartBundle($('#chart'),310);
    setChartData(overviewChart,data);
    if(signal)addSignalLines(overviewChart,signal);
    else clearPriceLines(overviewChart);
    const last=data.at(-1);
    const price=$('#chart-price');
    if(price){price.textContent=`${fmt(last?.close)} USDT`;price.classList.remove('negative');}
    const regime=$('#chart-regime');
    if(regime)regime.textContent=signal?regimeLine(signal):`BingX · ${displaySymbol(overviewSymbol).replaceAll(' ','')}`;
    const frameLabel=$('#chart-timeframe');
    if(frameLabel)frameLabel.textContent=overviewTimeframe.toUpperCase();
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
  chartFollowsSelectedSignal=true;
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
  const params=new URLSearchParams(window.location.search);
  const hashParams=new URLSearchParams(window.location.hash.replace(/^#/,''));
  const candidates=[
    params.get('signal_id'),
    params.get('tgWebAppStartParam'),
    tg?.initDataUnsafe?.start_param,
    hashParams.get('signal_id')
  ];
  for(const candidate of candidates){
    const match=String(candidate||'').match(/^(?:signal(?:_id)?[_=-]?)?(\d+)$/i);
    const id=Number(match?.[1]||'');
    if(Number.isSafeInteger(id)&&id>0)return id;
  }
  return 0;
}
async function load(){
  try{
    const requested=pinnedNoSetup?0:signalIdFromLocation();
    const signalsUrl=requested?`/api/signals?signal_id=${encodeURIComponent(requested)}`:'/api/signals';
    [profile,signals]=await Promise.all([api('/api/me'),api(signalsUrl)]);
    signals=signals.filter(signal=>isUsdtPair(signal.symbol)&&isSetup(signal));
    language=profile.language||'en';
    selectedSignal=requested?signals.find(signal=>Number(signal.id)===requested)||null:null;
    chartFollowsSelectedSignal=Boolean(requested&&selectedSignal);
    if(!selectedSignal&&!pinnedNoSetup)selectedSignal=preferredSignal();
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
    if(selectedSignal){
      const previous=selectedSignal;
      const refreshed=signals.find(signal=>String(signal.id)===String(previous.id))||null;
      if(refreshed)selectedSignal=refreshed;
      else if(chartFollowsSelectedSignal){
        const previousSymbol=String(previous.symbol||'').toUpperCase();
        selectedSignal=signals.find(signal=>String(signal.symbol||'').toUpperCase()===previousSymbol&&isOpenSetup(signal))||previous;
      }else selectedSignal=null;
    }
    if(chartFollowsSelectedSignal&&selectedSignal&&!isOpenSetup(selectedSignal)){
      const stoppedSymbol=String(selectedSignal.symbol||'').toUpperCase();
      const replacement=signals.find(signal=>String(signal.symbol||'').toUpperCase()===stoppedSymbol&&isOpenSetup(signal));
      if(replacement){selectedSignal=replacement;selectTimeframe(replacement.timeframe||'4h');}
    }
    if(!selectedSignal&&!pinnedNoSetup)selectedSignal=preferredSignal();
    renderProfile();
    renderSignals();
    renderMajorMarkets();
    renderHome();
    await loadHomeChart();
  }catch(error){}
}
document.querySelectorAll('.bottom-nav button').forEach(button=>button.addEventListener('click',async()=>{showView(button.dataset.target);if(button.dataset.target==='overview'&&chartFollowsSelectedSignal){chartFollowsSelectedSignal=false;selectTimeframe('4h');renderHome();await loadHomeChart();}}));
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
$('#settings-form').addEventListener('submit',async event=>{event.preventDefault();const payload={deposit:Number($('#deposit-input').value),risk_pct:Number($('#risk-input').value),leverage:Number($('#leverage-input').value),margin:document.querySelector('input[name=margin]:checked').value};const status=$('#form-status');try{await api('/api/settings',{method:'PATCH',body:JSON.stringify(payload)});Object.assign(profile,payload);const selectedId=selectedSignal?.id;signals=(await api('/api/signals')).filter(signal=>isUsdtPair(signal.symbol)&&isSetup(signal));selectedSignal=pinnedNoSetup&&!selectedId?null:(selectedId?signals.find(signal=>Number(signal.id)===Number(selectedId))||(pinnedNoSetup?null:preferredSignal()):preferredSignal());renderProfile();renderSignals();renderMajorMarkets();renderHome();status.classList.remove('error');status.textContent=tr('saved');showToast(tr('saved'))}catch(error){status.classList.add('error');status.textContent=tr('saveFailed');showToast(tr('saveFailed'))}});
$('#bingx-referral-link').addEventListener('click',openBingxReferral);
$('#referral-form').addEventListener('submit',submitReferral);
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
  $('#payment-details').hidden=false;
  $('#payment-title').hidden=false;
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
  $('#payment-details').hidden=true;
  $('#payment-title').hidden=true;
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
let paymentReturnFocus=null;
function closePayment(){
  $('#payment-sheet').hidden=true;
  document.body.classList.remove('payment-open');
  document.querySelectorAll('.topbar,main,.bottom-nav').forEach(node=>node.inert=false);
  if(paymentReturnFocus?.getClientRects().length)paymentReturnFocus.focus();
  else document.querySelector('.bottom-nav button.active')?.focus();
}
async function openPayment(){
  const sheet=$('#payment-sheet');
  if(!sheet)return;
  paymentReturnFocus=document.activeElement;
  sheet.hidden=false;
  document.body.classList.add('payment-open');
  document.querySelectorAll('.topbar,main,.bottom-nav').forEach(node=>node.inert=true);
  $('#payment-close').setAttribute('aria-label',({ru:'Закрыть',en:'Close',de:'Schließen',fr:'Fermer',es:'Cerrar'})[language]||'Close');
  $('#payment-close').focus();
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
async function submitPayment(event){
  event.preventDefault();
  const submit=$('#payment-form button[type=submit]');
  if(submit.disabled)return;
  submit.disabled=true;
  $('#payment-form').setAttribute('aria-busy','true');
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
  }catch(error){
    showPaymentError(tr('paymentFailed'));
  }finally{
    submit.disabled=false;
    $('#payment-form').removeAttribute('aria-busy');
  }
}
$('#payment-button').addEventListener('click',openPayment);
document.querySelectorAll('.paywall-button').forEach(button=>button.addEventListener('click',openPayment));
$('#payment-copy').addEventListener('click',copyPaymentAddress);
$('#payment-form').addEventListener('submit',submitPayment);
$('#payment-retry').addEventListener('click',()=>{showPaymentForm();$('#payment-hash').focus()});
$('#payment-close').addEventListener('click',closePayment);
$('#payment-sheet').addEventListener('click',event=>{if(event.target.id==='payment-sheet')closePayment()});
document.addEventListener('keydown',event=>{
  if($('#payment-sheet').hidden)return;
  if(event.key==='Escape'){event.preventDefault();closePayment();return;}
  if(event.key!=='Tab')return;
  const controls=[...$('#payment-panel').querySelectorAll('button:not(:disabled),input:not(:disabled)')].filter(el=>el.getClientRects().length);
  const first=controls[0],last=controls[controls.length-1];
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
  else if(!event.shiftKey&&(document.activeElement===last||!controls.includes(document.activeElement))){event.preventDefault();first?.focus();}
});
$('#refresh').addEventListener('click',async()=>{await load()});
window.addEventListener('resize',()=>{if(overviewChart)overviewChart.chart.applyOptions({width:overviewChart.container.clientWidth,height:overviewChart.container.clientHeight})});
tg?.setHeaderColor?.('#f5f7fb');
tg?.setBackgroundColor?.('#f5f7fb');
load();
setInterval(refreshLiveData,60000);
