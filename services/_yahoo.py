"""Recherche et cours via Yahoo Finance (actions, ETF, crypto)."""
from typing import Optional
import yfinance as yf


# Types Yahoo qu'on accepte (on filtre les OPCVM = MUTUALFUND)
ACCEPTED_TYPES = ('EQUITY', 'ETF', 'CRYPTOCURRENCY', 'INDEX')


def search_yahoo(query: str, limit: int = 10) -> list[dict]:
    """Recherche Yahoo en filtrant les OPCVM (mauvaise qualité)."""
    if not query or len(query) < 2:
        return []

    try:
        from yfinance import Search
        results = Search(query, max_results=limit * 2).quotes  # *2 car on filtre

        type_map = {
            'EQUITY': 'Action',
            'ETF': 'ETF',
            'CRYPTOCURRENCY': 'Crypto',
            'INDEX': 'Indice',
        }

        formatted = []
        for r in results:
            quote_type = r.get('quoteType', '')
            # ✅ FILTRE : on ne garde que actions, ETF, crypto, indices
            if quote_type not in ACCEPTED_TYPES:
                continue

            symbol = r.get('symbol', '')
            currency = r.get('currency', '')

            # Fallback devise via fast_info
            if not currency and symbol:
                try:
                    currency = yf.Ticker(symbol).fast_info.get('currency', 'USD')
                except Exception:
                    currency = 'USD'

            formatted.append({
                'symbol': symbol,
                'name': r.get('shortname') or r.get('longname', ''),
                'type': type_map.get(quote_type, 'Autre'),
                'exchange': r.get('exchDisp', ''),
                'currency': currency or 'USD',
                'source': 'yahoo',
            })

            if len(formatted) >= limit:
                break

        return formatted
    except Exception as e:
        print(f'Erreur recherche Yahoo: {e}')
        return []


def get_yahoo_price(symbol: str) -> dict:
    """Prix + devise depuis Yahoo."""
    try:
        ticker = yf.Ticker(symbol)
        fast = ticker.fast_info
        return {
            'price': float(fast.get('lastPrice')) if fast.get('lastPrice') else None,
            'currency': fast.get('currency', 'USD'),
        }
    except Exception as e:
        print(f'Erreur Yahoo prix {symbol}: {e}')
        return {'price': None, 'currency': 'USD'}


def get_currency_rate(from_curr: str, to_curr: str = 'EUR') -> Optional[float]:
    """Taux de change."""
    if from_curr == to_curr:
        return 1.0
    try:
        symbol = f'{from_curr}{to_curr}=X'
        ticker = yf.Ticker(symbol)
        return float(ticker.fast_info.get('lastPrice'))
    except Exception:
        return None