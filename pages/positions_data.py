"""Catégories de positions disponibles."""

CATEGORIES_POSITION = [
    {'value': 'Cash', 'label': 'Cash / Liquidités', 'icon': 'savings', 'couleur': '#10b981'},
    {'value': 'Action', 'label': 'Action', 'icon': 'business_center', 'couleur': '#3b82f6'},
    {'value': 'ETF', 'label': 'ETF', 'icon': 'pie_chart', 'couleur': '#10b981'},
    {'value': 'Fonds', 'label': 'Fonds (OPCVM/SICAV)', 'icon': 'account_tree', 'couleur': '#8b5cf6'},
    {'value': 'SCPI', 'label': 'SCPI', 'icon': 'apartment', 'couleur': '#f59e0b'},
    {'value': 'Obligation', 'label': 'Obligation', 'icon': 'description', 'couleur': '#06b6d4'},
    {'value': 'Crypto', 'label': 'Crypto', 'icon': 'currency_bitcoin', 'couleur': '#f97316'},
    {'value': 'Fonds €', 'label': 'Fonds Euro', 'icon': 'euro', 'couleur': '#ef4444'},
    {'value': 'UC', 'label': 'Unité de Compte', 'icon': 'layers', 'couleur': '#a855f7'},
    {'value': 'Projet', 'label': 'Projet (crowdfunding)', 'icon': 'groups', 'couleur': '#ec4899'},
    {'value': 'Autre', 'label': 'Autre', 'icon': 'inventory_2', 'couleur': '#64748b'},
]


def get_categorie_info(value):
    for cat in CATEGORIES_POSITION:
        if cat['value'] == value:
            return cat
    return CATEGORIES_POSITION[-1]