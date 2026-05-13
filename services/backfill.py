"""Reconstruit l'historique des valorisations à partir des transactions.

Logique de calcul :
- Pour chaque jour depuis la première transaction :
  - On rejoue toutes les transactions jusqu'à ce jour
  - On calcule les positions détenues (par ticker/code)
  - On valorise chaque position au cours du jour
  - On ajoute le cash résiduel
"""
from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import select

from database.db import get_session
from database.models import Portefeuille, Valorisation, CoursHistorique, Transaction
from services._yahoo import get_yahoo_history, get_currency_rate


def backfill_cours_historique(portefeuille_id: int) -> int:
    """Télécharge l'historique Yahoo pour les tickers présents dans les transactions.

    Source = transactions d'achat/vente (et pas seulement positions actuelles),
    pour gérer les titres déjà revendus.
    """
    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        if not p or not p.transactions:
            return 0

        # Date de départ = première transaction d'achat
        achats = [t for t in p.transactions if t.type_operation == 'achat']
        if not achats:
            print('   ℹ️  Aucun achat enregistré')
            return 0

        start_date = min(t.date_operation for t in achats)
        end_date = date.today()
        total_inserted = 0

        # Récupérer tous les tickers Yahoo présents dans les transactions
        tickers = set()
        for t in p.transactions:
            if t.type_operation in ('achat', 'vente') and t.ticker:
                tickers.add(t.ticker)

        if not tickers:
            print('   ⚠️ Aucun ticker Yahoo dans les transactions')
            return 0

        print(f'   📥 Téléchargement historique pour {len(tickers)} ticker(s)')

        for ticker in tickers:
            existing_dates = set(
                row[0] for row in session.execute(
                    select(CoursHistorique.date_cours)
                    .where(CoursHistorique.ticker == ticker)
                ).all()
            )

            history = get_yahoo_history(ticker, start_date, end_date)
            if not history:
                print(f'   ⚠️ Aucun historique récupéré pour {ticker}')
                continue

            currency = history[0]['currency']
            rate = 1.0
            if currency != 'EUR':
                rate = get_currency_rate(currency, 'EUR') or 1.0

            inserted = 0
            for h in history:
                if h['date'] in existing_dates:
                    continue

                session.add(CoursHistorique(
                    ticker=ticker,
                    isin=None,
                    date_cours=h['date'],
                    cours=h['cours'] * rate,
                    devise='EUR',
                    source='yahoo_backfill',
                ))
                inserted += 1

            print(f'   ✅ {ticker}: {inserted} cours insérés')
            total_inserted += inserted

        session.commit()
        return total_inserted


def backfill_valorisations(portefeuille_id: int) -> int:
    """Reconstruit les snapshots quotidiens en rejouant les transactions.

    Règles arbitrages internes :
    - Une transaction est "interne" si elle a un parent OU si elle est parente.
    - Pour les achats/ventes/versements/retraits internes : NE PAS toucher au cash.
      Seules les positions/quantités évoluent (transfert pur entre actifs).
    - Pour les versements/retraits externes (sans lien parent/enfant) : impacter le cash.
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

        # 🆕 Précalcul : IDs des transactions qui ont un enfant (= parents d'arbitrage)
        parent_ids_with_child = {
            t.parent_transaction_id for t in transactions
            if t.parent_transaction_id is not None
        }

        # Charger l'historique des cours pour tous les tickers présents dans les transactions
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

        def get_cours_a_date(ticker: str, target: date):
            """Dernier cours connu à une date donnée (forward-fill)."""
            cours_list = cours_par_ticker.get(ticker, [])
            last = None
            for d, c in cours_list:
                if d <= target:
                    last = c
                else:
                    break
            return last

        created = 0
        cash = 0.0
        positions_held = {}
        tx_index = 0
        current_date = start_date

        while current_date <= end_date:
            while tx_index < len(transactions) and transactions[tx_index].date_operation <= current_date:
                t = transactions[tx_index]

                key = t.ticker or t.code or t.nom_titre
                is_asset_specific_tx = bool(key and t.quantite is not None)
                is_arbitrage_child = t.parent_transaction_id is not None
                is_arbitrage_parent = t.id in parent_ids_with_child
                # 🛡️ Une tx est "interne" si elle est parent OU enfant d'arbitrage
                is_internal = is_arbitrage_child or is_arbitrage_parent

                # ─────────────────────────────────────────────
                # VERSEMENT
                # ─────────────────────────────────────────────
                if t.type_operation == 'versement':
                    if is_asset_specific_tx:
                        # Versement vers un actif (Fonds €)
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
                        # Cash : NE PAS toucher (que ce soit versement initial sur Fonds €
                        # ou arbitrage IN — dans les deux cas le cash n'est pas concerné)
                    else:
                        # Vrai apport externe d'argent en cash
                        cash += t.montant

                # ─────────────────────────────────────────────
                # RETRAIT
                # ─────────────────────────────────────────────
                elif t.type_operation == 'retrait':
                    if is_asset_specific_tx:
                        if key in positions_held:
                            positions_held[key]['quantite'] -= t.quantite
                        # Cash inchangé
                    else:
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
                    # 🛡️ Arbitrage interne : l'argent vient d'un Fonds € (pas du cash)
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
                    # 🛡️ Arbitrage interne : l'argent va vers un Fonds € (pas vers le cash)
                    if not is_internal:
                        cash += t.montant
                    if t.quantite is not None and key in positions_held:
                        positions_held[key]['quantite'] -= t.quantite

                tx_index += 1

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

        session.commit()
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