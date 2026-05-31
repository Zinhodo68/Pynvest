"""Reconstruit l'historique des valorisations à partir des transactions.

Logique de calcul optimisée :
- Téléchargement incrémental des cours Yahoo (jours manquants uniquement)
- Requêtes HTTP effectuées hors session de base de données (non bloquant pour SQLite)
- Calcul de valorisation journalier en O(1) amorti par pointeurs chronologiques
- Nettoyage des positions soldées (tolérance float epsilon)
"""
from datetime import date, timedelta
from collections import defaultdict
import math
import re
from sqlalchemy import select, func

from database.db import get_session
from database.models import Portefeuille, Valorisation, CoursHistorique, Transaction
from services._yahoo import get_yahoo_history, get_currency_rate

# ✅ Seuls ces types d'opérations enfant constituent un vrai arbitrage interne
ARBITRAGE_CHILD_TYPES = {'achat', 'vente', 'versement', 'retrait'}


def backfill_cours_historique(portefeuille_id: int) -> int:
    """Télécharge l'historique Yahoo uniquement pour les jours manquants."""
    ISIN_PATTERN = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}\d$')
    VALID_TICKER_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9.\-=^]{0,14}$')

    # 1. Étape rapide sous BDD pour lister les besoins (sans bloquer SQLite longuement)
    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        if not p or not p.transactions:
            return 0

        achats = [t for t in p.transactions if t.type_operation == 'achat']
        if not achats:
            print('   ℹ️  Aucun achat enregistré')
            return 0

        first_purchase_date = min(t.date_operation for t in achats)

        # Filtrage et identification des tickers uniques
        tickers = set()
        for t in p.transactions:
            if t.type_operation in ('achat', 'vente') and t.ticker:
                ticker = t.ticker.strip()
                if ISIN_PATTERN.match(ticker) or not VALID_TICKER_PATTERN.match(ticker):
                    continue
                tickers.add(ticker)

        if not tickers:
            print('   ⚠️ Aucun ticker Yahoo valide dans les transactions')
            return 0

        # Pour chaque actif, on détermine à partir de quand télécharger
        ticker_start_dates = {}
        for ticker in tickers:
            # Récupération de la date du dernier cours connu en BDD
            max_date = session.execute(
                select(func.max(CoursHistorique.date_cours))
                .where(CoursHistorique.ticker == ticker)
            ).scalar()

            if max_date:
                # Si on a déjà des cours, on reprend au lendemain du dernier cours connu
                ticker_start_dates[ticker] = max_date + timedelta(days=1)
            else:
                # Sinon, on prend la date du tout premier achat historique du portefeuille
                ticker_start_dates[ticker] = first_purchase_date

    # 2. Requêtes réseau hors session de base de données (sécurisé et non bloquant)
    end_date = date.today()
    all_history_to_insert = []

    for ticker, start_date in ticker_start_dates.items():
        if start_date >= end_date:
            print(f'   ℹ️  {ticker}: Déjà à jour (dernier cours en BDD le {start_date - timedelta(days=1)})')
            continue

        print(f'   📥 Téléchargement pour {ticker} du {start_date} au {end_date}')
        history = get_yahoo_history(ticker, start_date, end_date)
        if not history:
            print(f'   ⚠️ Aucun historique récupéré pour {ticker}')
            continue

        currency = history[0].get('currency', 'EUR')
        rate = 1.0
        if currency != 'EUR':
            rate = get_currency_rate(currency, 'EUR') or 1.0

        for h in history:
            cours_eur = h['cours'] * rate
            if math.isnan(cours_eur) or math.isinf(cours_eur) or cours_eur <= 0:
                continue

            all_history_to_insert.append({
                'ticker': ticker,
                'date_cours': h['date'],
                'cours': cours_eur
            })

    # 3. Insertion en base de données par lot
    total_inserted = 0
    if all_history_to_insert:
        with get_session() as session:
            # Récupération en une seule requête de tous les doublons potentiels
            existing_entries = set(
                session.execute(
                    select(CoursHistorique.ticker, CoursHistorique.date_cours)
                    .where(CoursHistorique.ticker.in_(tickers))
                ).all()
            )

            for item in all_history_to_insert:
                if (item['ticker'], item['date_cours']) not in existing_entries:
                    session.add(CoursHistorique(
                        ticker=item['ticker'],
                        isin=None,
                        date_cours=item['date_cours'],
                        cours=item['cours'],
                        devise='EUR',
                        source='yahoo_backfill',
                    ))
                    total_inserted += 1

            try:
                session.commit()
                print(f'   ✅ Fin d\'insertion : {total_inserted} cours ajoutés en BDD')
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
    """Reconstruit les snapshots quotidiens en rejouant les transactions."""
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

        # Charger l'historique des cours depuis la BDD locale
        tickers = set()
        for t in transactions:
            if t.type_operation in ('achat', 'vente') and t.ticker:
                tickers.add(t.ticker)

        cours_par_ticker = defaultdict(list)
        if tickers:
            cours_rows = session.execute(
                select(CoursHistorique.ticker,
                       CoursHistorique.date_cours,
                       CoursHistorique.cours)
                .where(CoursHistorique.ticker.in_(tickers))
                .order_by(CoursHistorique.ticker, CoursHistorique.date_cours)
            ).all()
            for ticker, d, cours in cours_rows:
                cours_par_ticker[ticker].append((d, cours))

        # Initialisation des index pour la recherche chronologique en O(1) amorti
        cours_index_pointers = {ticker: 0 for ticker in tickers}

        def get_cours_a_date(ticker: str, target: date):
            """Dernier cours connu à une date donnée (forward-fill en O(1))."""
            cours_list = cours_par_ticker.get(ticker, [])
            if not cours_list:
                return None

            idx = cours_index_pointers[ticker]
            # On avance le pointeur de cours tant qu'il est inférieur ou égal à la date cible
            while idx < len(cours_list) and cours_list[idx][0] <= target:
                idx += 1

            cours_index_pointers[ticker] = idx

            # Si le pointeur a bougé, la valeur précédente est le dernier cours à jour
            if idx > 0:
                return cours_list[idx - 1][1]
            return None

        created = 0
        cash = 0.0
        positions_held = {}
        tx_index = 0
        current_date = start_date

        # Étape 1 : Calculer les positions (Quantité, PRU)
        for t in transactions:
            key = t.ticker or t.code or t.nom_titre
            is_asset_specific_tx = bool(key and t.quantite is not None)
            is_internal = _is_arbitrage_internal(t, arbitrage_parent_ids)

            # ... (logique de mise à jour des positions et du cash identique)
            # ─────────────────────────────────────────────
            # VERSEMENT
            # ─────────────────────────────────────────────
            if t.type_operation == 'versement':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] += t.quantite
                    else:
                        positions_held[key] = {
                            'ticker': t.ticker,
                            'quantite': t.quantite,
                            'pru': t.prix_unitaire if t.prix_unitaire is not None else 1.0,
                            'nom': t.nom_titre,
                            'categorie': t.categorie,
                        }
                else:
                    if not is_internal:
                        cash += t.montant

            # ─────────────────────────────────────────────
            # RETRAIT
            # ─────────────────────────────────────────────
            elif t.type_operation == 'retrait':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] -= t.quantite
                else:
                    if not is_internal:
                        cash -= t.montant

            # ─────────────────────────────────────────────
            # INTÉRÊTS (Fonds €)
            # ─────────────────────────────────────────────
            elif t.type_operation == 'interets':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] += t.quantite
                    else:
                        positions_held[key] = {
                            'ticker': t.ticker,
                            'quantite': t.quantite,
                            'pru': t.prix_unitaire if t.prix_unitaire is not None else 1.0,
                            'nom': t.nom_titre,
                            'categorie': t.categorie,
                        }
                else:
                    cash += t.montant

            # ─────────────────────────────────────────────
            # DIVIDENDE
            # ─────────────────────────────────────────────
            elif t.type_operation == 'dividende':
                if is_asset_specific_tx:
                    if key in positions_held:
                        old = positions_held[key]
                        new_qte = old['quantite'] + t.quantite
                        new_pru = (
                                          (old['quantite'] * old['pru']) +
                                          (t.quantite * (t.prix_unitaire or 0))
                                  ) / new_qte if new_qte > 0 else (t.prix_unitaire or 0)
                        old['quantite'] = new_qte
                        old['pru'] = new_pru
                    else:
                        positions_held[key] = {
                            'ticker': t.ticker,
                            'quantite': t.quantite,
                            'pru': t.prix_unitaire,
                            'nom': t.nom_titre,
                            'categorie': t.categorie,
                        }
                else:
                    cash += t.montant

            # ─────────────────────────────────────────────
            # FRAIS
            # ─────────────────────────────────────────────
            elif t.type_operation == 'frais':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] -= t.quantite
                else:
                    cash -= t.montant

            # ─────────────────────────────────────────────
            # ACHAT
            # ─────────────────────────────────────────────
            elif t.type_operation == 'achat':
                if not is_internal:
                    cash -= t.montant

                if t.quantite is not None and t.prix_unitaire is not None:
                    if key in positions_held:
                        old = positions_held[key]
                        new_qte = old['quantite'] + t.quantite
                        new_pru = (
                                          (old['quantite'] * old['pru']) +
                                          (t.quantite * t.prix_unitaire)
                                  ) / new_qte if new_qte > 0 else t.prix_unitaire
                        old['quantite'] = new_qte
                        old['pru'] = new_pru
                    else:
                        positions_held[key] = {
                            'ticker': t.ticker,
                            'quantite': t.quantite,
                            'pru': t.prix_unitaire,
                            'nom': t.nom_titre,
                            'categorie': t.categorie,
                        }

            # ─────────────────────────────────────────────
            # VENTE
            # ─────────────────────────────────────────────
            elif t.type_operation == 'vente':
                if not is_internal:
                    cash += t.montant

                if t.quantite is not None and key in positions_held:
                    positions_held[key]['quantite'] -= t.quantite

            # ✅ NETTOYAGE : Supprime la ligne si la quantité détenue devient nulle (seuil d'arrondi)
            if key in positions_held and positions_held[key]['quantite'] <= 1e-9:
                del positions_held[key]

            tx_index += 1

        # 🔄 APRÈS avoir calculé l'état final, on essaie de mettre à jour les cours actuels
        # si ce n'est pas un support manuel
        for key, pos in positions_held.items():
            ticker = pos.get('ticker')
            if ticker:
                # On essaie de récupérer le dernier cours connu en BDD
                last_cours = session.execute(
                    select(CoursHistorique.cours)
                    .where(CoursHistorique.ticker == ticker)
                    .order_by(CoursHistorique.date_cours.desc())
                    .limit(1)
                    .scalar_one_or_none())

                # Mise à jour de la table 'positions' pour l'affichage temps réel
                existing_pos = session.execute(
                    select(Position).where(
                        Position.portefeuille_id == portefeuille_id,
                        (Position.ticker == ticker) | (Position.nom == pos['nom'])
                    )
                ).scalar_one_or_none()

                if existing_pos and last_cours:
                    existing_pos.cours_actuel = last_cours
                    existing_pos.prix_moyen = pos['pru']
                    existing_pos.quantite = pos['quantite']

            # (Reprise de la boucle de valorisation quotidienne...)

            # ─────────────────────────────────────────────
            # Calcul de la valorisation des titres détenus
            # ─────────────────────────────────────────────
            valo_titres = 0.0
            for key, pos in positions_held.items():
                qte = pos['quantite']
                if qte <= 0:
                    continue

                ticker = pos['ticker']
                if ticker:
                    cours = get_cours_a_date(ticker, current_date)
                    if cours is not None:
                        valo_titres += qte * cours
                    else:
                        valo_titres += qte * pos['pru']
                else:
                    valo_titres += qte * pos['pru']

            valo_totale = cash + valo_titres

            session.add(Valorisation(
                portefeuille_id=portefeuille_id,
                date_valeur=current_date,
                montant=round(valo_totale, 2),
            ))
            created += 1

            current_date += timedelta(days=1)

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