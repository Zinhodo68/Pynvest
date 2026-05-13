"""Recherche unifiée de titres : BDD locale + Yahoo + Boursorama.

Stratégie :
1. Détecte si la query est un ISIN (FR0010923375 = 2 lettres + 10 alphanumeriques)
   → si oui, route prioritairement vers Boursorama
2. Cherche dans la BDD les titres déjà manipulés (Transaction.distinct)
3. Cherche sur Yahoo Finance
4. Cherche sur Boursorama
5. Retourne toujours l'option "Créer manuel"
"""
import re
import asyncio
from sqlalchemy import select, distinct, func

from database.db import get_session
from database.models import Transaction, Position
from services._yahoo import search_yahoo
from services._boursorama import search_opcvm


# Pattern ISIN : 2 lettres pays + 10 caractères alphanumeriques
ISIN_PATTERN = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}\d$', re.IGNORECASE)


def is_isin(query: str) -> bool:
    """Détecte si la query ressemble à un ISIN."""
    if not query:
        return False
    return bool(ISIN_PATTERN.match(query.strip()))


def search_in_db(query: str, limit: int = 10) -> list[dict]:
    """Cherche dans les transactions passées les titres déjà manipulés.

    Retourne des résultats au format unifié avec en plus :
    - 'in_portfolios' : liste de noms de portefeuilles où le titre est encore détenu
    """
    if not query or len(query) < 2:
        return []

    q = query.strip().lower()

    with get_session() as session:
        # Récupère tous les titres distincts depuis les transactions
        # On déduplique par (ticker, code, nom_titre)
        stmt = select(
            Transaction.ticker,
            Transaction.code,
            Transaction.nom_titre,
            Transaction.categorie,
        ).where(
            Transaction.nom_titre.isnot(None),
            Transaction.type_operation.in_(['achat', 'vente', 'dividende']),
        ).distinct()

        rows = session.execute(stmt).all()

        # Filtre Python (case-insensitive sur ticker/code/nom)
        matched = []
        seen = set()
        for ticker, code, nom, categorie in rows:
            # Skip Cash et Fonds €
            if categorie in ('Cash', 'Fonds €', 'Fonds Euro'):
                continue
            # Skip doublons (même nom)
            key = (ticker or '', code or '', nom or '')
            if key in seen:
                continue
            # Match si la query apparaît dans ticker, code ou nom
            haystack = f"{ticker or ''} {code or ''} {nom or ''}".lower()
            if q not in haystack:
                continue
            seen.add(key)
            matched.append({
                'ticker': ticker,
                'code': code,
                'nom': nom,
                'categorie': categorie,
            })

        if not matched:
            return []

        # Pour chaque match, on enrichit avec les portefeuilles où le titre est détenu
        results = []
        for m in matched[:limit]:
            # Recherche dans Position pour voir où il est encore détenu
            pos_stmt = select(Position).where(Position.quantite > 0)
            if m['ticker']:
                pos_stmt = pos_stmt.where(
                    (Position.ticker == m['ticker']) | (Position.nom == m['nom'])
                )
            else:
                pos_stmt = pos_stmt.where(Position.nom == m['nom'])

            positions = session.execute(pos_stmt).scalars().all()
            in_portfolios = []
            for pos in positions:
                ptf = pos.portefeuille
                ptf_label = ptf.nom_affiche
                in_portfolios.append({
                    'portefeuille': ptf_label,
                    'quantite': pos.quantite,
                })

            results.append({
                'symbol': m['ticker'] or m['code'] or m['nom'][:20],
                'name': m['nom'],
                'ticker': m['ticker'],
                'isin': m['code'],
                'type': m['categorie'] or 'Autre',
                'currency': 'EUR',
                'exchange': 'BDD locale',
                'source': 'db',
                'in_portfolios': in_portfolios,
            })

        return results


async def unified_search(query: str, limit_per_source: int = 6) -> dict:
    """Recherche en parallèle dans BDD + Yahoo + Boursorama.

    Retourne un dict groupé :
    {
        'db':         [...],   # déjà dans tes portefeuilles
        'yahoo':      [...],   # actions/ETF/crypto
        'boursorama': [...],   # OPCVM/SICAV
        'is_isin':    bool,    # query détectée comme ISIN
    }
    """
    if not query or len(query) < 2:
        return {'db': [], 'yahoo': [], 'boursorama': [], 'is_isin': False}

    isin_detected = is_isin(query)

    # Lancement en parallèle
    db_task = asyncio.to_thread(search_in_db, query, limit_per_source)

    if isin_detected:
        # Pour un ISIN : on privilégie Boursorama, mais on tente Yahoo aussi (au cas où)
        boursorama_task = asyncio.to_thread(search_opcvm, query, limit_per_source)
        yahoo_task = asyncio.to_thread(search_yahoo, query, limit_per_source)
    else:
        yahoo_task = asyncio.to_thread(search_yahoo, query, limit_per_source)
        boursorama_task = asyncio.to_thread(search_opcvm, query, limit_per_source)

    db_res, yahoo_res, boursorama_res = await asyncio.gather(
        db_task, yahoo_task, boursorama_task, return_exceptions=True
    )

    # Gestion des erreurs : exception → liste vide
    if isinstance(db_res, Exception):
        print(f'Erreur search_in_db : {db_res}')
        db_res = []
    if isinstance(yahoo_res, Exception):
        print(f'Erreur search_yahoo : {yahoo_res}')
        yahoo_res = []
    if isinstance(boursorama_res, Exception):
        print(f'Erreur search_opcvm : {boursorama_res}')
        boursorama_res = []

    return {
        'db': db_res,
        'yahoo': yahoo_res,
        'boursorama': boursorama_res,
        'is_isin': isin_detected,
    }