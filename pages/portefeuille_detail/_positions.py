"""Section positions + dialogue d'ajout/édition."""
from datetime import date, datetime
from nicegui import ui

from database.db import get_session
from database.models import Position
from utils.formatters import format_money, format_percent, get_perf_color
from pages.positions_data import CATEGORIES_POSITION, get_categorie_info
# 🆕 Import du module relevé annuel
from pages.portefeuille_detail._releve_annuel import (
    get_available_years, show_releve_annuel
)


def render_positions_section(positions, data, c, portefeuille_id, refresh, is_dark=False):
    with ui.card().classes('w-full p-0 rounded-xl overflow-hidden').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]};'
    ):
        # Header
        with ui.row().classes('w-full items-center justify-between p-5').style(
            f'border-bottom: 1px solid {c["card_border"]};'
        ):
            with ui.column().classes('gap-0'):
                ui.label('Positions').classes('text-lg font-bold').style(
                    f'color: {c["text_primary"]}'
                )
                ui.label(f'{len(positions)} ligne(s) dans le portefeuille').classes('text-xs') \
                    .style(f'color: {c["text_secondary"]}')

            # 🆕 Menu déroulant "Relevé annuel" à droite du header
            available_years = get_available_years(portefeuille_id)
            if available_years:
                with ui.button(icon='description').props(
                        'flat dense'
                ).style(f'color: {c["text_secondary"]};') \
                        .tooltip("Relevé d'information annuel"):
                    with ui.menu():
                        # En-tête du menu (non-cliquable)
                        with ui.row().classes('items-center gap-2 px-3 py-2').style(
                                'pointer-events: none;'
                        ):
                            ui.icon('event_note').classes('text-sm').style(
                                f'color: {c["text_secondary"]}'
                            )
                            ui.label("Relevé d'information annuel").classes(
                                'text-xs font-bold tracking-wider'
                            ).style(f'color: {c["text_secondary"]};')
                        ui.separator()
                        # Liste des années
                        for year in available_years:
                            ui.menu_item(
                                f'📋 Année {year}',
                                on_click=lambda y=year: show_releve_annuel(
                                    portefeuille_id, y, c, is_dark
                                )
                            )

        if not positions:
            with ui.column().classes('w-full items-center py-10 gap-2'):
                ui.icon('inventory_2').classes('text-5xl').style(
                    f'color: {c["text_secondary"]}'
                )
                ui.label('Aucune position').classes('text-sm').style(
                    f'color: {c["text_primary"]}'
                )
                ui.label('Ajoutez vos actions, ETF, SCPI...').classes('text-xs') \
                    .style(f'color: {c["text_secondary"]}')
            return

        total_valo = sum(p['valorisation'] for p in positions)
        total_pru = sum(p['prix_revient'] for p in positions)
        total_pv = total_valo - total_pru

        # En-tête tableau
        with ui.row().classes('w-full px-5 py-3 text-xs font-semibold uppercase tracking-wider').style(
            f'color: {c["text_secondary"]}; '
            f'background-color: {c["card_border"]}30;'
        ):
            ui.label('Titre').style('flex: 2;')
            ui.label('Catégorie').style('width: 110px;')
            ui.label('Quantité').style('width: 90px; text-align: right;')
            ui.label('PRU').style('width: 100px; text-align: right;')
            ui.label('Cours').style('width: 100px; text-align: right;')
            ui.label('Valorisation').style('width: 130px; text-align: right;')
            ui.label('+/-').style('width: 130px; text-align: right;')
            ui.label('').style('width: 40px;')

        # 🆕 Séparation titres / réserves de liquidités
        RESERVES_CATEGORIES = {'Cash', 'Fonds €', 'Fonds Euro'}

        def is_reserve(p):
            return p['nom'] == 'Cash' or (p.get('categorie') in RESERVES_CATEGORIES)

        titres = [p for p in positions if not is_reserve(p)]
        reserves = [p for p in positions if is_reserve(p)]

        # Affichage des titres
        for pos in titres:
            _render_position_row(pos, c, portefeuille_id, refresh)

        # 🆕 Séparateur visuel si présence des deux groupes
        if titres and reserves:
            with ui.row().classes('w-full px-5 py-2 items-center').style(
                f'border-top: 2px dashed {c["card_border"]}; '
                f'background-color: {c["card_border"]}15;'
            ):
                ui.label('💰 Réserves de liquidités').classes(
                    'text-xs font-semibold uppercase tracking-wider'
                ).style(f'color: {c["text_secondary"]};')

        # Affichage des réserves
        for pos in reserves:
            _render_position_row(pos, c, portefeuille_id, refresh)

        # Footer total
        _render_positions_footer(total_pru, total_valo, total_pv, c)


def _render_position_row(pos, c, portefeuille_id, refresh):
    cat_info = get_categorie_info(pos['categorie'])
    pv_color = get_perf_color(pos['plus_value'])
    is_cash = pos['nom'] == 'Cash'

    with ui.row().classes('w-full px-5 py-3 items-center').style(
        f'border-top: 1px solid {c["card_border"]};'
        + (f' background-color: {cat_info["couleur"]}10;' if is_cash else '')
    ):
        with ui.column().classes('gap-0').style('flex: 2;'):
            with ui.row().classes('items-center gap-2'):
                if is_cash:
                    ui.icon('savings').classes('text-base').style(
                        f'color: {cat_info["couleur"]}'
                    )
                ui.label(pos['nom']).classes('text-sm font-semibold').style(
                    f'color: {c["text_primary"]}'
                )
            if pos['code'] and not is_cash:
                ui.label(pos['code']).classes('text-xs').style(
                    f'color: {c["text_secondary"]}'
                )

        with ui.row().classes('items-center gap-1').style('width: 110px;'):
            if not is_cash:
                ui.icon(cat_info['icon']).classes('text-sm').style(
                    f'color: {cat_info["couleur"]}'
                )
            ui.label(pos['categorie'] or '—').classes('text-xs').style(
                f'color: {cat_info["couleur"]}; font-weight: 500;'
            )

        ui.label(f'{pos["quantite"]:g}'.replace('.', ',') if not is_cash else '—') \
            .classes('text-sm').style(
                f'color: {c["text_primary"]}; width: 90px; text-align: right;'
            )

        ui.label(format_money(pos['prix_moyen'], decimals=2) if not is_cash else '—') \
            .classes('text-sm').style(
                f'color: {c["text_secondary"]}; width: 100px; text-align: right;'
            )

        if pos['cours_actuel'] is not None and not is_cash:
            ui.label(format_money(pos['cours_actuel'], decimals=2)).classes(
                'text-sm'
            ).style(f'color: {c["text_primary"]}; width: 100px; text-align: right;')
        else:
            ui.label('—').classes('text-sm').style(
                f'color: {c["text_secondary"]}; width: 100px; text-align: right;'
            )

        ui.label(format_money(pos['valorisation'], decimals=2)).classes(
            'text-sm font-semibold'
        ).style(f'color: {c["text_primary"]}; width: 130px; text-align: right;')

        with ui.column().classes('gap-0').style(
                'width: 130px; align-items: flex-end;'
        ):
            if is_cash:
                ui.label('—').classes('text-sm').style(
                    f'color: {c["text_secondary"]};'
                )
            else:
                ui.label(format_money(pos['plus_value'], decimals=2)).classes(
                    'text-sm font-semibold'
                ).style(f'color: {pv_color};')
                ui.label(format_percent(pos['plus_value_pct'])).classes(
                    'text-xs'
                ).style(f'color: {pv_color};')

        if is_cash:
            ui.label('').style('width: 40px;')
        else:
            with ui.button(icon='more_vert').props(
                    'flat round dense size=sm'
            ).style(f'color: {c["text_secondary"]}; width: 40px;'):
                with ui.menu():
                    ui.menu_item('Modifier', on_click=lambda pid=pos['id']:
                    open_position_edit_dialog(portefeuille_id, c, refresh, pid))
                    ui.menu_item('Supprimer', on_click=lambda pid=pos['id'], n=pos['nom']:
                    confirm_delete_position(pid, n, refresh))


def _render_positions_footer(total_pru, total_valo, total_pv, c):
    total_color = get_perf_color(total_pv)
    with ui.row().classes('w-full px-5 py-3 items-center').style(
        f'border-top: 2px solid {c["card_border"]}; '
        f'background-color: {c["card_border"]}20;'
    ):
        ui.label('TOTAL POSITIONS').classes('text-xs font-bold tracking-wider').style(
            f'color: {c["text_secondary"]}; flex: 2;'
        )
        ui.label('').style('width: 110px;')
        ui.label('').style('width: 90px;')
        ui.label('').style('width: 100px;')
        ui.label(format_money(total_pru, decimals=2)).classes('text-sm').style(
            f'color: {c["text_secondary"]}; width: 100px; text-align: right;'
        )
        ui.label(format_money(total_valo, decimals=2)).classes('text-sm font-bold').style(
            f'color: {c["text_primary"]}; width: 130px; text-align: right;'
        )
        with ui.column().classes('gap-0').style('width: 130px; align-items: flex-end;'):
            ui.label(format_money(total_pv, decimals=2)).classes('text-sm font-bold').style(
                f'color: {total_color};'
            )
            pv_pct = (total_pv / total_pru * 100) if total_pru > 0 else 0
            ui.label(format_percent(pv_pct)).classes('text-xs').style(
                f'color: {total_color};'
            )
        ui.label('').style('width: 40px;')


def open_position_edit_dialog(portefeuille_id, c, refresh, position_id: int):
    """Édition rapide d'une position existante (PRU, quantité, cours).
    Pour modifications structurelles : supprimer/recréer."""

    with get_session() as session:
        pos = session.get(Position, position_id)
        if not pos:
            return
        if pos.nom == 'Cash':
            ui.notify('La position Cash est gérée automatiquement', type='warning')
            return
        data = pos.to_dict()

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-3').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]}; '
            f'min-width: 400px;'
    ):
        ui.label('Modifier la position').classes('text-xl font-bold').style(
            f'color: {c["text_primary"]}'
        )
        ui.label(data['nom']).classes('text-sm').style(f'color: {c["text_secondary"]}')

        ui.label('💡 Pour ajouter des parts, utilisez "+ Transaction → Achat"') \
            .classes('text-xs italic px-3 py-2 rounded-lg').style(
            f'background-color: {c["card_border"]}; color: {c["text_secondary"]};'
        )

        with ui.row().classes('w-full gap-3'):
            quantite_input = ui.number(
                'Quantité', value=data['quantite'], format='%.4f', min=0
            ).classes('flex-1')
            pru_input = ui.number(
                'PRU (€)', value=data['prix_moyen'], format='%.4f', min=0
            ).classes('flex-1')

        cours_input = ui.number(
            'Cours actuel (€)', value=data['cours_actuel'] or 0,
            format='%.4f', min=0
        ).classes('w-full')

        notes_input = ui.textarea('Notes', value=data['notes'] or '') \
            .classes('w-full').props('rows=2')

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat')

            def save():
                with get_session() as session:
                    pos = session.get(Position, position_id)
                    pos.quantite = float(quantite_input.value or 0)
                    pos.prix_moyen = float(pru_input.value or 0)
                    pos.cours_actuel = float(cours_input.value) if cours_input.value else None
                    pos.notes = notes_input.value or None
                    session.commit()
                ui.notify('Position modifiée', type='positive')
                dialog.close()
                refresh()

            ui.button('Enregistrer', on_click=save).props('unelevated') \
                .classes('bg-blue-600 text-white')

    dialog.open()


def confirm_delete_position(position_id, name, refresh):
    """Confirmation de suppression d'une position."""
    if name == 'Cash':
        ui.notify('La position Cash ne peut pas être supprimée', type='warning')
        return

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4'):
        ui.label('Confirmer la suppression').classes('text-xl font-bold')
        ui.label(f'Supprimer la position "{name}" ?')
        ui.label('Les transactions associées (achats, ventes) ne seront pas supprimées.') \
            .classes('text-xs italic').style('color: #f59e0b')

        def do_delete():
            with get_session() as session:
                pos = session.get(Position, position_id)
                if pos:
                    session.delete(pos)
                    session.commit()
            ui.notify(f'"{name}" supprimée', type='warning')
            dialog.close()
            refresh()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Annuler', on_click=dialog.close).props('flat')
            ui.button('Supprimer', on_click=do_delete).props('unelevated') \
                .classes('bg-red-600 text-white')

    dialog.open()