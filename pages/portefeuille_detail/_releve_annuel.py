"""Popup affichant la situation du portefeuille au 31/12 d'une année donnée.

Reconstruit l'état historique en rejouant toutes les transactions jusqu'au 31/12.
"""
from datetime import date
from collections import defaultdict
from nicegui import ui
from sqlalchemy import select

from database.db import get_session
from database.models import Portefeuille, Transaction, CoursHistorique
from utils.formatters import format_money, format_percent, get_perf_color
from services.labels import get_display_name  # ✅ Import ajouté


def get_situation_at_date(portefeuille_id: int, target_date: date) -> dict:
    """Reconstruit la situation du portefeuille à une date donnée.

    Rejoue toutes les transactions jusqu'à `target_date` pour calculer :
    - les positions détenues (quantité, PRU, cours, valorisation, +/- value)
    - le cash résiduel
    - le total versé (flux externes uniquement)
    - les valorisations totales
    """
    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf:
            return None

        transactions = sorted(
            [t for t in ptf.transactions if t.date_operation <= target_date],
            key=lambda t: t.date_operation
        )

        if not transactions:
            return {
                'portefeuille_nom': ptf.nom_affiche,
                'portefeuille_type': ptf.type,
                'date_situation': target_date,
                'positions': [],
                'cash': 0.0,
                'total_verse': 0.0,
                'valo_titres': 0.0,
                'valo_totale': 0.0,
                'plus_value': 0.0,
                'plus_value_pct': 0.0,
            }

        # 🆕 On ne considère comme "arbitrage" QUE les liens entre transactions
        # de type achat/vente/versement/retrait. Les frais liés à un achat
        # ne sont PAS un arbitrage.
        ARBITRAGE_TYPES = {'achat', 'vente', 'versement', 'retrait'}

        parent_ids_with_child = {
            t.parent_transaction_id for t in transactions
            if t.parent_transaction_id is not None
               and t.type_operation in ARBITRAGE_TYPES
        }

        tickers = set()
        for t in transactions:
            if t.type_operation in ('achat', 'vente') and t.ticker:
                tickers.add(t.ticker)

        cours_par_ticker = defaultdict(list)
        if tickers:
            cours_rows = session.execute(
                select(CoursHistorique.ticker,
                       CoursHistorique.date_cours,
                       CoursHistorique.cours)
                .where(CoursHistorique.ticker.in_(tickers))
                .order_by(CoursHistorique.ticker, CoursHistorique.date_cours)
            ).all()
            for ticker, d, cours in cours_rows:
                cours_par_ticker[ticker].append((d, cours))

        def get_cours_a_date(ticker: str, target: date):
            cours_list = cours_par_ticker.get(ticker, [])
            last = None
            for d, c in cours_list:
                if d <= target:
                    last = c
                else:
                    break
            return last

        cash = 0.0
        total_verse = 0.0
        positions_held = {}

        for t in transactions:
            key = t.ticker or t.code or t.nom_titre
            is_asset_specific_tx = bool(key and t.quantite is not None)
            # 🆕 Un enfant n'est un arbitrage que s'il est de type achat/vente/versement/retrait
            is_arbitrage_child = (
                    t.parent_transaction_id is not None
                    and t.type_operation in ARBITRAGE_TYPES
            )
            is_arbitrage_parent = t.id in parent_ids_with_child
            is_internal = is_arbitrage_child or is_arbitrage_parent

            if t.type_operation == 'versement':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] += t.quantite
                    else:
                        positions_held[key] = {
                            'ticker': t.ticker, 'code': t.code,
                            'nom': t.nom_titre, 'categorie': t.categorie,
                            'quantite': t.quantite,
                            'pru': t.prix_unitaire if t.prix_unitaire is not None else 1.0,
                        }
                    # 🆕 Versement asset-specific sur Fonds €/Cash = vrai apport externe
                    # (sauf si c'est un enfant d'arbitrage)
                    if (not is_internal
                            and t.categorie in ('Fonds €', 'Fonds Euro', 'Cash')):
                        total_verse += t.montant
                else:
                    cash += t.montant
                    if not is_internal:
                        total_verse += t.montant


            elif t.type_operation == 'retrait':

                if is_asset_specific_tx:

                    if key in positions_held:
                        positions_held[key]['quantite'] -= t.quantite

                    # 🆕 Retrait asset-specific depuis Fonds €/Cash = vrai retrait externe

                    if (not is_internal

                            and t.categorie in ('Fonds €', 'Fonds Euro', 'Cash')):
                        total_verse -= t.montant

                else:

                    cash -= t.montant

                    if not is_internal:
                        total_verse -= t.montant

            elif t.type_operation == 'interets':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] += t.quantite
                    else:
                        positions_held[key] = {
                            'ticker': t.ticker, 'code': t.code,
                            'nom': t.nom_titre, 'categorie': t.categorie,
                            'quantite': t.quantite,
                            'pru': t.prix_unitaire if t.prix_unitaire is not None else 1.0,
                        }
                else:
                    cash += t.montant

            elif t.type_operation == 'dividende':
                if is_asset_specific_tx:
                    if key in positions_held:
                        old = positions_held[key]
                        new_qte = old['quantite'] + t.quantite
                        new_pru = (
                            (old['quantite'] * old['pru']) +
                            (t.quantite * (t.prix_unitaire or 0))
                        ) / new_qte if new_qte > 0 else (t.prix_unitaire or 0)
                        old['quantite'] = new_qte
                        old['pru'] = new_pru
                    else:
                        positions_held[key] = {
                            'ticker': t.ticker, 'code': t.code,
                            'nom': t.nom_titre, 'categorie': t.categorie,
                            'quantite': t.quantite,
                            'pru': t.prix_unitaire,
                        }
                else:
                    cash += t.montant

            elif t.type_operation == 'frais':
                if is_asset_specific_tx:
                    if key in positions_held:
                        positions_held[key]['quantite'] -= t.quantite
                else:
                    cash -= t.montant

            elif t.type_operation == 'achat':
                if not is_internal:
                    cash -= t.montant
                if t.quantite is not None and t.prix_unitaire is not None:
                    if key in positions_held:
                        old = positions_held[key]
                        new_qte = old['quantite'] + t.quantite
                        new_pru = (
                            (old['quantite'] * old['pru']) +
                            (t.quantite * t.prix_unitaire)
                        ) / new_qte if new_qte > 0 else t.prix_unitaire
                        old['quantite'] = new_qte
                        old['pru'] = new_pru
                    else:
                        positions_held[key] = {
                            'ticker': t.ticker, 'code': t.code,
                            'nom': t.nom_titre, 'categorie': t.categorie,
                            'quantite': t.quantite,
                            'pru': t.prix_unitaire,
                        }

            elif t.type_operation == 'vente':
                if not is_internal:
                    cash += t.montant
                if t.quantite is not None and key in positions_held:
                    positions_held[key]['quantite'] -= t.quantite

        positions_list = []
        valo_titres = 0.0

        def is_reserve(p):
            return p.get('categorie') in ('Cash', 'Fonds €', 'Fonds Euro')

        for key, pos in positions_held.items():
            qte = pos['quantite']
            if qte <= 0.0001:
                continue

            ticker = pos['ticker']
            cours = None
            if ticker:
                cours = get_cours_a_date(ticker, target_date)
            if cours is None:
                cours = pos['pru']

            valo = qte * cours
            cout_revient = qte * pos['pru']
            pv = valo - cout_revient
            pv_pct = (pv / cout_revient * 100) if cout_revient > 0 else 0

            positions_list.append({
                'nom': pos['nom'],
                'categorie': pos['categorie'],
                'ticker': pos['ticker'],
                'code': pos['code'],
                'quantite': qte,
                'pru': pos['pru'],
                'cours': cours,
                'valorisation': valo,
                'plus_value': pv,
                'plus_value_pct': pv_pct,
                'is_reserve': is_reserve(pos),
            })
            valo_titres += valo

        positions_list.sort(key=lambda p: (p['is_reserve'], -p['valorisation']))

        valo_totale = cash + valo_titres
        plus_value_globale = valo_totale - total_verse
        pv_pct_globale = (
            plus_value_globale / total_verse * 100
        ) if total_verse > 0 else 0

        return {
            'portefeuille_nom': ptf.nom_affiche,
            'portefeuille_type': ptf.type,
            'date_situation': target_date,
            'positions': positions_list,
            'cash': cash,
            'total_verse': total_verse,
            'valo_titres': valo_titres,
            'valo_totale': valo_totale,
            'plus_value': plus_value_globale,
            'plus_value_pct': pv_pct_globale,
        }


def get_available_years(portefeuille_id: int) -> list[int]:
    """Retourne la liste des années pour lesquelles un relevé peut être généré."""
    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        if not ptf or not ptf.transactions:
            return []

        first_year = min(t.date_operation.year for t in ptf.transactions)
        current_year = date.today().year

        years = list(range(first_year, current_year))
        return sorted(years, reverse=True)


def show_releve_annuel(portefeuille_id: int, annee: int, c, is_dark):
    """Affiche le popup avec la situation du portefeuille au 31/12 de l'année."""
    target_date = date(annee, 12, 31)
    situation = get_situation_at_date(portefeuille_id, target_date)

    if situation is None:
        ui.notify('Portefeuille introuvable', type='negative')
        return

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-3').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]}; '
            f'min-width: 800px; max-width: 1000px;'
    ):
        # Header
        with ui.row().classes('w-full items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label(f'📋 Relevé annuel {annee}').classes(
                    'text-xl font-bold'
                ).style(f'color: {c["text_primary"]}')
                ui.label(
                    f"Situation du {situation['portefeuille_nom']} "
                    f"au 31/12/{annee}"
                ).classes('text-sm').style(f'color: {c["text_secondary"]}')

            ui.button(icon='close', on_click=dialog.close).props('flat round dense')

        ui.separator()

        # KPIs globaux
        with ui.row().classes('w-full gap-4'):
            _render_kpi('💰 Total versé',
                        format_money(situation['total_verse'], decimals=2),
                        c, color=c['text_primary'])
            _render_kpi('📦 Valorisation',
                        format_money(situation['valo_totale'], decimals=2),
                        c, color=c['text_primary'])

            pv = situation['plus_value']
            pv_pct = situation['plus_value_pct']
            pv_color = get_perf_color(pv)
            _render_kpi(
                '📈 +/- value',
                f"{format_money(pv, decimals=2)} ({format_percent(pv_pct)})",
                c, color=pv_color
            )

        with ui.row().classes('w-full gap-4 mt-2'):
            _render_kpi('💵 Cash / Liquidités',
                        format_money(situation['cash'], decimals=2),
                        c, color=c['text_secondary'], small=True)
            _render_kpi('📊 Valorisation des titres',
                        format_money(situation['valo_titres'], decimals=2),
                        c, color=c['text_secondary'], small=True)

        ui.separator()

        # Tableau des positions
        if not situation['positions']:
            with ui.column().classes('w-full items-center py-6 gap-1'):
                ui.icon('inventory_2').classes('text-4xl').style(
                    f'color: {c["text_secondary"]}'
                )
                ui.label('Aucune position détenue à cette date').classes('text-sm') \
                    .style(f'color: {c["text_secondary"]}')
        else:
            ui.label(
                f"📦 Détail des positions ({len(situation['positions'])} ligne(s))"
            ).classes('text-sm font-bold').style(f'color: {c["text_primary"]}')

            with ui.column().classes('w-full gap-1').style(
                    'max-height: 400px; overflow-y: auto;'
            ):
                # Header tableau
                with ui.row().classes(
                        'w-full items-center px-3 py-2 rounded-lg'
                ).style(
                    f'background-color: {c["card_border"]}40; '
                    f'font-size: 0.7rem; font-weight: 600; '
                    f'letter-spacing: 0.05em; '
                    f'color: {c["text_secondary"]};'
                ):
                    ui.label('TITRE').style('flex: 2;')
                    ui.label('CATÉGORIE').style('flex: 1;')
                    ui.label('QUANTITÉ').style('flex: 1; text-align: right;')
                    ui.label('PRU').style('flex: 1; text-align: right;')
                    ui.label('COURS').style('flex: 1; text-align: right;')
                    ui.label('VALORISATION').style('flex: 1.2; text-align: right;')
                    ui.label('+/-').style('flex: 1.2; text-align: right;')

                # Lignes
                reserves_separator_added = False
                for pos in situation['positions']:
                    # Séparateur visuel avant les réserves
                    if pos['is_reserve'] and not reserves_separator_added:
                        with ui.row().classes(
                                'w-full items-center px-3 py-1 mt-2'
                        ).style(
                            f'border-top: 1px dashed {c["card_border"]};'
                        ):
                            ui.icon('savings').classes('text-xs').style(
                                f'color: {c["text_secondary"]}'
                            )
                            ui.label('RÉSERVES DE LIQUIDITÉS').classes(
                                'text-xs font-bold tracking-wider'
                            ).style(f'color: {c["text_secondary"]}')
                        reserves_separator_added = True

                    # ✅ Résolution du nom d'affichage (custom > original)
                    display_name = get_display_name(
                        ticker=pos.get('ticker'),
                        code=pos.get('code'),
                        fallback=pos['nom']
                    )

                    pv_color = get_perf_color(pos['plus_value'])
                    with ui.row().classes(
                            'w-full items-center px-3 py-2 rounded-lg'
                    ).style(f'background-color: {c["card_border"]}15;'):
                        # ✅ Utilisation de display_name au lieu de pos['nom']
                        ui.label(display_name).style(
                            f'flex: 2; font-weight: 500; '
                            f'color: {c["text_primary"]}; '
                            f'overflow: hidden; text-overflow: ellipsis; '
                            f'white-space: nowrap;'
                        )
                        ui.label(pos['categorie'] or '-').style(
                            f'flex: 1; color: {c["text_secondary"]}; '
                            f'font-size: 0.85rem;'
                        )
                        ui.label(f"{pos['quantite']:g}").style(
                            f'flex: 1; text-align: right; '
                            f'color: {c["text_primary"]};'
                        )
                        ui.label(format_money(pos['pru'], decimals=2)).style(
                            f'flex: 1; text-align: right; '
                            f'color: {c["text_secondary"]};'
                        )
                        ui.label(format_money(pos['cours'], decimals=2)).style(
                            f'flex: 1; text-align: right; '
                            f'color: {c["text_primary"]};'
                        )
                        ui.label(
                            format_money(pos['valorisation'], decimals=2)
                        ).style(
                            f'flex: 1.2; text-align: right; '
                            f'font-weight: 600; color: {c["text_primary"]};'
                        )

                        if pos['is_reserve']:
                            ui.label('-').style(
                                f'flex: 1.2; text-align: right; '
                                f'color: {c["text_secondary"]};'
                            )
                        else:
                            ui.label(
                                f"{format_money(pos['plus_value'], decimals=2)} "
                                f"({format_percent(pos['plus_value_pct'])})"
                            ).style(
                                f'flex: 1.2; text-align: right; '
                                f'font-weight: 600; color: {pv_color};'
                            )

        with ui.row().classes('w-full justify-end mt-3'):
            ui.button('Fermer', on_click=dialog.close).props('unelevated') \
                .classes('bg-blue-600 text-white')

    dialog.open()


def _render_kpi(label, value, c, color=None, small=False):
    """Petite carte KPI réutilisable."""
    color = color or c['text_primary']
    label_size = 'text-xs' if small else 'text-xs'
    value_size = 'text-sm' if small else 'text-lg'

    with ui.column().classes('gap-0 px-3 py-2 rounded-lg').style(
            f'background-color: {c["card_border"]}30; flex: 1;'
    ):
        ui.label(label).classes(
            f'{label_size} font-semibold tracking-wider'
        ).style(f'color: {c["text_secondary"]}')
        ui.label(value).classes(f'{value_size} font-bold').style(
            f'color: {color}'
        )