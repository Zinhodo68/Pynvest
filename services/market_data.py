"""Façade qui dispatch vers Yahoo, Boursorama, ou saisie manuelle."""
from typing import Optional

from services._yahoo import search_yahoo, get_yahoo_price, get_currency_rate
from services._boursorama import search_opcvm, get_opcvm_price


def search_action_etf(query: str, limit: int = 10) -> list[dict]:
    """Recherche d'actions, ETF, crypto, indices via Yahoo."""
    return search_yahoo(query, limit)


def search_fonds_opcvm(query: str, limit: int = 10) -> list[dict]:
    """Recherche d'OPCVM/SICAV via Boursorama."""
    return search_opcvm(query, limit)


def get_current_price_with_currency(symbol_or_url: str, source: str = 'yahoo') -> dict:
    """Récupère prix + devise selon la source.

    source : 'yahoo', 'boursorama', ou 'manual'
    """
    if source == 'boursorama':
        result = get_opcvm_price(symbol_or_url)
        if result:
            return {'price': result['price'], 'currency': result['currency']}
        return {'price': None, 'currency': 'EUR'}
    elif source == 'manual':
        return {'price': None, 'currency': 'EUR'}
    else:
        return get_yahoo_price(symbol_or_url)


# Réexport pour compatibilité
__all__ = [
    'search_action_etf', 'search_fonds_opcvm',
    'get_current_price_with_currency', 'get_currency_rate',
]


def get_price_at_date_with_currency(symbol_or_url: str, source: str, target_date) -> dict:
    """Récupère le cours d'un titre à une date donnée, depuis la source spécifiée.

    Args:
        symbol_or_url: ticker Yahoo ou URL/ISIN Boursorama
        source: 'yahoo' ou 'boursorama'
        target_date: date.date cible

    Returns:
        {'price': float|None, 'currency': str}
    """
    if source == 'yahoo':
        from services._yahoo import get_yahoo_price_at_date
        return get_yahoo_price_at_date(symbol_or_url, target_date)
    elif source == 'boursorama':
        # Boursorama ne supporte pas l'historique facilement
        # → On retourne le cours actuel en fallback
        return get_current_price_with_currency(symbol_or_url, source)
    else:
        return {'price': None, 'currency': 'EUR'}

# Recherche unifiée (BDD + Yahoo + Boursorama)
from services.search import unified_search

__all__ = [
    'search_action_etf', 'search_fonds_opcvm',
    'get_current_price_with_currency', 'get_currency_rate',
    'unified_search',
]