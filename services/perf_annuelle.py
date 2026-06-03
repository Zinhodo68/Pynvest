"""Calcul des rendements annuels et de la performance annualisée.

- Les rendements annuels affichés dans la KPI expandable sont calculés en
  Modified Dietz sur chaque année civile.
- La performance annualisée du portefeuille est calculée en TRI/XIRR sur les
  flux externes et la valorisation actuelle.

Point important : pour une période qui se termine aujourd'hui, on utilise la
valorisation réelle courante du portefeuille (positions.cours_actuel / stats
agrégées) plutôt qu'une reconstruction historique. Sinon, en l'absence de cours
historiques à jour, la perf. de l'année courante pouvait rester proche de 0 %
alors que la valorisation actuelle affichait bien une plus-value.
"""
from datetime import date, timedelta

from database.db import get_session
from database.models import Portefeuille
from pages.portefeuille_detail._releve_annuel import get_situation_at_date
from services.portfolio_stats import preload_stats
from services.perf_xirr import get_xirr_for_portefeuilles


def _is_external_flow(t) -> bool:
    """Détermine si une transaction est un flux externe (apport/retrait de capital)."""
    if t.parent_transaction_id is not None:
        return False
    return t.type_operation in ('versement', 'retrait')


def _get_current_situation(portefeuille_id: int) -> dict | None:
    """Retourne la situation courante à partir des stats réelles du portefeuille.

    ``get_situation_at_date`` reconstruit l'historique à partir des transactions
    et des cours historiques. C'est adapté pour un 31/12 passé, mais pas pour
    ``today`` lorsque les cours historiques ne sont pas synchronisés avec les
    cours actuels des positions. Pour la fin de période courante, la source de
    vérité doit être la même que celle des KPI Valorisation / Capital investi.
    """
    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf:
            return None

        preload_stats(session, [ptf])

        valo_totale = float(ptf.valorisation_actuelle or 0.0)
        total_verse = float(ptf.total_verse or 0.0)
        plus_value = valo_totale - total_verse

        return {
            'valo_totale': valo_totale,
            'total_verse': total_verse,
            'plus_value': plus_value,
            'plus_value_pct': (plus_value / total_verse * 100) if total_verse > 0 else 0.0,
        }


def _get_situation_for_period_end(portefeuille_id: int, target: date) -> dict | None:
    """Situation à une date, en utilisant la valo courante si target >= today."""
    if target >= date.today():
        return _get_current_situation(portefeuille_id)
    return get_situation_at_date(portefeuille_id, target)


def get_rendements_annuels(portefeuille_id: int, max_years: int = 10) -> list[dict]:
    today = date.today()

    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf or not ptf.transactions:
            return []

        # Ignore les opérations futures éventuelles : elles ne doivent pas
        # influencer une performance calculée à aujourd'hui.
        sorted_txs = sorted(
            [t for t in ptf.transactions if t.date_operation <= today],
            key=lambda t: t.date_operation,
        )
        if not sorted_txs:
            return []

        first_year = sorted_txs[0].date_operation.year
        years = list(range(first_year, today.year + 1))[-max_years:]

        rendements = []

        for year in years:
            debut_annee = date(year, 1, 1)
            # Pour la première année, le début est la date de la première transaction.
            debut = max(debut_annee, sorted_txs[0].date_operation) if year == first_year else debut_annee
            fin = date(year, 12, 31) if year < today.year else today

            nb_jours = (fin - debut).days + 1
            if nb_jours <= 0:
                continue

            situation_debut = get_situation_at_date(
                portefeuille_id,
                date(year - 1, 12, 31) if year > first_year else (debut - timedelta(days=1)),
            )
            situation_fin = _get_situation_for_period_end(portefeuille_id, fin)

            if situation_fin is None:
                continue

            valo_debut = situation_debut['valo_totale'] if situation_debut else 0.0
            valo_fin = situation_fin['valo_totale']

            flux_total = 0.0
            flux_pondere = 0.0

            for t in sorted_txs:
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
    """Performance annualisée du portefeuille.

    Historiquement cette fonction composait les rendements annuels Modified
    Dietz puis annualisait sur la durée depuis la première transaction. Cela
    pouvait produire une valeur très sous-estimée si l'historique annuel était
    tronqué ou si la valorisation courante n'était pas utilisée dans l'année en
    cours.

    Pour un KPI "perf. annualisée" exploitable avec des apports/retraits, on
    utilise désormais le TRI/XIRR : flux externes datés + valorisation courante.
    """
    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf:
            return 0.0

        preload_stats(session, [ptf])
        current_value = float(ptf.valorisation_actuelle or 0.0)

    xirr = get_xirr_for_portefeuilles([portefeuille_id], current_value)
    return xirr if xirr is not None else 0.0
