"""Reconstruit l'historique des valorisations depuis la création d'un portefeuille."""
from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import select

from database.db import get_session
from database.models import Portefeuille, Valorisation, CoursHistorique
from services._yahoo import get_yahoo_history, get_currency_rate


def backfill_cours_historique(portefeuille_id: int) -> int:
    """Télécharge l'historique complet des cours pour toutes les positions
    d'un portefeuille et les stocke dans CoursHistorique.

    Évite les doublons : si un cours existe déjà pour (ticker, date), il est ignoré.

    Returns:
        Nombre de nouveaux cours insérés.
    """
    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        if not p or not p.date_creation:
            return 0

        start_date = p.date_creation
        end_date = date.today()

        # Positions avec ticker (on ignore Cash et titres sans ticker)
        positions = [
            pos for pos in p.positions
            if pos.ticker and pos.nom != 'Cash'
        ]

        if not positions:
            print('   ℹ️  Aucune position avec ticker à backfiller')
            return 0

        # Tickers uniques à télécharger
        tickers = list(set(pos.ticker for pos in positions))
        print(f'   📥 Téléchargement historique pour {len(tickers)} ticker(s)')

        total_inserted = 0

        for ticker in tickers:
            # 1. Vérifier les dates déjà en BDD pour ce ticker
            existing_dates = set(
                row[0] for row in session.execute(
                    select(CoursHistorique.date_cours)
                    .where(CoursHistorique.ticker == ticker)
                ).all()
            )

            # 2. Télécharger l'historique complet
            history = get_yahoo_history(ticker, start_date, end_date)

            if not history:
                continue

            # 3. Récupérer le taux de change si nécessaire (1 fois pour tout l'historique)
            # ⚠️ Approximation : on utilise le taux actuel pour tout l'historique
            # (sinon il faudrait l'historique des taux, plus complexe)
            currency = history[0]['currency']
            rate = 1.0
            if currency != 'EUR':
                rate = get_currency_rate(currency, 'EUR') or 1.0

            # 4. Insérer en BDD (sans doublons)
            inserted = 0
            for h in history:
                if h['date'] in existing_dates:
                    continue  # Skip doublons

                cours_eur = h['cours'] * rate

                session.add(CoursHistorique(
                    ticker=ticker,
                    isin=None,
                    date_cours=h['date'],
                    cours=cours_eur,
                    devise='EUR',
                    source='yahoo_backfill',
                ))
                inserted += 1

            print(f'   ✅ {ticker}: {inserted} nouveaux cours insérés')
            total_inserted += inserted

        session.commit()
        return total_inserted


def backfill_valorisations(portefeuille_id: int) -> int:
    """Reconstruit les snapshots quotidiens de valorisation."""

    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        if not p:
            return 0

        # 🧹 Nettoyer les anciennes valorisations
        session.query(Valorisation).filter(
            Valorisation.portefeuille_id == portefeuille_id
        ).delete()
        session.flush()

        transactions = sorted(p.transactions, key=lambda t: t.date_operation)
        if not transactions:
            return 0

        # 🎯 La date de départ = la PREMIÈRE TRANSACTION (pas date_creation)
        # Comme ça on ne crée pas de snapshots avant que de l'argent soit présent
        start_date = transactions[0].date_operation
        end_date = date.today()

        positions_bourse = [
            pos for pos in p.positions
            if pos.nom != 'Cash' and (pos.quantite or 0) > 0
        ]

        # Charger les historiques de cours
        history_by_position = {}
        for pos in positions_bourse:
            stmt = select(
                CoursHistorique.date_cours,
                CoursHistorique.cours
            ).order_by(CoursHistorique.date_cours)

            if pos.ticker:
                stmt = stmt.where(CoursHistorique.ticker == pos.ticker)
            elif pos.code:
                stmt = stmt.where(CoursHistorique.isin == pos.code)
            else:
                history_by_position[pos.id] = []
                continue

            history_by_position[pos.id] = session.execute(stmt).all()

        def get_last_cours(rows, target_date):
            last = None
            for d, c in rows:
                if d <= target_date:
                    last = c
                else:
                    break
            return last

        created = 0
        cash = 0.0
        tx_index = 0
        current_date = start_date

        while current_date <= end_date:
            # Appliquer les transactions du jour
            while tx_index < len(transactions) and transactions[tx_index].date_operation <= current_date:
                t = transactions[tx_index]
                if t.type_operation == 'versement':
                    cash += t.montant
                elif t.type_operation == 'retrait':
                    cash -= t.montant
                elif t.type_operation == 'achat':
                    cash -= t.montant
                elif t.type_operation == 'vente':
                    cash += t.montant
                tx_index += 1

            # 🎯 Valoriser les titres SEULEMENT s'ils ont été achetés
            valo_titres = 0.0
            for pos in positions_bourse:
                date_ouverture = pos.date_ouverture
                if date_ouverture is None:
                    # Si pas de date d'ouverture, on suppose qu'elle existe depuis le début
                    date_ouverture = start_date

                # 🚨 LE FIX CRITIQUE : ne pas valoriser avant l'achat
                if current_date < date_ouverture:
                    continue

                rows = history_by_position.get(pos.id, [])
                cours = get_last_cours(rows, current_date)

                if cours is None:
                    cours = pos.prix_moyen or 0.0

                valo_titres += (pos.quantite or 0) * cours

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
    """Lance les 2 étapes du backfill : cours historiques + valorisations.

    Returns:
        {'cours_inserts': N, 'valorisations_creees': N}
    """
    print(f'🔄 Backfill du portefeuille #{portefeuille_id}')

    # 1. Télécharger l'historique des cours
    cours_inserts = backfill_cours_historique(portefeuille_id)

    # 2. Reconstruire les valorisations
    valos_creees = backfill_valorisations(portefeuille_id)

    print(f'✅ Backfill terminé : {cours_inserts} cours, {valos_creees} valorisations')
    return {
        'cours_inserts': cours_inserts,
        'valorisations_creees': valos_creees,
    }