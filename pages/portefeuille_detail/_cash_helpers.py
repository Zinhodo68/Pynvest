"""Helpers pour la gestion automatique de la position Cash / Fonds €."""
from sqlalchemy import select
from database.models import Position

# Catégories considérées comme "réserves de liquidités"
CASH_CATEGORIES = ('Cash', 'Fonds €', 'Fonds Euro')


def impact_cash(type_operation: str, montant: float) -> float:
    """Retourne l'impact d'une transaction sur le solde de cash."""
    if type_operation in ('versement', 'dividende', 'vente'):
        return montant
    elif type_operation in ('retrait', 'frais', 'achat'):
        return -montant
    return 0


def get_cash_position(session, portefeuille_id: int, target_position_id: int | None = None):
    """Retourne la position cash/fonds € à créditer pour ce portefeuille.

    Priorité :
    1. Position explicitement ciblée (target_position_id)
    2. Position avec catégorie Cash/Fonds € ayant la plus grosse quantité
    3. Position nommée 'Cash' (legacy)
    4. None
    """
    # 1. Cible explicite
    if target_position_id is not None:
        pos = session.get(Position, target_position_id)
        if pos and pos.portefeuille_id == portefeuille_id:
            return pos

    # 2. Plus grosse réserve de liquidités du portefeuille
    cash_positions = session.execute(
        select(Position).where(
            Position.portefeuille_id == portefeuille_id,
            Position.categorie.in_(CASH_CATEGORIES),
        ).order_by(Position.quantite.desc())
    ).scalars().all()

    if cash_positions:
        return cash_positions[0]

    # 3. Legacy : position nommée 'Cash'
    return session.execute(
        select(Position).where(
            Position.portefeuille_id == portefeuille_id,
            Position.nom == 'Cash',
        )
    ).scalar_one_or_none()


def ajuster_cash(session, portefeuille_id: int, delta: float,
                 target_position_id: int | None = None):
    """Ajuste la position cash / fonds € du portefeuille du montant delta.

    Args:
        session: session SQLAlchemy
        portefeuille_id: id du portefeuille
        delta: montant à ajouter (positif) ou retirer (négatif)
        target_position_id: id explicite du fonds € à créditer (optionnel)
    """
    if delta == 0:
        return

    cash_pos = get_cash_position(session, portefeuille_id, target_position_id)

    if cash_pos is None:
        # Aucune position de cash → on en crée une par défaut nommée 'Cash'
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
        # ⚠️ Ne PAS forcer prix_moyen/cours_actuel pour les fonds € qui pourraient
        # avoir des valeurs > 1 dans d'autres contextes. On ne touche que si c'est
        # une vraie position 'Cash' à 1€/part.
        if cash_pos.nom == 'Cash' and cash_pos.categorie == 'Cash':
            cash_pos.prix_moyen = 1.0
            cash_pos.cours_actuel = 1.0