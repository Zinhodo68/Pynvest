"""Section positions + dialogue d'ajout/édition."""
from datetime import date, datetime
from nicegui import ui

from database.db import get_session
from database.models import Position
from utils.formatters import format_money, format_percent, get_perf_color
from pages.positions_data import CATEGORIES_POSITION, get_categorie_info
from pages.portefeuille_detail._releve_annuel import (
    get_available_years, show_releve_annuel
)
from services.labels import get_display_name, set_custom_name, delete_custom_name


def render_positions_section(positions, data, c, portefeuille_id, refresh, is_dark=False):
    with ui.card().classes('w-full p-0 rounded-xl overflow-hidden').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]};'
    ):
        # Header (réduit en hauteur)
        with ui.row().classes('w-full items-center justify-between px-5 py-3').style(
            f'border-bottom: 1px solid {c["card_border"]};'
        ):
            with ui.column().classes('gap-0'):
                ui.label('Positions').classes('text-lg font-bold').style(
                    f'color: {c["text_primary"]}'
                )
                ui.label(f'{len(positions)} ligne(s) dans le portefeuille').classes('text-xs') \
                    .style(f'color: {c["text_secondary"]}')

            # Menu déroulant "Relevé annuel" à droite du header
            available_years = get_available_years(portefeuille_id)
            if available_years:
                with ui.button(icon='description').props(
                        'flat dense'
                ).style(f'color: {c["text_secondary"]};') \
                        .tooltip("Relevé d'information annuel"):
                    with ui.menu():
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

        # En-tête tableau (réduit en hauteur, colonne Catégorie supprimée)
        with ui.row().classes('w-full px-5 py-1.5 text-xs font-semibold uppercase tracking-wider').style(
            f'color: {c["text_secondary"]}; '
            f'background-color: {c["card_border"]}30;'
        ):
            ui.label('Titre').style('flex: 2;')
            ui.label('Quantité').style('width: 90px; text-align: right;')
            ui.label('PRU').style('width: 100px; text-align: right;')
            ui.label('Cours').style('width: 100px; text-align: right;')
            ui.label('Valorisation').style('width: 130px; text-align: right;')
            ui.label('+/-').style('width: 130px; text-align: right;')
            ui.label('').style('width: 40px;')

        # Séparation titres / réserves de liquidités
        RESERVES_CATEGORIES = {'Cash', 'Fonds €', 'Fonds Euro'}

        def is_reserve(p):
            return p['nom'] == 'Cash' or (p.get('categorie') in RESERVES_CATEGORIES)

        titres = [p for p in positions if not is_reserve(p)]
        reserves = [p for p in positions if is_reserve(p)]

        # 3. Limitation de hauteur avec défilement interne pour les lignes de données
        with ui.column().classes('w-full max-h-[350px] overflow-y-auto gap-0'):
            for pos in titres:
                _render_position_row(pos, c, portefeuille_id, refresh)

            if titres and reserves:
                with ui.row().classes('w-full px-5 py-1 items-center').style(
                    f'border-top: 2px dashed {c["card_border"]}; '
                    f'background-color: {c["card_border"]}15;'
                ):
                    ui.label('💰 Réserves de liquidités').classes(
                        'text-xs font-semibold uppercase tracking-wider'
                    ).style(f'color: {c["text_secondary"]};')

            for pos in reserves:
                _render_position_row(pos, c, portefeuille_id, refresh)

        # Pied de page fixe
        _render_positions_footer(total_pru, total_valo, total_pv, c)


def _render_rename_dialog(pos, c, refresh):
    """
    Popup de renommage d'un support.
    Le nom personnalisé est prioritaire sur le nom Yahoo/Boursorama à l'affichage.
    Le ticker Yahoo reste inchangé pour la récupération des cours.
    """
    ticker = pos.get('ticker')
    code = pos.get('code')
    nom_original = pos.get('nom') or ticker or code or '—'

    # Nom actuellement affiché (custom ou fallback Yahoo)
    current_display = get_display_name(
        ticker=ticker,
        code=code,
        fallback=nom_original
    )

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-3').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'min-width: 420px;'
    ):
        ui.label('✏️ Renommer le support').classes('text-lg font-bold').style(
            f'color: {c["text_primary"]}'
        )

        # Infos du support (lecture seule)
        ticker_display = ticker or code or '—'
        ui.label(f'Ticker / Code : {ticker_display}').classes('text-sm').style(
            f'color: {c["text_secondary"]}'
        )
        ui.label(f'Nom original : {nom_original}').classes('text-sm').style(
            f'color: {c["text_secondary"]}'
        )

        ui.separator()

        name_input = ui.input(
            label='Nom personnalisé',
            value=current_display,
            placeholder='Ex: LVMH, World ETF Amundi...'
        ).classes('w-full')

        ui.label(
            '⚠️ Ce nom est uniquement cosmétique. '
            'Le ticker Yahoo reste inchangé pour la récupération des cours.'
        ).classes('text-xs px-3 py-2 rounded-lg').style(
            f'background-color: {c["card_border"]}30; '
            f'color: #f59e0b;'
        )

        with ui.row().classes('w-full justify-between items-center gap-2 mt-2'):

            # Bouton "Réinitialiser" à gauche
            async def handle_reset():
                deleted = delete_custom_name(ticker=ticker, code=code)
                if deleted:
                    ui.notify('Nom réinitialisé (retour au nom Yahoo/Boursorama)', color='info')
                else:
                    ui.notify('Aucun nom personnalisé à réinitialiser', color='warning')
                dialog.close()
                refresh()

            ui.button('Réinitialiser', on_click=handle_reset).props('flat color=warning')

            # Annuler + Enregistrer à droite
            with ui.row().classes('gap-2'):
                ui.button('Annuler', on_click=dialog.close).props('flat')

                async def handle_save():
                    new_name = name_input.value.strip()
                    if not new_name:
                        ui.notify('Le nom ne peut pas être vide', color='negative')
                        return
                    if new_name == nom_original:
                        # Pas de custom_name nécessaire si identique à l'original
                        delete_custom_name(ticker=ticker, code=code)
                        ui.notify('Nom inchangé — label supprimé si existant', color='info')
                    else:
                        set_custom_name(
                            ticker=ticker,
                            code=code,
                            custom_name=new_name,
                            original_name=nom_original
                        )
                        ui.notify(f'✅ Renommé en "{new_name}"', color='positive')
                    dialog.close()
                    refresh()

                ui.button('Enregistrer', on_click=handle_save).props(
                    'unelevated color=primary'
                )

    dialog.open()


def _render_position_row(pos, c, portefeuille_id, refresh):
    cat_info = get_categorie_info(pos['categorie'])
    pv_color = get_perf_color(pos['plus_value'])
    is_cash = pos['nom'] == 'Cash'
    is_reserve = pos.get('categorie') in {'Cash', 'Fonds €', 'Fonds Euro'} or is_cash

    # ✅ Résolution du nom à afficher (custom_name prioritaire)
    display_name = get_display_name(
        ticker=pos.get('ticker'),
        code=pos.get('code'),
        fallback=pos['nom']
    ) if not is_cash else 'Cash'

    # Hauteur de ligne réduite à py-1.5 au lieu de py-3
    with ui.row().classes('w-full px-5 py-1.5 items-center').style(
        f'border-top: 1px solid {c["card_border"]};'
        + (f' background-color: {cat_info["couleur"]}10;' if is_cash else '')
    ):
        # Colonne Titre
        with ui.column().classes('gap-0').style('flex: 2;'):
            with ui.row().classes('items-center gap-1'):
                if is_cash:
                    ui.icon('savings').classes('text-base').style(
                        f'color: {cat_info["couleur"]}'
                    )
                ui.label(display_name).classes('text-sm font-semibold').style(
                    f'color: {c["text_primary"]}'
                )
                # ✏️ Bouton renommage (uniquement sur les titres, pas les réserves)
                if not is_reserve:
                    ui.button(
                        icon='edit',
                        on_click=lambda p=pos: _render_rename_dialog(p, c, refresh)
                    ).props('flat round dense size=xs').style(
                        f'color: {c["text_secondary"]};'
                    ).tooltip('Renommer ce support')

            if pos['code'] and not is_cash:
                ui.label(pos['code']).classes('text-xs').style(
                    f'color: {c["text_secondary"]}'
                )

        # La colonne "Catégorie" a été complètement retirée ici pour libérer de la place

        # Quantité
        ui.label(f'{pos["quantite"]:g}'.replace('.', ',') if not is_cash else '—') \
            .classes('text-sm').style(
                f'color: {c["text_primary"]}; width: 90px; text-align: right;'
            )

        # PRU
        ui.label(format_money(pos['prix_moyen'], decimals=2) if not is_cash else '—') \
            .classes('text-sm').style(
                f'color: {c["text_secondary"]}; width: 100px; text-align: right;'
            )

        # Cours actuel
        if pos['cours_actuel'] is not None and not is_cash:
            ui.label(format_money(pos['cours_actuel'], decimals=2)).classes(
                'text-sm'
            ).style(f'color: {c["text_primary"]}; width: 100px; text-align: right;')
        else:
            ui.label('—').classes('text-sm').style(
                f'color: {c["text_secondary"]}; width: 100px; text-align: right;'
            )

        # Valorisation
        ui.label(format_money(pos['valorisation'], decimals=2)).classes(
            'text-sm font-semibold'
        ).style(f'color: {c["text_primary"]}; width: 130px; text-align: right;')

        # +/- value
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

        # Menu actions
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
    # Hauteur de ligne réduite à py-1.5 au lieu de py-3
    with ui.row().classes('w-full px-5 py-1.5 items-center').style(
        f'border-top: 2px solid {c["card_border"]}; '
        f'background-color: {c["card_border"]}20;'
    ):
        ui.label('TOTAL POSITIONS').classes('text-xs font-bold tracking-wider').style(
            f'color: {c["text_secondary"]}; flex: 2;'
        )
        # La colonne Catégorie vide (width: 110px) a été retirée pour préserver l'alignement
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