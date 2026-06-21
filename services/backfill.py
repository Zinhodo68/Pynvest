"""Reconstruit l'historique des valorisations à partir des transactions.

Logique de calcul optimisée :
- Téléchargement incrémental des cours Yahoo (jours manquants uniquement)
- Reconstruction des cours des actifs NON disponibles sur Yahoo (OPCVM/SICAV,
  fonds maison…) à partir des prix saisis lors des achats/ventes
- Requêtes HTTP effectuées hors session de base de données (non bloquant pour SQLite)
- Calcul de valorisation journalier en O(1) amorti par pointeurs chronologiques
- Nettoyage des positions soldées (tolérance float epsilon)
"""
from datetime import date, timedelta
from collections import defaultdict
import math
import re
from sqlalchemy import select, func, or_

from database.db import get_session
from database.models import Portefeuille, Position, Valorisation, CoursHistorique, Transaction
from services._yahoo import get_yahoo_history, get_currency_rate

# ✅ Seuls ces types d'opérations enfant constituent un vrai arbitrage interne
ARBITRAGE_CHILD_TYPES = {'achat', 'vente', 'versement', 'retrait'}

# Types d'opérations qui portent un "cours" exploitable (prix unitaire saisi)
_PRICED_OPS = ('achat', 'vente')

ISIN_PATTERN = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}\d$')
VALID_TICKER_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9.\-=^]{0,14}$')


def _is_valid_yahoo_ticker(ticker: str) -> bool:
    """Un ticker exploitable par Yahoo (≠ ISIN, ≠ libellé fantaisiste)."""
    if not ticker:
        return False
    ticker = ticker.strip()
    if ISIN_PATTERN.match(ticker):
        return False
    return bool(VALID_TICKER_PATTERN.match(ticker))


def backfill_cours_historique(portefeuille_id: int) -> int:
    """Construit l'historique des cours pour toutes les positions :

    1. Télécharge l'historique Yahoo (jours manquants) pour les tickers valides.
    2. Reconstruit une série de cours à partir des prix d'achat/vente saisis
       pour les actifs NON disponibles sur Yahoo (OPCVM, SICAV, fonds maison…).
       Ces points sont stockés avec ``source='transaction'`` et ne sont jamais
       écrasés par un cours déjà présent (Yahoo reste prioritaire).
    """
    # ──────────────────────────────────────────────────────────────────────
    # 1. Étape rapide sous BDD pour lister les besoins (sans bloquer SQLite)
    # ──────────────────────────────────────────────────────────────────────
    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        if not p or not p.transactions:
            return 0

        achats = [t for t in p.transactions if t.type_operation == 'achat']
        if not achats:
            print('   ℹ️  Aucun achat enregistré')
            return 0

        first_purchase_date = min(t.date_operation for t in achats)

        # Tickers Yahoo valides (téléchargement réseau)
        yahoo_tickers = set()
        for t in p.transactions:
            if t.type_operation in _PRICED_OPS and _is_valid_yahoo_ticker(t.ticker):
                yahoo_tickers.add(t.ticker.strip())

        # Pour chaque ticker Yahoo, on détermine à partir de quand télécharger
        ticker_start_dates = {}
        for ticker in yahoo_tickers:
            max_date = session.execute(
                select(func.max(CoursHistorique.date_cours))
                .where(CoursHistorique.ticker == ticker)
            ).scalar()

            if max_date:
                ticker_start_dates[ticker] = max_date + timedelta(days=1)
            else:
                ticker_start_dates[ticker] = first_purchase_date

        # Snapshot des prix saisis (achat/vente) pour la reconstruction locale.
        # On garde ticker + code pour pouvoir indexer le cours de façon robuste.
        priced_tx = []
        for t in p.transactions:
            if (
                t.type_operation in _PRICED_OPS
                and t.quantite is not None
                and t.prix_unitaire is not None
                and t.prix_unitaire > 0
            ):
                priced_tx.append({
                    'ticker': (t.ticker or None),
                    'code': (t.code or None),
                    'date': t.date_operation,
                    'prix': float(t.prix_unitaire),
                })

    # ──────────────────────────────────────────────────────────────────────
    # 2. Requêtes réseau hors session de base de données (non bloquant)
    # ──────────────────────────────────────────────────────────────────────
    end_date = date.today()
    yahoo_history_to_insert = []

    for ticker, start_date in ticker_start_dates.items():
        if start_date >= end_date:
            print(f'   ℹ️  {ticker}: Déjà à jour (dernier cours en BDD le {start_date - timedelta(days=1)})')
            continue

        print(f'   📥 Téléchargement Yahoo pour {ticker} du {start_date} au {end_date}')
        history = get_yahoo_history(ticker, start_date, end_date)
        if not history:
            print(f'   ⚠️ Aucun historique Yahoo récupéré pour {ticker}')
            continue

        currency = history[0].get('currency', 'EUR')
        rate = 1.0
        if currency != 'EUR':
            rate = get_currency_rate(currency, 'EUR') or 1.0

        for h in history:
            cours_eur = h['cours'] * rate
            if math.isnan(cours_eur) or math.isinf(cours_eur) or cours_eur <= 0:
                continue
            yahoo_history_to_insert.append({
                'ticker': ticker,
                'isin': None,
                'date_cours': h['date'],
                'cours': cours_eur,
                'source': 'yahoo_backfill',
            })

    # ──────────────────────────────────────────────────────────────────────
    # 3. Insertion en base de données
    # ──────────────────────────────────────────────────────────────────────
    total_inserted = 0
    with get_session() as session:
        # 3a. Cours Yahoo (anti-doublon par ticker/date)
        if yahoo_history_to_insert:
            existing_yahoo = set(
                session.execute(
                    select(CoursHistorique.ticker, CoursHistorique.date_cours)
                    .where(CoursHistorique.ticker.in_(yahoo_tickers))
                ).all()
            )
            for item in yahoo_history_to_insert:
                if (item['ticker'], item['date_cours']) not in existing_yahoo:
                    session.add(CoursHistorique(
                        ticker=item['ticker'],
                        isin=item['isin'],
                        date_cours=item['date_cours'],
                        cours=item['cours'],
                        devise='EUR',
                        source=item['source'],
                    ))
                    existing_yahoo.add((item['ticker'], item['date_cours']))
                    total_inserted += 1

        # 3b. Cours reconstruits depuis les prix d'achat/vente saisis,
        #     pour les actifs NON couverts par Yahoo.
        #     On n'insère un point que si AUCUN cours (Yahoo ou autre) n'existe
        #     déjà pour cet actif à cette date.
        if priced_tx:
            # Ensemble de tous les couples (ticker|isin, date) déjà connus en BDD
            ids = set()
            for tx in priced_tx:
                if tx['ticker']:
                    ids.add(tx['ticker'])
                if tx['code']:
                    ids.add(tx['code'])

            existing_pairs = set()
            if ids:
                rows = session.execute(
                    select(CoursHistorique.ticker, CoursHistorique.isin,
                           CoursHistorique.date_cours)
                    .where(
                        (CoursHistorique.ticker.in_(ids)) |
                        (CoursHistorique.isin.in_(ids))
                    )
                ).all()
                for tck, isin, d in rows:
                    if tck:
                        existing_pairs.add((tck, d))
                    if isin:
                        existing_pairs.add((isin, d))

            for tx in priced_tx:
                # L'actif est-il déjà couvert par Yahoo ? (ticker valide)
                if _is_valid_yahoo_ticker(tx['ticker']):
                    # On laisse Yahoo gérer ces dates, sauf trou éventuel
                    pass

                identifiers = [i for i in (tx['ticker'], tx['code']) if i]
                if not identifiers:
                    continue

                # Déjà un cours connu pour cet actif à cette date ? → on saute
                already = any((ident, tx['date']) in existing_pairs for ident in identifiers)
                if already:
                    continue

                session.add(CoursHistorique(
                    ticker=tx['ticker'],
                    isin=tx['code'],
                    date_cours=tx['date'],
                    cours=tx['prix'],
                    devise='EUR',
                    source='transaction',
                ))
                for ident in identifiers:
                    existing_pairs.add((ident, tx['date']))
                total_inserted += 1

        try:
            session.commit()
            print(f"   ✅ Fin d'insertion : {total_inserted} cours ajoutés en BDD")
        except Exception as e:
            print(f'   ❌ Échec de la sauvegarde des cours historiques : {e}')
            session.rollback()

    return total_inserted


def _build_arbitrage_parent_ids(transactions: list) -> set:
    """Identifie les IDs de transactions qui sont des VRAIS parents d'arbitrage.

    Un parent est un arbitrage interne UNIQUEMENT si son enfant est de type
    achat/vente/versement/retrait (= transfert entre actifs).
    """
    arbitrage_parent_ids = set()
    for t in transactions:
        if t.parent_transaction_id is not None:
            if t.type_operation in ARBITRAGE_CHILD_TYPES:
                arbitrage_parent_ids.add(t.parent_transaction_id)
    return arbitrage_parent_ids


def _is_arbitrage_internal(t, arbitrage_parent_ids: set) -> bool:
    """Détermine si une transaction est partie d'un arbitrage interne."""
    is_arb_child = (
            t.parent_transaction_id is not None
            and t.type_operation in ARBITRAGE_CHILD_TYPES
    )
    is_arb_parent = t.id in arbitrage_parent_ids
    return is_arb_child or is_arb_parent


def backfill_valorisations(portefeuille_id: int) -> int:
    """Reconstruit les snapshots quotidiens en rejouant les transactions.

    À chaque jour, la valeur des titres détenus utilise le DERNIER COURS CONNU
    (Yahoo ou cours reconstruit depuis les prix saisis), et non plus le PRU.
    Le PRU ne sert que de filet de sécurité ultime si aucun cours n'existe.
    """
    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        if not p or not p.transactions:
            return 0

        # Nettoyage des anciennes valorisations
        session.query(Valorisation).filter(
            Valorisation.portefeuille_id == portefeuille_id
        ).delete()
        session.flush()

        transactions = sorted(p.transactions, key=lambda t: t.date_operation)
        start_date = transactions[0].date_operation
        end_date = date.today()

        arbitrage_parent_ids = _build_arbitrage_parent_ids(transactions)

        # ──────────────────────────────────────────────────────────────────
        # Chargement de l'historique des cours depuis la BDD locale.
        # On indexe par TOUS les identifiants possibles (ticker ET isin),
        # pour valoriser aussi bien les actions Yahoo que les OPCVM.
        # ──────────────────────────────────────────────────────────────────
        identifiers = set()
        for t in transactions:
            if t.type_operation in _PRICED_OPS:
                if t.ticker:
                    identifiers.add(t.ticker)
                if t.code:
                    identifiers.add(t.code)

        cours_par_id = defaultdict(list)
        if identifiers:
            cours_rows = session.execute(
                select(CoursHistorique.ticker,
                       CoursHistorique.isin,
                       CoursHistorique.date_cours,
                       CoursHistorique.cours)
                .where(
                    (CoursHistorique.ticker.in_(identifiers)) |
                    (CoursHistorique.isin.in_(identifiers))
                )
                .order_by(CoursHistorique.date_cours)
            ).all()
            for tck, isin, d, cours in cours_rows:
                if tck:
                    cours_par_id[tck].append((d, cours))
                if isin and isin != tck:
                    cours_par_id[isin].append((d, cours))

        # Tri + dédoublonnage (au cas où un id porte plusieurs sources)
        for ident, lst in cours_par_id.items():
            lst.sort(key=lambda x: x[0])

        # Pointeurs chronologiques (forward-fill en O(1) amorti)
        cours_index_pointers = {ident: 0 for ident in cours_par_id}

        def get_cours_a_date(ident: str, target: date):
            """Dernier cours connu d'un identifiant à une date donnée."""
            cours_list = cours_par_id.get(ident)
            if not cours_list:
                return None
            idx = cours_index_pointers[ident]
            while idx < len(cours_list) and cours_list[idx][0] <= target:
                idx += 1
            cours_index_pointers[ident] = idx
            if idx > 0:
                return cours_list[idx - 1][1]
            return None

        def get_cours_position(pos, target: date):
            """Dernier cours connu d'une position (essaie ticker puis code)."""
            for ident in (pos.get('ticker'), pos.get('code')):
                if ident:
                    c = get_cours_a_date(ident, target)
                    if c is not None:
                        return c
            return None

        def get_dernier_cours_connu(pos):
            """Tout dernier cours connu, toutes dates confondues (pour cours_actuel)."""
            best = None
            for ident in (pos.get('ticker'), pos.get('code')):
                lst = cours_par_id.get(ident)
                if lst:
                    cand = lst[-1][1]
                    best = cand  # la dernière entrée chronologique
            return best

        # ──────────────────────────────────────────────────────────────────
        # Application d'une transaction sur l'état (cash + positions_held)
        # ──────────────────────────────────────────────────────────────────
        cash = 0.0
        positions_held = {}

        def _ensure_pos(key, t, default_pru):
            positions_held[key] = {
                'ticker': t.ticker,
                'code': t.code,
                'quantite': t.quantite,
                'pru': default_pru,
                'nom': t.nom_titre,
                'categorie': t.categorie,
            }

        def apply_tx(t):
            nonlocal cash
            # 🆕 Crédit sur Fonds € (AV/PER) : on route vers le Fonds €
            # ciblé par nom_titre, même si ticker/code pointent vers
            # l'action source (qui a versé le dividende).
            is_fonds_euro_credit = (
                t.categorie == 'Fonds Euro'
                and t.quantite is not None
                and t.prix_unitaire == 1.0
            )
            if is_fonds_euro_credit:
                key = t.nom_titre
                is_asset_specific_tx = True
            else:
                key = t.ticker or t.code or t.nom_titre
                is_asset_specific_tx = bool(key and t.quantite is not None)
            is_internal = _is_arbitrage_internal(t, arbitrage_parent_ids)

            if t.type_operation == 'versement':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] += t.quantite
                    else:
                        _ensure_pos(key, t, t.prix_unitaire if t.prix_unitaire is not None else 1.0)
                elif not is_internal:
                    cash += t.montant

            elif t.type_operation == 'retrait':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] -= t.quantite
                elif not is_internal:
                    cash -= t.montant

            elif t.type_operation == 'interets':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] += t.quantite
                    else:
                        _ensure_pos(key, t, t.prix_unitaire if t.prix_unitaire is not None else 1.0)
                else:
                    cash += t.montant

            elif t.type_operation == 'dividende':
                if is_asset_specific_tx:
                    if key in positions_held:
                        old = positions_held[key]
                        if is_fonds_euro_credit:
                            # Crédit Fonds € : on ne touche pas au PRU
                            # (toujours 1.0 pour un Fonds €)
                            old['quantite'] += t.quantite
                        else:
                            # Réinvestissement : moyenne pondérée du PRU
                            new_qte = old['quantite'] + t.quantite
                            old['pru'] = (
                                ((old['quantite'] * old['pru']) + (t.quantite * (t.prix_unitaire or 0))) / new_qte
                                if new_qte > 0 else (t.prix_unitaire or 0)
                            )
                            old['quantite'] = new_qte
                    else:
                        _ensure_pos(key, t, t.prix_unitaire)
                else:
                    cash += t.montant

            elif t.type_operation == 'frais':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] -= t.quantite
                else:
                    cash -= t.montant

            elif t.type_operation == 'achat':
                if not is_internal:
                    cash -= t.montant
                if t.quantite is not None and t.prix_unitaire is not None:
                    if key in positions_held:
                        old = positions_held[key]
                        new_qte = old['quantite'] + t.quantite
                        old['pru'] = (
                            ((old['quantite'] * old['pru']) + (t.quantite * t.prix_unitaire)) / new_qte
                            if new_qte > 0 else t.prix_unitaire
                        )
                        old['quantite'] = new_qte
                    else:
                        _ensure_pos(key, t, t.prix_unitaire)

            elif t.type_operation == 'vente':
                if not is_internal:
                    cash += t.montant
                if t.quantite is not None and key in positions_held:
                    positions_held[key]['quantite'] -= t.quantite

            # Nettoyage des lignes soldées (tolérance arrondi)
            if key in positions_held and positions_held[key]['quantite'] <= 1e-9:
                del positions_held[key]

        # ──────────────────────────────────────────────────────────────────
        # Boucle jour par jour : on rejoue les transactions au fil du temps
        # et on prend un snapshot de valorisation chaque jour.
        # ──────────────────────────────────────────────────────────────────
        created = 0
        tx_index = 0
        n_tx = len(transactions)
        current_date = start_date

        while current_date <= end_date:
            # Appliquer toutes les transactions dont la date <= jour courant
            while tx_index < n_tx and transactions[tx_index].date_operation <= current_date:
                apply_tx(transactions[tx_index])
                tx_index += 1

            # Valorisation des titres détenus à la date courante
            valo_titres = 0.0
            for pos in positions_held.values():
                qte = pos['quantite']
                if qte <= 0:
                    continue
                cours = get_cours_position(pos, current_date)
                if cours is not None:
                    valo_titres += qte * cours
                else:
                    # Filet de sécurité : aucun cours connu → PRU
                    valo_titres += qte * pos['pru']

            valo_totale = cash + valo_titres
            session.add(Valorisation(
                portefeuille_id=portefeuille_id,
                date_valeur=current_date,
                montant=round(valo_totale, 2),
            ))
            created += 1
            current_date += timedelta(days=1)

        # ──────────────────────────────────────────────────────────────────
        # Mise à jour de la table 'positions' pour l'affichage temps réel :
        # cours_actuel = DERNIER COURS CONNU (et non plus le PRU).
        # ──────────────────────────────────────────────────────────────────
        for key, pos in positions_held.items():
            last_cours = get_dernier_cours_connu(pos)

            match_conditions = [Position.nom == pos['nom']]
            if pos.get('ticker'):
                match_conditions.append(Position.ticker == pos['ticker'])
            if pos.get('code'):
                match_conditions.append(Position.code == pos['code'])

            existing_pos = session.execute(
                select(Position).where(
                    Position.portefeuille_id == portefeuille_id,
                    or_(*match_conditions),
                )
            ).scalars().first()

            if existing_pos:
                if last_cours is not None:
                    existing_pos.cours_actuel = last_cours
                existing_pos.prix_moyen = pos['pru']
                existing_pos.quantite = pos['quantite']

        try:
            session.commit()
        except Exception as e:
            print(f'   ❌ Échec de la sauvegarde du backfill valorisation : {e}')
            session.rollback()

        return created


def backfill_portefeuille(portefeuille_id: int) -> dict:
    """Lance le backfill complet : cours historiques + valorisations."""
    print(f'🔄 Backfill du portefeuille #{portefeuille_id}')
    cours_inserts = backfill_cours_historique(portefeuille_id)
    valos_creees = backfill_valorisations(portefeuille_id)
    print(f'✅ Backfill terminé : {cours_inserts} cours, {valos_creees} valorisations')
    return {
        'cours_inserts': cours_inserts,
        'valorisations_creees': valos_creees,
    }
