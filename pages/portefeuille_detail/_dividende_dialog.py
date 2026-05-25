"""Dialogue d'enregistrement de dividende."""
import asyncio
from datetime import date, datetime
from nicegui import ui
from sqlalchemy import select

from database.db import get_session
from database.models import Position, Transaction
from utils.formatters import format_money
from services.labels import get_display_name
from pages.portefeuille_detail._cash_helpers import impact_cash, ajuster_cash


def open_dividende_dialog(portefeuille_id, c, refresh,
                          preselect_ticker=None, preselect_code=None, preselect_nom=None):
    """Dialogue pour enregistrer un dividende reçu."""

    # Charger les positions du portefeuille (hors Cash/Fonds€)
    with get_session() as session:
        positions_db = session.execute(
            select(Position).where(
                Position.portefeuille_id == portefeuille_id,
                Position.quantite > 0,
                ~Position.categorie.in_(['Cash', 'Fonds €', 'Fonds Euro']),
            ).order_by(Position.nom)
        ).scalars().all()

        positions_data = []
        for p in positions_db:
            display = get_display_name(
                ticker=p.ticker,
                code=p.code,
                fallback=p.nom
            )
            ticker_code = p.ticker or p.code or '—'
            positions_data.append({
                'id': p.id,
                'ticker': p.ticker,
                'code': p.code,
                'nom': p.nom,
                'display': display,
                'label': f'{display} ({ticker_code})',
                'quantite': p.quantite,
            })

    if not positions_data:
        ui.notify('Aucune position éligible au dividende', type='warning')
        return

    # Trouver la pré-sélection
    preselect_id = None
    for p in positions_data:
        if preselect_ticker and p['ticker'] == preselect_ticker:
            preselect_id = p['id']
            break
        if preselect_code and p['code'] == preselect_code:
            preselect_id = p['id']
            break
        if preselect_nom and p['nom'] == preselect_nom:
            preselect_id = p['id']
            break

    # Options pour le select : {id: label}
    pos_options = {p['id']: p['label'] for p in positions_data}

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-3').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'min-width: 500px; max-width: 600px;'
    ):
        ui.label('🎁 Enregistrer un dividende').classes('text-xl font-bold').style(
            f'color: {c["text_primary"]}'
        )

        # ── Sélection du support ──
        ui.label('Position concernée').classes('text-sm font-medium mt-2').style(
            f'color: {c["text_secondary"]}'
        )

        position_select = ui.select(
            pos_options,
            label='Sélectionnez la position',
            value=preselect_id,
        ).classes('w-full')

        ui.separator()

        # ── Montants ──
        with ui.row().classes('w-full gap-3'):
            montant_brut_input = ui.number(
                'Montant brut (€)', value=0, format='%.2f', min=0
            ).classes('flex-1').props('onfocus="this.select()"')

            montant_net_input = ui.number(
                'Montant net reçu (€)', value=0, format='%.2f', min=0
            ).classes('flex-1').props('onfocus="this.select()"')

        # Quand on saisit le brut, remplir le net si vide
        def on_brut_change():
            if not montant_net_input.value or montant_net_input.value == 0:
                montant_net_input.value = montant_brut_input.value

        montant_brut_input.on('update:model-value', lambda _: on_brut_change())

        ui.label(
            '💡 Le montant net est crédité sur le Cash. '
            'Le brut est enregistré pour le suivi fiscal.'
        ).classes('text-xs px-3 py-2 rounded-lg').style(
            f'background-color: {c["card_border"]}30; '
            f'color: {c["text_secondary"]};'
        )

        # ── Date ──
        date_today_fr = date.today().strftime('%d/%m/%Y')
        with ui.input('Date du dividende', value=date_today_fr).classes('w-full') \
                .props('mask="##/##/####" placeholder="JJ/MM/AAAA" onfocus="this.select()"') as date_input:
            with ui.menu().props('no-parent-event') as menu:
                date_picker = ui.date().bind_value(date_input).props(
                    'mask="DD/MM/YYYY"'
                )
                with date_picker:
                    with ui.row().classes('justify-end'):
                        ui.button('Fermer', on_click=menu.close).props('flat')
            with date_input.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        # ── Notes ──
        notes_input = ui.textarea(
            'Notes (optionnel)',
            placeholder='Ex: Dividende annuel 2024, coupon obligataire...'
        ).classes('w-full').props('rows=2')

        # ── Option crédit cash ──
        credit_cash_cb = ui.checkbox('Créditer le Cash du portefeuille', value=True)

        # ── Résumé ──
        summary_label = ui.label('').classes(
            'text-sm font-medium px-3 py-2 rounded-lg whitespace-pre-line'
        ).style(
            f'background-color: {c["card_border"]}; color: {c["text_primary"]};'
        )

        def update_summary():
            pos_id = position_select.value
            pos = next((p for p in positions_data if p['id'] == pos_id), None)
            brut = float(montant_brut_input.value or 0)
            net = float(montant_net_input.value or 0)
            prel = brut - net if brut > net else 0

            if pos and (brut > 0 or net > 0):
                lines = [
                    f'📈 Titre : {pos["display"]}',
                    f'💶 Brut : {format_money(brut, decimals=2)}',
                ]
                if prel > 0:
                    lines.append(f'🏦 Prélèvements : -{format_money(prel, decimals=2)}')
                lines.append(f'✅ Net reçu : {format_money(net, decimals=2)}')
                if credit_cash_cb.value:
                    lines.append(f'💰 → Crédité sur le Cash')
                summary_label.text = '\n'.join(lines)
            else:
                summary_label.text = '💡 Sélectionnez une position et saisissez le montant'

        position_select.on('update:model-value', lambda _: update_summary())
        montant_brut_input.on('update:model-value', lambda _: update_summary())
        montant_net_input.on('update:model-value', lambda _: update_summary())
        credit_cash_cb.on('update:model-value', lambda _: update_summary())

        update_summary()

        # ── Boutons ──
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat')

            def save_dividende():
                pos_id = position_select.value
                if not pos_id:
                    ui.notify('Sélectionnez une position', type='warning')
                    return

                net = float(montant_net_input.value or 0)
                brut = float(montant_brut_input.value or net)

                if net <= 0:
                    ui.notify('Le montant net doit être positif', type='warning')
                    return

                try:
                    date_val = datetime.strptime(date_input.value, '%d/%m/%Y').date()
                except (ValueError, TypeError):
                    ui.notify('Date invalide (format JJ/MM/AAAA)', type='warning')
                    return

                pos = next((p for p in positions_data if p['id'] == pos_id), None)
                if not pos:
                    ui.notify('Position introuvable', type='negative')
                    return

                with get_session() as session:
                    # Transaction dividende
                    tx = Transaction(
                        portefeuille_id=portefeuille_id,
                        date_operation=date_val,
                        type_operation='dividende',
                        montant=net,
                        libelle=f'Dividende {pos["display"][:40]}',
                        ticker=pos['ticker'],
                        code=pos['code'],
                        nom_titre=pos['nom'],
                        categorie='dividende',
                        quantite=None,
                        prix_unitaire=None,
                    )
                    session.add(tx)

                    # Créditer le cash si demandé
                    if credit_cash_cb.value:
                        ajuster_cash(
                            session, portefeuille_id,
                            impact_cash('dividende', net)
                        )

                    session.commit()

                ui.notify(
                    f'✅ Dividende de {format_money(net)} enregistré pour {pos["display"]}',
                    type='positive'
                )
                dialog.close()
                refresh()

            ui.button('✅ Enregistrer', on_click=save_dividende) \
                .props('unelevated').classes('bg-green-600 text-white')

    dialog.open()