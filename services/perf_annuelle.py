"""Calcul des rendements annuels (performance time-weighted simple)."""
from datetime import date
from sqlalchemy import select

from database.db import get_session
from database.models import Portefeuille
from pages.portefeuille_detail._releve_annuel import get_situation_at_date


def get_rendements_annuels(portefeuille_id: int, max_years: int = 10) -> list[dict]:
    """Calcule les rendements année par année.

    Formule (time-weighted simple) :
        Rendement(N) = (Valo_31/12/N - Valo_31/12/N-1 - flux_nets_N) / Valo_31/12/N-1 × 100

    où flux_nets_N = versements externes - retraits externes durant l'année N.

    Returns:
        Liste de dicts triés du plus récent au plus ancien :
        [{'annee': 2024, 'rendement_pct': 12.3, 'valo_debut': 1000, 'valo_fin': 1150,
          'flux_nets': 50}, ...]
    """
    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf or not ptf.transactions:
            return []

        first_year = min(t.date_operation.year for t in ptf.transactions)
        current_year = date.today().year

        # Années à analyser : depuis la 1ère année jusqu'à l'année en cours (incluse)
        # 🆕 L'année en cours est incluse (calculée jusqu'à la date du jour)
        years_to_analyze = list(range(first_year, current_year + 1))
        if not years_to_analyze:
            return []

        # Limiter aux N dernières années
        years_to_analyze = years_to_analyze[-max_years:]

        # Pré-calculer les flux nets externes par année
        flux_par_annee = {}
        for t in ptf.transactions:
            if t.parent_transaction_id is not None:
                continue  # Exclure les arbitrages internes
            year = t.date_operation.year
            if t.type_operation == 'versement':
                # Filtrer les versements vers Fonds € (asset-specific) qui ne sont pas externes
                # Un vrai versement externe a montant > 0 et n'est pas lié à un asset spécifique
                # → on prend tous les versements parent_id IS NULL (déjà filtré ci-dessus)
                flux_par_annee.setdefault(year, 0)
                flux_par_annee[year] += t.montant
            elif t.type_operation == 'retrait':
                flux_par_annee.setdefault(year, 0)
                flux_par_annee[year] -= t.montant

    # Calculer les valos de fin d'année (utilise get_situation_at_date qui est éprouvé)
    rendements = []
    valo_precedente = None

    today = date.today()

    for year in years_to_analyze:
        # 🆕 Pour l'année en cours, on prend la date du jour au lieu du 31/12
        if year == today.year:
            target_date = today
        else:
            target_date = date(year, 12, 31)
        situation = get_situation_at_date(portefeuille_id, target_date)

        if situation is None:
            continue

        valo_fin = situation['valo_totale']
        flux_nets = flux_par_annee.get(year, 0)

        if valo_precedente is not None and valo_precedente > 0:
            # Performance time-weighted simple : on retire l'impact des flux externes
            gain_brut = valo_fin - valo_precedente
            gain_net = gain_brut - flux_nets
            rendement_pct = (gain_net / valo_precedente) * 100
            valo_debut = valo_precedente
        else:
            # Première année : calcul approximatif (gain / capital moyen investi)
            # On utilise (valo_fin - flux_nets) / flux_nets comme rendement
            if flux_nets > 0:
                rendement_pct = ((valo_fin - flux_nets) / flux_nets) * 100
                valo_debut = 0
            else:
                rendement_pct = 0
                valo_debut = 0

        rendements.append({
            'annee': year,
            'rendement_pct': rendement_pct,
            'valo_debut': valo_debut,
            'valo_fin': valo_fin,
            'flux_nets': flux_nets,
        })

        valo_precedente = valo_fin

    # Trier du plus récent au plus ancien
    rendements.sort(key=lambda r: r['annee'], reverse=True)
    return rendements