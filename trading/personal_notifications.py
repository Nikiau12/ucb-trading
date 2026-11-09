"""One identity and layout for price events and confirmed personal fills."""
import html
from trading.signal_updates import signal_identity_footer

_COPY = {
 'en': {
  'enter': "I'm in the trade", 'exit': "I've exited", 'tracking_on':'Trade updates enabled', 'tracking_off':'Trade updates stopped',
  'tracking_failed':'This trade cannot be tracked. Open the current signal in the app.',
  'removed':'Scalp and SMC signals have been removed. Use /plan or /scan.',
  'balance_unavailable':'BingX balance is unavailable. Position calculation is paused; check the connection in Settings.',
  'balance_managed':'Balance is updated from BingX. Manage the connection in Settings.',
  'universe_unavailable':'Capitalization ranking is temporarily unavailable. Please try again later.',
  'outside_selection':'This coin is outside the top-100 or your selected groups. Change groups in Signals.',
  'tp1_reached':'Signal price reached TP1', 'tp2_reached':'Signal price reached TP2',
  'stop_reached':'Signal price reached the stop level', 'cancelled_before_entry':'Signal no longer valid',
  'cancel_note':'This is a signal status, not a record of your order. Check any open position separately on BingX.',
  'tp1_filled':'Your BingX TP1 order was filled',
  'price_note':'Price event from the signal. Your order execution is checked separately.',
  'filled_note':'Confirmed by your linked BingX order.',
  'be':'Check the remaining position and move its stop to your actual entry price.',
 },
 'ru': {
  'enter':'Я в сделке', 'exit':'Я вышел', 'tracking_on':'Сопровождение включено', 'tracking_off':'Сопровождение прекращено',
  'tracking_failed':'Эту сделку сейчас нельзя подключить. Откройте актуальный сигнал в приложении.',
  'removed':'Скальпы и SMC-сигналы удалены. Используйте /plan или /scan.',
  'balance_unavailable':'Баланс BingX недоступен. Расчёт позиции приостановлен; проверьте подключение в настройках.',
  'balance_managed':'Баланс обновляется из BingX. Подключение доступно в настройках.',
  'universe_unavailable':'Рейтинг капитализации временно недоступен. Попробуйте позже.',
  'outside_selection':'Монета вне топ-100 или выбранных групп. Изменить группы можно в «Сигналах».',
  'tp1_reached':'Цена сигнала достигла TP1', 'tp2_reached':'Цена сигнала достигла TP2',
  'stop_reached':'Цена сигнала достигла уровня стопа', 'cancelled_before_entry':'Сигнал больше не актуален',
  'cancel_note':'Это статус сигнала, а не запись о вашем ордере. Открытую позицию проверьте отдельно в BingX.',
  'tp1_filled':'Ваш ордер TP1 в BingX исполнен',
  'price_note':'Событие по цене сигнала. Исполнение вашего ордера проверяется отдельно.',
  'filled_note':'Подтверждено по связанному ордеру вашего аккаунта BingX.',
  'be':'Проверьте остаток позиции и перенесите его стоп на вашу фактическую цену входа.',
 },
 'de': {
  'enter':'Ich bin im Trade', 'exit':'Ich bin ausgestiegen', 'tracking_on':'Trade-Updates aktiviert', 'tracking_off':'Trade-Updates beendet',
  'tracking_failed':'Dieser Trade kann derzeit nicht verfolgt werden. Öffne das aktuelle Signal.',
  'removed':'Scalp- und SMC-Signale wurden entfernt. Nutze /plan oder /scan.',
  'balance_unavailable':'BingX-Guthaben nicht verfügbar. Positionsberechnung pausiert; prüfe die Verbindung in den Einstellungen.',
  'balance_managed':'Das Guthaben wird von BingX aktualisiert.',
  'universe_unavailable':'Die Rangliste nach Marktkapitalisierung ist vorübergehend nicht verfügbar.',
  'outside_selection':'Dieser Coin liegt außerhalb der Top 100 oder deiner ausgewählten Gruppen.',
  'tp1_reached':'Signalpreis hat TP1 erreicht', 'tp2_reached':'Signalpreis hat TP2 erreicht',
  'stop_reached':'Signalpreis hat das Stop-Niveau erreicht', 'cancelled_before_entry':'Signal nicht mehr gültig',
  'cancel_note':'Dies ist ein Signalstatus, kein Nachweis deiner Order. Prüfe eine offene Position separat auf BingX.',
  'tp1_filled':'Deine BingX-TP1-Order wurde ausgeführt',
  'price_note':'Ereignis zum Signalpreis. Die Orderausführung wird separat geprüft.',
  'filled_note':'Durch deine verknüpfte BingX-Order bestätigt.',
  'be':'Prüfe die Restposition und verschiebe ihren Stop auf deinen tatsächlichen Einstiegspreis.',
 },
 'fr': {
  'enter':'Je suis en position', 'exit':'Je suis sorti', 'tracking_on':'Suivi activé', 'tracking_off':'Suivi arrêté',
  'tracking_failed':'Ce trade ne peut pas être suivi actuellement. Ouvre le signal dans l’application.',
  'removed':'Les signaux scalp et SMC sont supprimés. Utilise /plan ou /scan.',
  'balance_unavailable':'Solde BingX indisponible. Calcul suspendu ; vérifie la connexion dans les réglages.',
  'balance_managed':'Le solde est actualisé depuis BingX.',
  'universe_unavailable':'Le classement par capitalisation est temporairement indisponible.',
  'outside_selection':'Cette monnaie est hors du top 100 ou des groupes sélectionnés.',
  'tp1_reached':'Le prix du signal a atteint TP1', 'tp2_reached':'Le prix du signal a atteint TP2',
  'stop_reached':'Le prix du signal a atteint le stop', 'cancelled_before_entry':'Signal non valable',
  'cancel_note':'Il s’agit du statut du signal, pas de votre ordre. Vérifiez toute position ouverte séparément sur BingX.',
  'tp1_filled':'Votre ordre TP1 BingX a été exécuté',
  'price_note':'Événement lié au prix du signal. L’exécution de votre ordre est vérifiée séparément.',
  'filled_note':'Confirmé par votre ordre BingX associé.',
  'be':'Vérifiez la position restante et déplacez son stop sur votre prix d’entrée réel.',
 },
 'es': {
  'enter':'Estoy en la operación', 'exit':'He salido', 'tracking_on':'Seguimiento activado', 'tracking_off':'Seguimiento detenido',
  'tracking_failed':'No se puede seguir esta operación ahora. Abre la señal actual.',
  'removed':'Se eliminaron las señales scalp y SMC. Usa /plan o /scan.',
  'balance_unavailable':'Saldo BingX no disponible. Cálculo pausado; revisa la conexión en Ajustes.',
  'balance_managed':'El saldo se actualiza desde BingX.',
  'universe_unavailable':'El ranking por capitalización no está disponible temporalmente.',
  'outside_selection':'Esta moneda está fuera del top 100 o de tus grupos seleccionados.',
  'tp1_reached':'El precio de la señal alcanzó TP1', 'tp2_reached':'El precio de la señal alcanzó TP2',
  'stop_reached':'El precio de la señal alcanzó el stop', 'cancelled_before_entry':'Señal ya no válida',
  'cancel_note':'Es el estado de la señal, no un registro de tu orden. Comprueba cualquier posición abierta en BingX.',
  'tp1_filled':'Tu orden TP1 de BingX se ejecutó',
  'price_note':'Evento del precio de la señal. La ejecución de tu orden se comprueba por separado.',
  'filled_note':'Confirmado por tu orden BingX vinculada.',
  'be':'Comprueba la posición restante y mueve su stop a tu precio de entrada real.',
 },
}

for _lang, _text in {
    'en':'BingX futures balance is zero. Signal levels still arrive; position size is not calculated.',
    'ru':'Фьючерсный баланс BingX равен нулю. Уровни сигнала продолжают приходить; объём позиции не рассчитывается.',
    'de':'Das BingX-Futures-Guthaben ist null. Signalniveaus kommen weiter; die Positionsgröße wird nicht berechnet.',
    'fr':'Le solde futures BingX est nul. Les niveaux du signal arrivent toujours ; la taille de position n’est pas calculée.',
    'es':'El saldo de futuros BingX es cero. Seguirás recibiendo los niveles de señal; no se calcula el tamaño de posición.',
}.items():
    _COPY[_lang]['empty_balance'] = _text

for _lang, _text in {
    'en':'Calculation deposit is zero or not set. Signal levels still arrive; position size is not calculated.',
    'ru':'Расчётный депозит равен нулю или не указан. Уровни сигнала продолжают приходить; объём позиции не рассчитывается.',
    'de':'Das Berechnungskapital ist null oder nicht angegeben. Signalniveaus kommen weiter; die Positionsgröße wird nicht berechnet.',
    'fr':'Le capital de calcul est nul ou non indiqué. Les niveaux du signal arrivent toujours ; la taille de position n’est pas calculée.',
    'es':'El capital de cálculo es cero o no está indicado. Seguirás recibiendo los niveles de señal; no se calcula el tamaño de posición.',
}.items():
    _COPY[_lang]['no_deposit'] = _text

def personal_text(lang, key):
    return _COPY.get(lang, _COPY['en'])[key]

def render_update(signal, lang):
    from trading.group_labels import strategy_notice, cancellation_reason
    event = signal['event_type']
    if event not in ('tp1_reached','tp2_reached','tp1_filled','stop_reached','cancelled_before_entry'):
        raise ValueError('unsupported_event')
    title = personal_text(lang, event)
    identity = signal_identity_footer(int(signal['id']), signal['symbol'], signal['side'], lang=lang, created_at=signal.get('created_at'))
    if event == 'cancelled_before_entry':
        reason = cancellation_reason(signal, lang, '')
        lines = [f"<b>{html.escape(title)}</b>", identity]
        if reason:
            lines.append(html.escape(reason))
        lines.append(html.escape(personal_text(lang, 'cancel_note')))
        return '\n\n'.join(lines) + strategy_notice(signal, lang, details=False)
    key = 'tp2' if event=='tp2_reached' else ('stop' if event=='stop_reached' else 'tp1')
    value = signal.get('entry') if event=='stop_reached' and signal.get('tp1_hit_at') else signal.get(key)
    note = personal_text(lang, 'filled_note' if event=='tp1_filled' else 'price_note')
    lines = [f"<b>{html.escape(title)}</b>", identity, f"{key.upper()}: <code>{html.escape(str(value))}</code>", html.escape(note)]
    if event in ('tp1_reached','tp1_filled'):
        lines.append(html.escape(personal_text(lang, 'be')))
    return '\n\n'.join(lines) + strategy_notice(signal,lang,details=False)

def render_unpriced_signal(plan, lang, *, empty_balance=False, no_deposit=False):
    from trading.group_labels import strategy_notice
    primary = plan['primary']
    lines = [f"<b>{html.escape(str(plan['symbol']))} · {html.escape(str(primary['side']).upper())}</b>"]
    for label,value in [('Entry',primary.get('entry')),('Stop',primary.get('stop')),*[(f'TP{i+1}',tp.get('price')) for i,tp in enumerate(primary.get('tps',[]))]]:
        lines.append(f'{label}: <code>{html.escape(str(value))}</code>')
    note = 'empty_balance' if empty_balance else 'no_deposit' if no_deposit else 'balance_unavailable'
    lines.append(personal_text(lang,note))
    return '\n'.join(lines) + strategy_notice(plan,lang)
