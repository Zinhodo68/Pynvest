"""Calcul des rendements annuels avec la méthode Modified Dietz."""
from datetime import date
from database.db import get_session
from database.models import Portefeuille
from pages.portefeuille_detail._releve_annuel import get_situation_at_date


# Types de transactions considérés comme des "vrais" arbitrages internes
# (par opposition aux liens parent/enfant pour frais ou dividendes)
ARBITRAGE_TYPES = {'achat', 'vente', 'versement', 'retrait'}

# Catégories considérées comme "réserves de liquidités" pour les portefeuilles
# de type AV/PER. Un versement/retrait asset-specific sur l'une de ces catégories
# est traité comme un flux externe réel (vrai apport ou retrait).
LIQUIDITY_CATEGORIES = {'Fonds €', 'Fonds Euro', 'Cash'}


def get_rendements_annuels(portefeuille_id: int, max_years: int = 10) -> list[dict]:
    """Calcule les rendements annuels avec la méthode Modified Dietz.

    Formule Modified Dietz :
        R = (V_fin - V_début - F_total) / (V_début + Σ(F_i × w_i))

    où :
        - V_fin     = valorisation totale en fin de période
        - V_début   = valorisation totale en début de période
        - F_total   = somme des flux externes nets (versements - retraits)
        - F_i       = flux externe i
        - w_i       = (nb_jours_restants_après_flux_i) / nb_jours_total_période

    Cette méthode pondère chaque flux par le temps qu'il a réellement été
    présent dans le portefeuille, ce qui donne un rendement représentatif
    de la performance du portefeuille, indépendamment du timing des apports.

    Gestion des flux externes :
        - PEA / CTO  : versements/retraits non asset-specific = flux externes
        - AV / PER   : versements/retraits asset-specific sur Fonds €/Cash
                       = flux externes (apports/retraits réels)
        - Arbitrages internes (enfants liés via parent_transaction_id sur
          des types achat/vente/versement/retrait) : exclus du calcul
    """
    today = date.today()

    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf or not ptf.transactions:
            return []

        first_year = min(t.date_operation.year for t in ptf.transactions)
        current_year = today.year

        years_to_analyze = list(range(first_year, current_year + 1))
        if not years_to_analyze:
            return []
        years_to_analyze = years_to_analyze[-max_years:]

        # 🆕 Identifier les parents d'arbitrage (achats/ventes ayant un enfant
        # arbitrage). Ces parents représentent la moitié visible d'un mouvement
        # interne et ne doivent pas être comptés comme flux externe.
        parent_ids_with_child = {
            t.parent_transaction_id for t in ptf.transactions
            if t.parent_transaction_id is not None
            and t.type_operation in ARBITRAGE_TYPES
        }

        # Collecter les flux externes (avec leur date exacte)
        flux_par_date = {}  # {date: montant_net}

        for t in ptf.transactions:
            # Exclure les enfants d'arbitrage (vrais arbitrages, pas les frais)
            if (t.parent_transaction_id is not None
                    and t.type_operation in ARBITRAGE_TYPES):
                continue

            # Exclure les parents d'arbitrage de type achat/vente
            # (le mouvement complet est interne au portefeuille)
            if t.id in parent_ids_with_child and t.type_operation in ('achat', 'vente'):
                continue

            is_asset_specific = bool(
                (t.ticker or t.code or t.nom_titre) and t.quantite is not None
            )

            # 🆕 Gestion AV-aware des versements/retraits :
            # - asset-specific sur Fonds €/Cash = flux externe réel (cas AV/PER)
            # - non asset-specific = flux externe classique (cas PEA/CTO)
            # - asset-specific sur autre catégorie = mouvement interne, à exclure
            if t.type_operation == 'versement':
                if is_asset_specific:
                    if t.categorie in LIQUIDITY_CATEGORIES:
                        flux_par_date.setdefault(t.date_operation, 0.0)
                        flux_par_date[t.date_operation] += t.montant
                    # sinon : mouvement interne sur titre → ignoré
                else:
                    flux_par_date.setdefault(t.date_operation, 0.0)
                    flux_par_date[t.date_operation] += t.montant

            elif t.type_operation == 'retrait':
                if is_asset_specific:
                    if t.categorie in LIQUIDITY_CATEGORIES:
                        flux_par_date.setdefault(t.date_operation, 0.0)
                        flux_par_date[t.date_operation] -= t.montant
                    # sinon : mouvement interne sur titre → ignoré
                else:
                    flux_par_date.setdefault(t.date_operation, 0.0)
                    flux_par_date[t.date_operation] -= t.montant

    rendements = []
    valo_precedente = None

    for year in years_to_analyze:
        debut = date(year, 1, 1)
        fin = date(year, 12, 31) if year < today.year else today
        nb_jours_periode = (fin - debut).days + 1

        # Valorisation fin de période
        situation_fin = get_situation_at_date(portefeuille_id, fin)
        if situation_fin is None:
            continue
        valo_fin = situation_fin['valo_totale']

        # Valorisation début de période = valo au 31/12 de l'année précédente
        valo_debut = valo_precedente if valo_precedente is not None else 0.0

        # Flux pendant l'année
        flux_annee = {d: m for d, m in flux_par_date.items() if debut <= d <= fin}
        flux_total = sum(flux_annee.values())

        # 🆕 Cas spécial : 1ère année (V_début = 0)
        # On utilise un rendement simple pondéré, sans effet d'annualisation
        # trompeur si la période d'exposition est courte
        is_first_year = (valo_debut == 0 and flux_total > 0)

        if is_first_year:
            # Rendement simple : gain / capital investi
            gain_net = valo_fin - flux_total
            if flux_total > 1.0:
                rendement_pct = (gain_net / flux_total) * 100
            else:
                rendement_pct = 0.0
        else:
            # Modified Dietz standard
            flux_pondere = 0.0
            for d, m in flux_annee.items():
                jours_restants = (fin - d).days + 1
                poids = jours_restants / nb_jours_periode
                flux_pondere += m * poids

            denominateur = valo_debut + flux_pondere

            if denominateur > 1.0:
                gain_net = valo_fin - valo_debut - flux_total
                rendement_pct = (gain_net / denominateur) * 100
            else:
                rendement_pct = 0.0

        rendements.append({
            'annee': year,
            'rendement_pct': rendement_pct,
            'valo_debut': valo_debut,
            'valo_fin': valo_fin,
            'flux_nets': flux_total,
            'is_first_year': is_first_year,  # 🆕 pour l'UI
        })

        valo_precedente = valo_fin

    rendements.sort(key=lambda r: r['annee'], reverse=True)
    return rendements