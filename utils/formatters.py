"""Utilitaires de formatage (montants, pourcentages, dates...)."""
from datetime import date, datetime


def format_money(value: float, currency: str = '€', decimals: int = 0) -> str:
    """Formate un montant à la française : 12 345 €"""
    if value is None:
        return '—'
    formatted = f'{value:,.{decimals}f}'.replace(',', ' ').replace('.', ',')
    return f'{formatted} {currency}'


def format_percent(value: float, decimals: int = 2, with_sign: bool = True) -> str:
    """Formate un pourcentage : +12,45 %"""
    if value is None:
        return '—'
    sign = '+' if (with_sign and value > 0) else ''
    formatted = f'{value:,.{decimals}f}'.replace(',', '§').replace('.', ',').replace('§', ' ')
    return f'{sign}{formatted} %'


def format_date_fr(value) -> str:
    """Formate une date en JJ/MM/AAAA."""
    if value is None:
        return '—'
    if isinstance(value, str):
        value = date.fromisoformat(value)
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime('%d/%m/%Y')


def get_perf_color(value: float) -> str:
    """Couleur selon le signe : vert positif, rouge négatif, gris neutre."""
    if value is None or value == 0:
        return '#94a3b8'
    return '#10b981' if value > 0 else '#ef4444'