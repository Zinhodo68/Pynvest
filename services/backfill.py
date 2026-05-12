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
    """Reconstruit les snapshots quotidiens en rejouant les transactions."""

    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        if not p or not p.transactions:
            return 0

        # Nettoyage
        session.query(Valorisation).filter(
            Valorisation.portefeuille_id == portefeuille_id
        ).delete()
        session.flush()

        transactions = sorted(p.transactions, key=lambda t: t.date_operation)
        start_date = transactions[0].date_operation
        end_date = date.today()

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
        # Positions détenues par ticker : {ticker: {'quantite': X, 'pru': Y, 'nom': Z, 'categorie': C}}
        # Pour les titres sans ticker, on utilise une clé alternative
        positions_held = {}
        tx_index = 0
        current_date = start_date

        while current_date <= end_date:
            # Rejouer toutes les transactions du jour
            while tx_index < len(transactions) and transactions[tx_index].date_operation <= current_date:
                t = transactions[tx_index]

                if t.type_operation == 'versement':
                    cash += t.montant
                elif t.type_operation == 'retrait':
                    cash -= t.montant
                elif t.type_operation == 'frais':
                    cash -= t.montant
                elif t.type_operation == 'achat':
                    cash -= t.montant
                    # Mise à jour de la position
                    key = t.ticker or t.code or t.nom_titre or 'inconnu'
                    if t.quantite is not None and t.prix_unitaire is not None:
                        if key in positions_held:
                            old = positions_held[key]
                            new_qte = old['quantite'] + t.quantite
                            new_pru = (
                                              (old['quantite'] * old['pru']) +
                                              (t.quantite * t.prix_unitaire)
                                      ) / new_qte
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
                elif t.type_operation == 'vente':
                    cash += t.montant
                    key = t.ticker or t.code or t.nom_titre or 'inconnu'
                    if t.quantite is not None and key in positions_held:
                        positions_held[key]['quantite'] -= t.quantite
                        # Si la quantité tombe à 0, on peut garder l'entrée à 0
                        # (ça n'impacte pas la valo)

                tx_index += 1

            # Calculer la valorisation des titres détenus
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
                        # Fallback : PRU
                        valo_titres += qte * pos['pru']
                else:
                    # Pas de ticker : on utilise toujours le PRU (OPCVM, SCPI)
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