# services/labels.py  — nouveau module

from database.db import get_session
from database.models import SupportLabel


def get_display_name(ticker: str | None, code: str | None, fallback: str) -> str:
    """
    Retourne le nom à afficher pour un support.
    Priorité : custom_name (BDD) > fallback (nom Yahoo/Boursorama)

    Args:
        ticker:   ticker Yahoo (ex: 'MC.PA'), peut être None
        code:     code ISIN (ex: 'FR0010149120'), peut être None
        fallback: nom brut retourné par l'API (ex: 'LVMH MOET HENNESSY LOUIS VUI')
    """
    if not ticker and not code:
        return fallback

    with get_session() as session:
        q = session.query(SupportLabel)
        if ticker:
            label = q.filter_by(ticker=ticker).first()
            if label:
                return label.custom_name
        if code:
            label = q.filter_by(code=code).first()
            if label:
                return label.custom_name

    return fallback


def set_custom_name(
        ticker: str | None,
        code: str | None,
        custom_name: str,
        original_name: str | None = None
) -> SupportLabel:
    """
    Crée ou met à jour le nom personnalisé d'un support.
    Upsert : si un label existe déjà pour ce ticker/code, il est mis à jour.
    """
    with get_session() as session:
        label = None
        if ticker:
            label = session.query(SupportLabel).filter_by(ticker=ticker).first()
        if not label and code:
            label = session.query(SupportLabel).filter_by(code=code).first()

        if label:
            label.custom_name = custom_name
            label.updated_at = datetime.utcnow()
        else:
            label = SupportLabel(
                ticker=ticker,
                code=code,
                custom_name=custom_name,
                original_name=original_name,
            )
            session.add(label)

        session.commit()
        session.refresh(label)
        return label


def delete_custom_name(ticker: str | None, code: str | None) -> bool:
    """
    Supprime le label personnalisé → retour au nom Yahoo/Boursorama.
    Retourne True si un label a été supprimé, False sinon.
    """
    with get_session() as session:
        label = None
        if ticker:
            label = session.query(SupportLabel).filter_by(ticker=ticker).first()
        if not label and code:
            label = session.query(SupportLabel).filter_by(code=code).first()

        if label:
            session.delete(label)
            session.commit()
            return True
        return False