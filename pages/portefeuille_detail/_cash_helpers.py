"""Helpers pour la gestion automatique de la position Cash."""
from sqlalchemy import select
from database.models import Position


def impact_cash(type_operation: str, montant: float) -> float:
    """Retourne l'impact d'une transaction sur le solde de cash."""
    if type_operation in ('versement', 'dividende', 'vente'):
        return montant
    elif type_operation in ('retrait', 'frais', 'achat'):
        return -montant
    return 0


def ajuster_cash(session, portefeuille_id: int, delta: float):
    """Ajuste la position 'Cash' du portefeuille du montant delta."""
    if delta == 0:
        return

    cash_pos = session.execute(
        select(Position).where(
            Position.portefeuille_id == portefeuille_id,
            Position.nom == 'Cash'
        )
    ).scalar_one_or_none()

    if cash_pos is None:
        cash_pos = Position(
            portefeuille_id=portefeuille_id,
            nom='Cash',
            categorie='Cash',
            quantite=delta,
            prix_moyen=1.0,
            cours_actuel=1.0,
            devise='EUR',
        )
        session.add(cash_pos)
    else:
        cash_pos.quantite = (cash_pos.quantite or 0) + delta
        cash_pos.prix_moyen = 1.0
        cash_pos.cours_actuel = 1.0