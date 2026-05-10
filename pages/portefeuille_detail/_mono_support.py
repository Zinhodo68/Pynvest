"""Section mono-support (livrets) + dialogues."""
from datetime import date, datetime
from nicegui import ui

from database.db import get_session
from database.models import Portefeuille, Valorisation
from utils.formatters import format_money
from pages.portefeuilles_data import get_type_info


def render_mono_support_section(data, type_info, c, portefeuille_id, refresh):
    """Pour Livret A, LDDS... : affiche taux, plafond, intérêts estimés."""
    plafond = data.get('plafond') or type_info.get('plafond')
    taux = data.get('taux_interet') or type_info.get('taux_defaut')
    valo = data['valorisation_actuelle']

    pct_plafond = (valo / plafond * 100) if plafond else 0
    interets_annuels = (valo * taux / 100) if (valo and taux) else 0

    with ui.card().classes('w-full p-5 rounded-xl').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]};'
    ):
        with ui.row().classes('w-full items-center justify-between mb-3'):
            ui.label('Caractéristiques du compte').classes('text-lg font-bold').style(
                f'color: {c["text_primary"]}'
            )
            ui.button(icon='edit', on_click=lambda: _open_mono_dialog(
                portefeuille_id, c, refresh)) \
                .props('flat round dense').style(f'color: {c["text_secondary"]}')

        with ui.row().classes('w-full gap-6'):
            with ui.column().classes('gap-1').style('flex: 1;'):
                ui.label('TAUX D\'INTÉRÊT').classes('text-xs font-semibold tracking-wider').style(
                    f'color: {c["text_secondary"]}'
                )
                if taux is not None:
                    ui.label(f'{taux:.2f} %'.replace('.', ',')).classes(
                        'text-2xl font-bold'
                    ).style(f'color: {type_info["couleur"]}')
                    ui.label(f'≈ {format_money(interets_annuels)} / an d\'intérêts').classes(
                        'text-xs'
                    ).style(f'color: {c["text_secondary"]}')
                else:
                    ui.label('Non renseigné').classes('text-sm').style(
                        f'color: {c["text_secondary"]}'
                    )

            with ui.column().classes('gap-1').style('flex: 1;'):
                ui.label('PLAFOND').classes('text-xs font-semibold tracking-wider').style(
                    f'color: {c["text_secondary"]}'
                )
                if plafond:
                    ui.label(format_money(plafond)).classes('text-2xl font-bold').style(
                        f'color: {c["text_primary"]}'
                    )
                    with ui.element('div').classes('w-full mt-1').style(
                        f'background-color: {c["card_border"]}; height: 6px; border-radius: 3px;'
                    ):
                        ui.element('div').style(
                            f'background-color: {type_info["couleur"]}; '
                            f'width: {min(pct_plafond, 100)}%; height: 100%; border-radius: 3px;'
                        )
                    ui.label(
                        f'{pct_plafond:.1f}% du plafond utilisé'.replace('.', ',')
                    ).classes('text-xs').style(f'color: {c["text_secondary"]}')
                else:
                    ui.label('Pas de plafond').classes('text-sm').style(
                        f'color: {c["text_secondary"]}'
                    )

            if plafond:
                with ui.column().classes('gap-1').style('flex: 1;'):
                    dispo = max(0, plafond - valo)
                    ui.label('DISPONIBLE').classes('text-xs font-semibold tracking-wider').style(
                        f'color: {c["text_secondary"]}'
                    )
                    ui.label(format_money(dispo)).classes('text-2xl font-bold').style(
                        f'color: {"#10b981" if dispo > 0 else "#ef4444"}'
                    )
                    ui.label('Avant atteinte du plafond').classes('text-xs').style(
                        f'color: {c["text_secondary"]}'
                    )


def _open_mono_dialog(portefeuille_id, c, refresh):
    with get_session() as session:
        p = session.get(Portefeuille, portefeuille_id)
        type_info = get_type_info(p.type)
        current_taux = p.taux_interet or type_info.get('taux_defaut')
        current_plafond = p.plafond or type_info.get('plafond')

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'min-width: 400px;'
    ):
        ui.label('Modifier les caractéristiques').classes('text-xl font-bold').style(
            f'color: {c["text_primary"]}'
        )

        taux_input = ui.number('Taux d\'intérêt (%)', value=current_taux,
                                format='%.2f', min=0, step=0.05).classes('w-full')
        plafond_input = ui.number('Plafond (€)', value=current_plafond,
                                    format='%.0f', min=0).classes('w-full')

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat')

            def save():
                with get_session() as session:
                    p = session.get(Portefeuille, portefeuille_id)
                    p.taux_interet = float(taux_input.value) if taux_input.value else None
                    p.plafond = float(plafond_input.value) if plafond_input.value else None
                    session.commit()
                ui.notify('Caractéristiques mises à jour', type='positive')
                dialog.close()
                refresh()

            ui.button('Enregistrer', on_click=save).props('unelevated') \
                .classes('bg-blue-600 text-white')

    dialog.open()


def open_valorisation_dialog(portefeuille_id, c, refresh):
    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'min-width: 400px;'
    ):
        ui.label('Saisir une valorisation').classes('text-xl font-bold').style(
            f'color: {c["text_primary"]}'
        )
        ui.label('Snapshot de la valeur de votre portefeuille à une date donnée.') \
            .classes('text-sm').style(f'color: {c["text_secondary"]}')

        date_today_fr = date.today().strftime('%d/%m/%Y')
        with ui.input('Date de valeur', value=date_today_fr).classes('w-full') \
                .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input:
            with ui.menu().props('no-parent-event') as menu:
                with ui.date().bind_value(date_input).props('mask="DD/MM/YYYY"'):
                    with ui.row().classes('justify-end'):
                        ui.button('Fermer', on_click=menu.close).props('flat')
            with date_input.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        montant_input = ui.number('Valeur (€)', value=0, format='%.2f', min=0) \
            .classes('w-full')

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat')

            def save():
                try:
                    date_val = datetime.strptime(date_input.value, '%d/%m/%Y').date()
                except (ValueError, TypeError):
                    ui.notify('Date invalide', type='negative')
                    return
                if montant_input.value is None or montant_input.value < 0:
                    ui.notify('Montant invalide', type='negative')
                    return

                with get_session() as session:
                    v = Valorisation(
                        portefeuille_id=portefeuille_id,
                        date_valeur=date_val,
                        montant=float(montant_input.value),
                    )
                    session.add(v)
                    session.commit()
                ui.notify('Valorisation enregistrée', type='positive')
                dialog.close()
                refresh()

            ui.button('Enregistrer', on_click=save).props('unelevated') \
                .classes('bg-blue-600 text-white')

    dialog.open()