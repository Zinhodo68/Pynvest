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


def get_yahoo_history(symbol: str, start_date, end_date=None) -> list[dict]:
    """Récupère l'historique des cours quotidiens d'un titre."""
    from datetime import date as _date
    import math

    if end_date is None:
        end_date = _date.today()

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(
            start=start_date.isoformat(),
            end=(end_date).isoformat(),
            auto_adjust=False,
        )

        if hist.empty:
            print(f'   ⚠️  Aucun historique pour {symbol}')
            return []

        try:
            currency = ticker.fast_info.get('currency', 'USD')
        except Exception:
            currency = 'USD'

        # Conversion DataFrame → liste de dicts (filtrage des NaN)
        result = []
        for idx, row in hist.iterrows():
            cours = float(row['Close'])
            if math.isnan(cours) or math.isinf(cours) or cours <= 0:
                continue
            result.append({
                'date': idx.date(),
                'cours': cours,
                'currency': currency,
            })

        return result
    except Exception as e:
        print(f'   ❌ Erreur historique Yahoo {symbol}: {e}')
        return []


def get_yahoo_price_at_date(symbol: str, target_date) -> dict:
    """Récupère le cours de clôture d'un titre à une date donnée.

    Si la date est un week-end ou jour férié, retourne le dernier cours
    connu avant cette date (ex: vendredi pour un samedi).

    Args:
        symbol: ticker Yahoo (ex: 'MC.PA')
        target_date: date.date cible

    Returns:
        {'price': float, 'currency': str} ou {'price': None, 'currency': 'USD'}
    """
    from datetime import timedelta, date as _date, datetime as _dt

    try:
        ticker = yf.Ticker(symbol)
        # Fenêtre de 10 jours avant pour gérer week-ends/fériés/congés
        start = target_date - timedelta(days=10)
        end = target_date + timedelta(days=1)

        hist = ticker.history(
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=False,
        )

        if hist.empty:
            return {'price': None, 'currency': 'USD'}

        # Filtrer pour ne garder que les dates <= target_date
        valid_rows = hist[hist.index.date <= target_date]
        if valid_rows.empty:
            return {'price': None, 'currency': 'USD'}

        last_row = valid_rows.iloc[-1]

        try:
            currency = ticker.fast_info.get('currency', 'USD')
        except Exception:
            currency = 'USD'

        return {
            'price': float(last_row['Close']),
            'currency': currency,
        }
    except Exception as e:
        print(f'Erreur get_yahoo_price_at_date {symbol}: {e}')
        return {'price': None, 'currency': 'USD'}