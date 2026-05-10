"""Section positions + dialogue d'ajout/édition."""
from datetime import date, datetime
from nicegui import ui

from database.db import get_session
from database.models import Position
from utils.formatters import format_money, format_percent, get_perf_color
from pages.positions_data import CATEGORIES_POSITION, get_categorie_info


def render_positions_section(positions, data, c, portefeuille_id, refresh):
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

            ui.button('+ Position', on_click=lambda: open_position_dialog(
                portefeuille_id, c, refresh)) \
                .props('unelevated').classes('bg-blue-600 text-white')

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

        for pos in positions:
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
                ui.label(format_money(pos['plus_value'], decimals=2)).classes(  # ← decimals=2
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
                        open_position_dialog(portefeuille_id, c, refresh, position_id=pid))
                    ui.menu_item('Supprimer', on_click=lambda pid=pos['id'], n=pos['nom']:
                        _confirm_delete_position(pid, n, refresh))


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
        # Footer total
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


def open_position_dialog(portefeuille_id, c, refresh, position_id: int = None):
    is_edit = position_id is not None

    if is_edit:
        with get_session() as session:
            pos = session.get(Position, position_id)
            if pos and pos.nom == 'Cash':
                ui.notify(
                    'La position Cash est gérée automatiquement par les transactions.',
                    type='warning', timeout=4000
                )
                return

    data = {
        'nom': '', 'code': '', 'categorie': 'Action',
        'quantite': 0, 'prix_moyen': 0, 'cours_actuel': None,
        'devise': 'EUR', 'notes': '', 'date_ouverture': None,
    }

    if is_edit:
        with get_session() as session:
            pos = session.get(Position, position_id)
            if pos:
                data = pos.to_dict()

    cat_options = {cat['value']: cat['label'] for cat in CATEGORIES_POSITION
                   if cat['value'] != 'Cash'}  # On exclut Cash

    date_initiale_fr = ''
    if data['date_ouverture']:
        date_initiale_fr = date.fromisoformat(data['date_ouverture']).strftime('%d/%m/%Y')

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'min-width: 500px;'
    ):
        ui.label('Modifier la position' if is_edit else 'Nouvelle position') \
            .classes('text-xl font-bold').style(f'color: {c["text_primary"]}')

        nom_input = ui.input('Nom du titre *', value=data['nom']).classes('w-full') \
            .props('placeholder="ex: Apple, iShares Core MSCI World, SCPI Primovie"')

        with ui.row().classes('w-full gap-3'):
            code_input = ui.input('Code / ISIN / Ticker', value=data['code'] or '') \
                .classes('flex-1').props('placeholder="ex: AAPL, IE00B4L5Y983"')
            categorie_input = ui.select(cat_options, value=data['categorie'],
                                          label='Catégorie *').classes('flex-1')

        with ui.row().classes('w-full gap-3'):
            quantite_input = ui.number('Quantité *', value=data['quantite'],
                                         format='%.4f', min=0).classes('flex-1')
            prix_moyen_input = ui.number('Prix de revient unitaire (PRU) *',
                                           value=data['prix_moyen'], format='%.4f',
                                           min=0).classes('flex-1')

        with ui.row().classes('w-full gap-3'):
            cours_input = ui.number(
                'Cours actuel (laisser vide = utilise PRU)',
                value=data['cours_actuel'], format='%.4f', min=0
            ).classes('flex-1')
            devise_input = ui.select(
                {'EUR': 'EUR €', 'USD': 'USD $', 'GBP': 'GBP £', 'CHF': 'CHF', 'BTC': 'BTC'},
                value=data['devise'] or 'EUR', label='Devise'
            ).classes('w-32')

        with ui.input('Date d\'achat', value=date_initiale_fr).classes('w-full') \
                .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input:
            with ui.menu().props('no-parent-event') as menu:
                with ui.date().bind_value(date_input).props('mask="DD/MM/YYYY"'):
                    with ui.row().classes('justify-end'):
                        ui.button('Fermer', on_click=menu.close).props('flat')
            with date_input.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        notes_input = ui.textarea('Notes (optionnel)', value=data['notes'] or '') \
            .classes('w-full').props('rows=2')

        preview = ui.label().classes('text-sm font-medium px-3 py-2 rounded-lg').style(
            f'background-color: {c["card_border"]}; color: {c["text_primary"]};'
        )

        def update_preview():
            try:
                q = float(quantite_input.value or 0)
                pru = float(prix_moyen_input.value or 0)
                cours = float(cours_input.value) if cours_input.value else pru
                pr = q * pru
                valo = q * cours
                pv = valo - pr
                preview.text = (f'💰 Investi : {format_money(pr, decimals=2)}  →  '
                                 f'Valorisé : {format_money(valo, decimals=2)}  →  '
                                 f'+/- : {format_money(pv, decimals=2)}')
            except (TypeError, ValueError):
                preview.text = '💰 Saisissez quantité et PRU pour voir l\'aperçu'

        update_preview()
        for inp in (quantite_input, prix_moyen_input, cours_input):
            inp.on('update:model-value', lambda _: update_preview())

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat')

            def save():
                if not nom_input.value or not nom_input.value.strip():
                    ui.notify('Le nom est obligatoire', type='negative')
                    return
                if quantite_input.value is None or quantite_input.value <= 0:
                    ui.notify('La quantité doit être positive', type='negative')
                    return
                if prix_moyen_input.value is None or prix_moyen_input.value < 0:
                    ui.notify('Le PRU doit être positif', type='negative')
                    return

                date_val = None
                if date_input.value:
                    try:
                        date_val = datetime.strptime(date_input.value, '%d/%m/%Y').date()
                    except ValueError:
                        ui.notify('Date invalide (JJ/MM/AAAA)', type='negative')
                        return

                with get_session() as session:
                    if is_edit:
                        pos = session.get(Position, position_id)
                        pos.nom = nom_input.value.strip()
                        pos.code = code_input.value or None
                        pos.categorie = categorie_input.value
                        pos.quantite = float(quantite_input.value)
                        pos.prix_moyen = float(prix_moyen_input.value)
                        pos.cours_actuel = float(cours_input.value) if cours_input.value else None
                        pos.devise = devise_input.value
                        pos.notes = notes_input.value or None
                        pos.date_ouverture = date_val
                    else:
                        pos = Position(
                            portefeuille_id=portefeuille_id,
                            nom=nom_input.value.strip(),
                            code=code_input.value or None,
                            categorie=categorie_input.value,
                            quantite=float(quantite_input.value),
                            prix_moyen=float(prix_moyen_input.value),
                            cours_actuel=float(cours_input.value) if cours_input.value else None,
                            devise=devise_input.value,
                            notes=notes_input.value or None,
                            date_ouverture=date_val,
                        )
                        session.add(pos)
                    session.commit()

                ui.notify('Position modifiée' if is_edit else 'Position ajoutée',
                          type='positive')
                dialog.close()
                refresh()

            ui.button('Enregistrer', on_click=save).props('unelevated') \
                .classes('bg-blue-600 text-white')

    dialog.open()


def _confirm_delete_position(position_id, name, refresh):
    if name == 'Cash':
        ui.notify(
            'La position Cash ne peut pas être supprimée manuellement.',
            type='warning'
        )
        return

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4'):
        ui.label('Confirmer la suppression').classes('text-xl font-bold')
        ui.label(f'Supprimer la position "{name}" ?')

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