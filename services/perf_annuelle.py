"""Calcul des rendements annuels (Modified Dietz) + rendement annualisé temps-pondéré."""
from datetime import date, timedelta
from database.db import get_session
from database.models import Portefeuille
from pages.portefeuille_detail._releve_annuel import get_situation_at_date


def _is_external_flow(t) -> bool:
    """Détermine si une transaction est un flux externe (apport/retrait de capital)."""
    if t.parent_transaction_id is not None:
        return False
    return t.type_operation in ('versement', 'retrait')


def get_rendements_annuels(portefeuille_id: int, max_years: int = 10) -> list[dict]:
    today = date.today()

    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf or not ptf.transactions:
            return []

        # On trie les transactions par date
        sorted_txs = sorted(ptf.transactions, key=lambda t: t.date_operation)
        first_year = sorted_txs[0].date_operation.year
        years = list(range(first_year, today.year + 1))[-max_years:]

        rendements = []

        for year in years:
            debut_annee = date(year, 1, 1)
            # Pour la première année, le début est la date de la première transaction
            debut = max(debut_annee, sorted_txs[0].date_operation) if year == first_year else debut_annee
            fin = date(year, 12, 31) if year < today.year else today

            nb_jours = (fin - debut).days + 1
            if nb_jours <= 0:
                continue

            situation_debut = get_situation_at_date(
                portefeuille_id,
                date(year - 1, 12, 31) if year > first_year else (debut - timedelta(days=1))
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
    """Rendement annualisé temps-pondéré (TWR) basé sur la durée réelle."""
    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf or not ptf.transactions:
            return 0.0

        # Date de début réelle
        first_date = min(t.date_operation for t in ptf.transactions)
        today = date.today()
        nb_jours_total = (today - first_date).days

        if nb_jours_total <= 0:
            return 0.0

        nb_annees_reelles = nb_jours_total / 365.25

    rendements = get_rendements_annuels(portefeuille_id, max_years=20)
    if not rendements:
        return 0.0

    # On compose les rendements annuels (Modified Dietz par an)
    rendements = sorted(rendements, key=lambda r: r['annee'])
    cumulative = 1.0
    for r in rendements:
        cumulative *= (1 + r['rendement_pct'] / 100)

    # Annualisation sur la durée réelle totale
    twr_annualise = (cumulative ** (1 / nb_annees_reelles) - 1) * 100
    return round(twr_annualise, 2)

    nb_annees = len(rendements)
    if nb_annees == 0:
        return 0.0

    twr_annualise = (cumulative ** (1 / nb_annees) - 1) * 100
    return round(twr_annualise, 2)