# services/perf_xirr.py

from datetime import date
from sqlalchemy import select

from database.db import get_session
from database.models import Transaction


def _is_external_flow(t) -> bool:
    """Détermine si une transaction est un flux externe (apport/retrait de capital)."""
    if t.parent_transaction_id is not None:
        return False
    return t.type_operation in ('versement', 'retrait')


def _xirr(flows: list[tuple[date, float]]) -> float | None:
    """
    Calcule un TRI annualisé à partir de flux datés.

    Convention :
    - versement utilisateur = flux négatif
    - retrait utilisateur = flux positif
    - valorisation finale = flux positif
    """
    if len(flows) < 2:
        return None

    flows = sorted(flows, key=lambda x: x[0])
    d0 = flows[0][0]

    amounts = [amount for _, amount in flows]

    if not any(a < 0 for a in amounts) or not any(a > 0 for a in amounts):
        return None

    def npv(rate: float) -> float:
        total = 0.0
        for flow_date, amount in flows:
            years = (flow_date - d0).days / 365.25
            total += amount / ((1 + rate) ** years)
        return total

    low = -0.9999
    high = 10.0  # 1000 %

    f_low = npv(low)
    f_high = npv(high)

    # On élargit si besoin
    while f_low * f_high > 0 and high < 1_000_000:
        high *= 2
        f_high = npv(high)

    if f_low * f_high > 0:
        return None

    for _ in range(100):
        mid = (low + high) / 2
        f_mid = npv(mid)

        if abs(f_mid) < 1e-7:
            return mid * 100

        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    return ((low + high) / 2) * 100


def get_xirr_for_portefeuilles(
    portefeuille_ids: list[int] | tuple[int, ...],
    current_value: float,
) -> float | None:
    """
    Calcule le TRI annualisé consolidé d'une liste de portefeuilles.

    current_value doit être la valorisation actuelle totale de ces portefeuilles.
    """
    ids = tuple(int(pid) for pid in portefeuille_ids if pid is not None)

    if not ids:
        return None

    flows: list[tuple[date, float]] = []

    with get_session() as session:
        transactions = session.execute(
            select(Transaction)
            .where(Transaction.portefeuille_id.in_(ids))
            .order_by(Transaction.date_operation)
        ).scalars().all()

        for t in transactions:
            if not _is_external_flow(t):
                continue

            if t.type_operation == 'versement':
                flows.append((t.date_operation, -abs(t.montant)))
            elif t.type_operation == 'retrait':
                flows.append((t.date_operation, abs(t.montant)))

    if current_value and current_value > 0:
        flows.append((date.today(), float(current_value)))

    result = _xirr(flows)

    if result is None:
        return None

    return round(result, 2)