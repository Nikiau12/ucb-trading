"""Explicit per-user opt-in and conservative exchange-order reconciliation."""
from __future__ import annotations
import math

try:
    from .bingx_account import account_client, AccountUnavailable
except ImportError:
    from bingx_account import account_client, AccountUnavailable


class TrackingError(ValueError):
    pass


def set_tracking(connection, user_id, signal_id, active):
    connection.execute("SELECT pg_advisory_xact_lock(20261107, hashtext(%s))", (str(user_id),))
    current = connection.execute("SELECT status FROM user_trade_tracking WHERE telegram_user_id=%s AND signal_id=%s FOR UPDATE", (user_id,signal_id)).fetchone()
    if not active:
        if not current:
            raise TrackingError('tracking_not_found')
        connection.execute("UPDATE user_trade_tracking SET status='exited',exited_at=NOW() WHERE telegram_user_id=%s AND signal_id=%s", (user_id,signal_id))
        connection.execute("UPDATE signal_update_deliveries SET status='sent',last_error='user_exited' WHERE telegram_user_id=%s AND signal_id=%s AND status IN ('pending','failed')", (user_id,signal_id))
        return {'tracking_status':'exited'}
    if current:
        if current[0] == 'active':
            return {'tracking_status':'active'}
        # Old entry buttons cannot re-enable notifications after an exit.
        raise TrackingError('already_exited')
    row = connection.execute("""SELECT s.symbol,s.side,l.status FROM signals s
        LEFT JOIN signal_lifecycle l ON l.signal_id=s.id
        WHERE s.id=%s AND s.source IN ('scanner','manual') AND
        (EXISTS (SELECT 1 FROM user_signal_access a WHERE a.signal_id=s.id AND a.telegram_user_id=%s)
         OR (s.source='scanner' AND EXISTS (SELECT 1 FROM subscriptions p WHERE p.telegram_user_id=%s AND p.paid_until>NOW())))""",
        (signal_id,user_id,user_id)).fetchone()
    if not row:
        raise TrackingError('signal_not_available')
    if row[2] not in ('waiting_entry','active','tp1_reached'):
        raise TrackingError('signal_not_active')
    existing = connection.execute("SELECT 1 FROM user_trade_tracking WHERE telegram_user_id=%s AND symbol=%s AND side=%s AND status='active'", (user_id,row[0],row[1])).fetchone()
    if existing:
        raise TrackingError('market_already_tracked')
    connection.execute("INSERT INTO user_signal_access (telegram_user_id,signal_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (user_id,signal_id))
    connection.execute("INSERT INTO user_trade_tracking (telegram_user_id,signal_id,symbol,side) VALUES (%s,%s,%s,%s)", (user_id,signal_id,row[0],row[1]))
    return {'tracking_status':'active'}


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def matching_position(signal, positions):
    candidates = [p for p in positions if p.get('symbol') == signal['symbol'].replace('_','-')
                  and p.get('positionSide') == signal['side'] and abs(_number(p.get('positionAmt')) or 0) > 0
                  and p.get('positionId')]
    return candidates[0] if len(candidates) == 1 else None


def matching_tp1_order(signal, orders, position):
    candidates = []
    side = 'SELL' if signal['side'] == 'LONG' else 'BUY'
    for order in orders:
        if order.get('symbol') != signal['symbol'].replace('_','-') or order.get('side') != side:
            continue
        if order.get('positionSide') not in (signal['side'], 'BOTH'):
            continue
        if order.get('positionSide') == 'BOTH' and not any(str(order.get(k)).lower() == 'true' for k in ('reduceOnly','closePosition')):
            continue
        if order.get('positionId') and str(order['positionId']) != str(position['positionId']):
            continue
        if order.get('type') not in ('TAKE_PROFIT','TAKE_PROFIT_MARKET') or order.get('status') not in ('NEW','PARTIALLY_FILLED'):
            continue
        target = _number(signal.get('tp1'))
        trigger = _number(order.get('stopPrice'))
        tolerance = max(_number(signal.get('price_unit')) or 0, abs(target or 0) * 1e-8)
        if target and trigger and abs(target-trigger) <= tolerance and order.get('orderId'):
            candidates.append(order)
    return candidates[0] if len(candidates) == 1 else None


def order_confirms_tp1(signal, order):
    return bool(str(order.get('orderId')) == str(signal.get('tp1_order_id'))
        and order.get('symbol') == signal['symbol'].replace('_','-')
        and order.get('side') == ('SELL' if signal['side']=='LONG' else 'BUY')
        and order.get('positionSide') in (signal['side'],'BOTH')
        and order.get('status') == 'FILLED' and (_number(order.get('executedQty')) or 0) > 0)


def reconcile_user(connection, user_id):
    client = account_client(connection, user_id)
    if not client:
        return 0
    rows = connection.execute("""SELECT t.signal_id,t.symbol,t.side,t.position_id,t.tp1_order_id,
        s.tp1,s.price_unit,t.execution_state FROM user_trade_tracking t JOIN signals s ON s.id=t.signal_id
        WHERE t.telegram_user_id=%s AND t.status='active'""", (user_id,)).fetchall()
    checked = 0
    for row in rows:
        signal = dict(zip(('id','symbol','side','position_id','tp1_order_id','tp1','price_unit','execution_state'), row))
        if signal['execution_state'] == 'tp1_filled':
            continue
        try:
            state = 'unverified'
            if signal['tp1_order_id']:
                order = client.order(signal['symbol'], signal['tp1_order_id'])
                if order_confirms_tp1(signal, order):
                    state = 'tp1_filled'
                elif order.get('status') in ('CANCELED','EXPIRED','REJECTED'):
                    signal['tp1_order_id'] = None
                else:
                    state = 'order_linked'
            if not signal['tp1_order_id']:
                position = matching_position(signal, client.positions(signal['symbol']))
                # Never rebind an existing trade to a subsequent position in the same coin.
                if position and (not signal['position_id'] or str(position['positionId']) == str(signal['position_id'])):
                    signal['position_id'] = str(position['positionId'])
                    order = matching_tp1_order(signal, client.open_orders(signal['symbol']), position)
                    if order:
                        signal['tp1_order_id'] = str(order['orderId'])
                        state = 'order_linked'
                    else:
                        state = 'position_linked'
            # A concurrent exit/disconnect wins over work done during the HTTP calls.
            updated = connection.execute("""UPDATE user_trade_tracking SET position_id=%s,tp1_order_id=%s,
                execution_state=%s,execution_checked_at=NOW() WHERE telegram_user_id=%s AND signal_id=%s
                AND status='active' AND EXISTS (SELECT 1 FROM bingx_accounts WHERE telegram_user_id=%s)
                RETURNING signal_id""", (signal['position_id'],signal['tp1_order_id'],state,user_id,signal['id'],user_id)).fetchone()
            if updated and state == 'tp1_filled':
                connection.execute("""INSERT INTO signal_update_deliveries (signal_id,telegram_user_id,event_type)
                    SELECT signal_id,telegram_user_id,'tp1_filled' FROM user_trade_tracking
                    WHERE telegram_user_id=%s AND signal_id=%s AND status='active'
                    ON CONFLICT DO NOTHING""", (user_id,signal['id']))
        except AccountUnavailable:
            connection.execute("""UPDATE user_trade_tracking SET execution_state='unavailable',execution_checked_at=NOW()
                WHERE telegram_user_id=%s AND signal_id=%s AND status='active'""", (user_id,signal['id']))
            continue
        checked += 1
    return checked
