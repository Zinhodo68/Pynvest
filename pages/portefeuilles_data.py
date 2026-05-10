"""Données de référence pour les portefeuilles."""

# 'mode' : 'mono' (1 seul support, taux) ou 'multi' (positions multiples)
TYPES_PORTEFEUILLE = [
    {'value': 'PEA', 'label': 'PEA', 'icon': 'show_chart', 'couleur': '#3b82f6', 'mode': 'multi'},
    {'value': 'PEA-PME', 'label': 'PEA-PME', 'icon': 'business', 'couleur': '#6366f1', 'mode': 'multi'},
    {'value': 'PER', 'label': 'PER', 'icon': 'savings', 'couleur': '#8b5cf6', 'mode': 'multi'},
    {'value': 'CTO', 'label': 'Compte-Titres Ordinaire', 'icon': 'candlestick_chart', 'couleur': '#10b981', 'mode': 'multi'},
    {'value': 'Assurance-Vie', 'label': 'Assurance-Vie', 'icon': 'shield', 'couleur': '#06b6d4', 'mode': 'multi'},
    {'value': 'Livret A', 'label': 'Livret A', 'icon': 'account_balance', 'couleur': '#ef4444', 'mode': 'mono', 'plafond': 22950, 'taux_defaut': 3.0},
    {'value': 'Livret Bleu', 'label': 'Livret Bleu', 'icon': 'account_balance', 'couleur': '#3b82f6', 'mode': 'mono', 'plafond': 22950, 'taux_defaut': 3.0},
    {'value': 'LDDS', 'label': 'LDDS', 'icon': 'account_balance', 'couleur': '#f59e0b', 'mode': 'mono', 'plafond': 12000, 'taux_defaut': 3.0},
    {'value': 'Livret Jeune', 'label': 'Livret Jeune', 'icon': 'account_balance', 'couleur': '#a855f7', 'mode': 'mono', 'plafond': 1600, 'taux_defaut': 3.0},
    {'value': 'LEP', 'label': 'LEP', 'icon': 'account_balance', 'couleur': '#14b8a6', 'mode': 'mono', 'plafond': 10000, 'taux_defaut': 5.0},
    {'value': 'Crowdfunding', 'label': 'Crowdfunding', 'icon': 'groups', 'couleur': '#ec4899', 'mode': 'multi'},
    {'value': 'Crypto', 'label': 'Crypto', 'icon': 'currency_bitcoin', 'couleur': '#f97316', 'mode': 'multi'},
    {'value': 'Compte Épargne', 'label': 'Compte Épargne', 'icon': 'savings', 'couleur': '#22c55e', 'mode': 'mono', 'taux_defaut': 1.0},
    {'value': 'Autre', 'label': 'Autre', 'icon': 'account_balance_wallet', 'couleur': '#6b7280', 'mode': 'multi'},
]


def get_type_info(type_value: str):
    for t in TYPES_PORTEFEUILLE:
        if t['value'] == type_value:
            return t
    return TYPES_PORTEFEUILLE[-1]


def is_mono_support(type_value: str) -> bool:
    """True si le portefeuille est mono-support (livret, compte...)."""
    return get_type_info(type_value).get('mode') == 'mono'