"""Service de calcul des statistiques des portefeuilles via agrégats SQL.

Optimisation N+1 → 1 query :
Au lieu de charger toutes les positions/transactions en mémoire et d'itérer
en Python (lazy loading N+1), on utilise des requêtes SQL agrégées (SUM, CASE,
COUNT) qui retournent tous les résultats en une seule requête.

Le cache est stocké sur chaque instance Portefeuille._stats_cache.
"""

from __future__ import annotations

from sqlalchemy import select, func, case
from sqlalchemy.orm import Session

from database.models import Portefeuille, Position, Transaction


def preload_stats(session: Session, portefeuilles: list) -> None:
    """Pré-charge les stats agrégées sur les instances de Portefeuille.

    Remplit le cache ``_stats_cache`` de chaque instance via **une seule
    requête SQL**, évitant N+1 requêtes.
    """
    if not portefeuilles:
        return

    ids = [p.id for p in portefeuilles]

    # ── Sub-query 1 : valorisation par portefeuille ──────────────────────
    valo_sq = (
        select(
            Position.portefeuille_id,
            func.coalesce(
                func.sum(
                    func.coalesce(Position.quantite, 0)
                    * case(
                        (Position.cours_actuel.isnot(None), Position.cours_actuel),
                        else_=func.coalesce(Position.prix_moyen, 0),
                    )
                ),
                0,
            ).label("valorisation"),
        )
        .where(Position.portefeuille_id.in_(ids))
        .group_by(Position.portefeuille_id)
        .subquery()
    )

    # ── Sub-query 2 : total_verse par portefeuille (hors arbitrages) ────
    verse_sq = (
        select(
            Transaction.portefeuille_id,
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.type_operation == "versement", Transaction.montant),
                        (Transaction.type_operation == "retrait", -Transaction.montant),
                        else_=0,
                    )
                ),
                0,
            ).label("total_verse"),
        )
        .where(
            Transaction.portefeuille_id.in_(ids),
            Transaction.parent_transaction_id.is_(None),
        )
        .group_by(Transaction.portefeuille_id)
        .subquery()
    )

    # ── Sub-query 3 : nb_transactions total ─────────────────────────────
    nb_tx_sq = (
        select(
            Transaction.portefeuille_id,
            func.count().label("nb_transactions"),
        )
        .where(Transaction.portefeuille_id.in_(ids))
        .group_by(Transaction.portefeuille_id)
        .subquery()
    )

    # ── Requête principale ──────────────────────────────────────────────
    stmt = (
        select(
            Portefeuille.id,
            func.coalesce(valo_sq.c.valorisation, 0).label("valorisation_actuelle"),
            func.coalesce(verse_sq.c.total_verse, 0).label("total_verse"),
            func.coalesce(nb_tx_sq.c.nb_transactions, 0).label("nb_transactions"),
        )
        .outerjoin(valo_sq, Portefeuille.id == valo_sq.c.portefeuille_id)
        .outerjoin(verse_sq, Portefeuille.id == verse_sq.c.portefeuille_id)
        .outerjoin(nb_tx_sq, Portefeuille.id == nb_tx_sq.c.portefeuille_id)
        .where(Portefeuille.id.in_(ids))
    )

    rows = session.execute(stmt).all()
    results_map = {row.id: row for row in rows}

    for p in portefeuilles:
        row = results_map.get(p.id)

        if row is not None:
            valorisation = float(row.valorisation_actuelle or 0)
            # ✨ Si pas de positions, on regarde peut-être les valorisations manuelles historiques
            if valorisation == 0 and p.valorisations:
                valorisation = float(p.valorisations[-1].montant)

            total_verse = float(row.total_verse or 0)
            plus_value = valorisation - total_verse

        p._stats_cache = {
            "valorisation_actuelle": valorisation,
            "total_verse": total_verse,
            "plus_value": plus_value,
            "rendement_total_pct": (plus_value / total_verse * 100) if total_verse > 0 else 0.0,
            "nb_transactions": int(row.nb_transactions or 0),
        }
    else:
        p._stats_cache = _empty_stats()


def preload_single(session: Session, portefeuille_id: int) -> dict | None:
    """Raccourci : charge un portefeuille + ses stats en 2 requêtes."""
    p = session.get(Portefeuille, portefeuille_id)
    if p is None:
        return None
    preload_stats(session, [p])
    return p._stats_cache


def _empty_stats() -> dict:
    """Stats par défaut pour un portefeuille vide."""
    return {
        "valorisation_actuelle": 0.0,
        "total_verse": 0.0,
        "plus_value": 0.0,
        "rendement_total_pct": 0.0,
        "nb_transactions": 0,
    }