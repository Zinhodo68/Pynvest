"""Calcul des rendements annuels (Modified Dietz) + rendement annualisé temps-pondéré."""
from datetime import date
from database.db import get_session
from database.models import Portefeuille
from pages.portefeuille_detail._releve_annuel import get_situation_at_date


def _is_external_flow(t) -> bool:
    if t.parent_transaction_id is not None:
        return False
    if t.type_operation not in ('versement', 'retrait'):
        return False

    LIQUIDITY_CATEGORIES = {'Fonds €', 'Fonds Euro', 'Cash'}
    is_asset_specific = bool((t.ticker or t.code or t.nom_titre) and t.quantite is not None)

    if is_asset_specific:
        return t.categorie in LIQUIDITY_CATEGORIES
    else:
        return True


def get_rendements_annuels(portefeuille_id: int, max_years: int = 10) -> list[dict]:
    today = date.today()

    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf or not ptf.transactions:
            return []

        first_year = min(t.date_operation.year for t in ptf.transactions)
        years = list(range(first_year, today.year + 1))[-max_years:]

        rendements = []

        for year in years:
            debut = date(year, 1, 1)
            fin = date(year, 12, 31) if year < today.year else today
            nb_jours = (fin - debut).days + 1

            situation_debut = get_situation_at_date(
                portefeuille_id,
                date(year - 1, 12, 31) if year > first_year else debut
            )
            situation_fin = get_situation_at_date(portefeuille_id, fin)

            if situation_fin is None:
                continue

            valo_debut = situation_debut['valo_totale'] if situation_debut else 0.0
            valo_fin = situation_fin['valo_totale']

            flux_total = 0.0
            flux_pondere = 0.0

            for t in ptf.transactions:
                if not (debut <= t.date_operation <= fin):
                    continue
                if not _is_external_flow(t):
                    continue

                montant = t.montant if t.type_operation == 'versement' else -t.montant
                flux_total += montant

                jours_restants = (fin - t.date_operation).days + 1
                poids = jours_restants / nb_jours
                flux_pondere += montant * poids

            denominateur = valo_debut + flux_pondere

            if denominateur > 1.0:
                gain = valo_fin - valo_debut - flux_total
                rendement_pct = (gain / denominateur) * 100
            else:
                rendement_pct = 0.0

            rendements.append({
                'annee': year,
                'rendement_pct': round(rendement_pct, 2),
                'valo_debut': round(valo_debut, 2),
                'valo_fin': round(valo_fin, 2),
                'flux_nets': round(flux_total, 2),
                'is_first_year': year == first_year,
            })

        rendements.sort(key=lambda r: r['annee'], reverse=True)
        return rendements


def get_rendement_annualise_time_weighted(portefeuille_id: int) -> float:
    """Rendement annualisé temps-pondéré (TWR)."""
    rendements = get_rendements_annuels(portefeuille_id, max_years=20)
    if not rendements:
        return 0.0

    rendements = sorted(rendements, key=lambda r: r['annee'])
    cumulative = 1.0
    for r in rendements:
        cumulative *= (1 + r['rendement_pct'] / 100)

    nb_annees = len(rendements)
    if nb_annees == 0:
        return 0.0

    twr_annualise = (cumulative ** (1 / nb_annees) - 1) * 100
    return round(twr_annualise, 2)