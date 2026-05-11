"""Reconstruit l'historique des valorisations depuis la création d'un portefeuille."""
from datetime import date, timedelta
from sqlalchemy import select

from database.db import get_session
from database.models import Portefeuille, Valorisation, Transaction


def backfill_portefeuille(portefeuille_id: int) -> int:
    """Crée un snapshot quotidien depuis la date de création du portefeuille
    en se basant sur les transactions (versements/retraits/achats/ventes).

    ⚠️ Approximation : suppose que les positions valent leur PRU jour J.
    Un vrai calcul nécessiterait l'historique des cours par jour.
    """
    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        if not p or not p.date_creation:
            return 0

        # Date de départ : création du portefeuille
        start_date = p.date_creation
        end_date = date.today()

        # Existing snapshots
        existing_dates = set(v.date_valeur for v in p.valorisations)

        # Transactions triées par date
        transactions = sorted(p.transactions, key=lambda t: t.date_operation)

        created = 0
        cumul_apports = 0
        current_date = start_date
        tx_index = 0

        while current_date <= end_date:
            # Cumuler les transactions jusqu'à cette date
            while tx_index < len(transactions) and \
                    transactions[tx_index].date_operation <= current_date:
                t = transactions[tx_index]
                if t.type_operation == 'versement':
                    cumul_apports += t.montant
                elif t.type_operation == 'retrait':
                    cumul_apports -= t.montant
                tx_index += 1

            # Créer un snapshot si pas déjà existant
            if current_date not in existing_dates and cumul_apports > 0:
                session.add(Valorisation(
                    portefeuille_id=portefeuille_id,
                    date_valeur=current_date,
                    montant=cumul_apports,  # Approximation
                ))
                created += 1

            current_date += timedelta(days=1)

        session.commit()
        return created