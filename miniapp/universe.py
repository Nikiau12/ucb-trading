"""Global top-100 by capitalization intersected with active BingX USDT futures."""
from __future__ import annotations
import os
import threading
import time
import requests

_lock = threading.Lock()
_symbols = None
_checked_at = 0.0
_retry_at = 0.0
# Explicit contract-unit aliases; never strip arbitrary numerical prefixes.
ALIASES = {"BONK": "1000BONK", "PEPE": "1000PEPE", "SHIB": "1000SHIB", "SATS": "10000SATS"}

class UniverseUnavailable(RuntimeError):
    pass

def select_symbols(coins, contracts):
    available = {c['symbol'].replace('-', '_') for c in contracts
                 if c.get('status') == 1 and str(c.get('apiStateOpen')).lower() == 'true'
                 and str(c.get('symbol','')).endswith('-USDT')}
    selected = []
    for coin in sorted(coins, key=lambda c: c.get('market_cap_rank') or 10**9):
        rank = coin.get('market_cap_rank')
        if not isinstance(rank, int) or not 1 <= rank <= 100:
            continue
        base = str(coin.get('symbol', '')).upper()
        if not base.isalnum() or base.startswith(('NCCO','NCFX','NCSI','NCSK')):
            continue
        candidates = [base + '_USDT', ALIASES.get(base, base) + '_USDT']
        match = next((s for s in candidates if s in available), None)
        if match and match not in selected:
            selected.append(match)
    return selected[:100]

def top_symbols(n=100):
    global _symbols, _checked_at, _retry_at
    with _lock:
        now = time.monotonic()
        if _symbols is not None and now - _checked_at < 3600:
            return list(_symbols[:min(100, n)])
        if now >= _retry_at:
            try:
                key = os.getenv('COINGECKO_DEMO_API_KEY', '')
                headers = {'x-cg-demo-api-key': key} if key else {}
                response = requests.get('https://api.coingecko.com/api/v3/coins/markets',
                    params={'vs_currency':'usd','order':'market_cap_desc','per_page':100,'page':1,'sparkline':'false'},
                    headers=headers, timeout=12)
                response.raise_for_status()
                coins = response.json()
                response = requests.get('https://open-api.bingx.com/openApi/swap/v2/quote/contracts', timeout=12)
                response.raise_for_status()
                payload = response.json()
                if int(payload.get('code', -1)) != 0 or not isinstance(coins, list) or len(coins) < 100:
                    raise ValueError('incomplete_universe')
                selected = select_symbols(coins, payload['data'])
                if not selected:
                    raise ValueError('empty_universe')
                _symbols, _checked_at = selected, now
            except (requests.RequestException, ValueError, KeyError, TypeError):
                _retry_at = now + 60
        # Bounded last-good fallback; never substitute a volume ranking.
        if _symbols is None or now - _checked_at > 6 * 3600:
            raise UniverseUnavailable('capitalization_ranking_unavailable')
        return list(_symbols[:min(100, n)])
