"""Card des transactions + dialogue d'ajout/édition."""
from datetime import date, datetime
from nicegui import ui

from database.db import get_session
from database.models import Transaction
from utils.formatters import format_money, format_date_fr
from pages.portefeuille_detail._cash_helpers import impact_cash, ajuster_cash


def render_transactions_card(transactions, c, is_dark, refresh, portefeuille_id,
                              full_width=False):
    # ✨ Séparer les transactions principales des frais liés
    main_transactions = [t for t in transactions if not t.get('parent_transaction_id')]
    frais_by_parent = {}
    for t in transactions:
        if t.get('parent_transaction_id'):
            parent_id = t['parent_transaction_id']
            frais_by_parent.setdefault(parent_id, []).append(t)

    with ui.card().classes('p-5 rounded-xl w-full').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]};'
    ):
        with ui.row().classes('w-full items-center justify-between mb-3'):
            with ui.column().classes('gap-0'):
                ui.label('Transactions').classes('text-lg font-bold').style(
                    f'color: {c["text_primary"]}'
                )
                ui.label(f'{len(main_transactions)} mouvement(s)').classes('text-xs') \
                    .style(f'color: {c["text_secondary"]}')
            ui.button(
                '+ Transaction',
                on_click=lambda: open_transaction_dialog(portefeuille_id, c, refresh)
            ).props('unelevated dense').classes('bg-blue-600 text-white')

        if not main_transactions:
            with ui.column().classes('w-full items-center py-6 gap-1'):
                ui.icon('receipt_long').classes('text-4xl').style(
                    f'color: {c["text_secondary"]}'
                )
                ui.label('Aucune transaction').classes('text-sm').style(
                    f'color: {c["text_secondary"]}'
                )
            return

        type_colors = {
            'versement': '#10b981', 'retrait': '#ef4444',
            'dividende': '#3b82f6', 'frais': '#f97316',
            'achat': '#8b5cf6', 'vente': '#ec4899',
        }
        type_icons = {
            'versement': 'arrow_downward', 'retrait': 'arrow_upward',
            'dividende': 'paid', 'frais': 'remove_circle',
            'achat': 'shopping_cart', 'vente': 'sell',
        }

        with ui.column().classes('w-full gap-2').style(
            'max-height: 500px; overflow-y: auto;'
        ):
            for t in reversed(main_transactions):
                type_color = type_colors.get(t['type'], '#64748b')
                type_icon = type_icons.get(t['type'], 'circle')
                sign = '+' if t['type'] in ('versement', 'dividende', 'vente') else '-'

                # Frais liés à cette transaction
                frais_lies = frais_by_parent.get(t['id'], [])
                total_frais = sum(f['montant'] for f in frais_lies)

                with ui.row().classes('w-full items-center gap-3 p-2 rounded-lg').style(
                    f'background-color: {c["card_border"]}20;'
                ):
                    # Icône
                    with ui.element('div').classes(
                        'rounded-full flex items-center justify-center'
                    ).style(
                        f'background-color: {type_color}20; '
                        f'width: 32px; height: 32px; min-width: 32px;'
                    ):
                        ui.icon(type_icon).classes('text-base').style(
                            f'color: {type_color}'
                        )

                    # Infos
                    with ui.column().classes('gap-0').style('flex: 1; min-width: 0;'):
                        ui.label(t['libelle'] or t['type'].capitalize()).classes(
                            'text-sm font-medium'
                        ).style(
                            f'color: {c["text_primary"]}; '
                            f'overflow: hidden; text-overflow: ellipsis; '
                            f'white-space: nowrap;'
                        )
                        # Date + frais éventuels
                        sub_text = format_date_fr(t['date'])
                        if total_frais > 0:
                            sub_text += f' • +{format_money(total_frais, decimals=2)} de frais'
                        ui.label(sub_text).classes('text-xs').style(
                            f'color: {c["text_secondary"]}'
                        )

                    # Montant
                    ui.label(f'{sign}{format_money(t["montant"], decimals=2)}').classes(
                        'text-sm font-semibold'
                    ).style(f'color: {type_color}; white-space: nowrap;')

                    # Menu
                    with ui.button(icon='more_vert').props(
                        'flat round dense size=sm'
                    ).style(f'color: {c["text_secondary"]};'):
                        with ui.menu():
                            ui.menu_item(
                                'Modifier',
                                on_click=lambda tid=t['id']:
                                    open_transaction_dialog(
                                        portefeuille_id, c, refresh, transaction_id=tid
                                    )
                            )
                            ui.menu_item(
                                'Supprimer',
                                on_click=lambda tid=t['id'], lib=t['libelle'] or t['type']:
                                    _confirm_delete_transaction(tid, lib, refresh)
                            )


def open_transaction_dialog(portefeuille_id, c, refresh, transaction_id: int = None):
    """Création ou édition d'une transaction."""
    is_edit = transaction_id is not None

    data = {
        'date_operation': date.today().isoformat(),
        'type_operation': 'versement',
        'montant': 0,
        'libelle': '',
    }
    frais_existants = 0
    frais_id = None

    if is_edit:
        with get_session() as session:
            t = session.get(Transaction, transaction_id)
            if t:
                data = {
                    'date_operation': t.date_operation.isoformat(),
                    'type_operation': t.type_operation,
                    'montant': t.montant,
                    'libelle': t.libelle or '',
                }
                # Récupérer les frais liés
                if hasattr(t, 'children'):
                    for child in t.children:
                        if child.type_operation == 'frais':
                            frais_existants = child.montant
                            frais_id = child.id
                            break

    is_achat_vente = data['type_operation'] in ('achat', 'vente')
    date_initiale_fr = date.fromisoformat(data['date_operation']).strftime('%d/%m/%Y')

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'min-width: 450px;'
    ):
        ui.label('Modifier la transaction' if is_edit else 'Ajouter une transaction') \
            .classes('text-xl font-bold').style(f'color: {c["text_primary"]}')

        # Type d'opération
        type_options = {
            'versement': '💰 Versement',
            'retrait': '💸 Retrait',
            'achat': '🛒 Achat de titre',
            'vente': '💹 Vente de titre',
            'dividende': '🎁 Dividende',
            'frais': '⚠️ Frais',
        }

        def on_type_change(e):
            """Bascule vers le dialogue dédié pour Achat ou Vente."""
            if not is_edit:
                if e.value == 'achat':
                    dialog.close()
                    from pages.portefeuille_detail._buy_dialog import open_buy_dialog
                    open_buy_dialog(portefeuille_id, c, refresh)
                elif e.value == 'vente':
                    dialog.close()
                    from pages.portefeuille_detail._sell_dialog import open_sell_dialog
                    open_sell_dialog(portefeuille_id, c, refresh)

        type_input = ui.select(
            type_options,
            value=data['type_operation'],
            label="Type d'opération",
            on_change=on_type_change,
        ).classes('w-full')

        # Si on édite un achat/vente, on désactive le changement de type
        if is_edit and is_achat_vente:
            type_input.props('readonly')

        with ui.input('Date', value=date_initiale_fr).classes('w-full') \
                .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input:
            with ui.menu().props('no-parent-event') as menu:
                with ui.date().bind_value(date_input).props('mask="DD/MM/YYYY"'):
                    with ui.row().classes('justify-end'):
                        ui.button('Fermer', on_click=menu.close).props('flat')
            with date_input.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes(
                    'cursor-pointer'
                )

        montant_input = ui.number('Montant (€)', value=data['montant'],
                                    format='%.2f', min=0).classes('w-full')

        libelle_input = ui.input('Libellé (optionnel)', value=data['libelle']) \
            .classes('w-full').props('placeholder="ex: Versement programmé"')

        # ✨ Champ frais (visible uniquement pour achat/vente)
        frais_input = ui.number(
            '⚠️ Frais associés (€)', value=frais_existants,
            format='%.2f', min=0
        ).classes('w-full')

        if not is_achat_vente:
            frais_input.set_visibility(False)

        info_label = ui.label().classes('text-xs px-3 py-2 rounded-lg').style(
            f'background-color: {c["card_border"]}; color: {c["text_secondary"]};'
        )

        def update_info():
            messages = {
                'versement': '💰 Le montant viendra alimenter la position "Cash"',
                'retrait': '💸 Le montant sera prélevé de la position "Cash"',
                'achat': '🛒 Achat (formulaire dédié)',
                'vente': '💹 Vente (formulaire dédié)',
                'dividende': '🎁 Le dividende viendra alimenter la position "Cash"',
                'frais': '⚠️ Les frais seront prélevés de la position "Cash"',
            }
            info_label.text = messages.get(type_input.value, '')
            if type_input.value in ('achat', 'vente'):
                frais_input.set_visibility(True)
            else:
                frais_input.set_visibility(False)

        update_info()
        type_input.on('update:model-value', lambda _: update_info())

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat')

            def save():
                try:
                    date_val = datetime.strptime(date_input.value, '%d/%m/%Y').date()
                except (ValueError, TypeError):
                    ui.notify('Date invalide', type='negative')
                    return
                if not montant_input.value or montant_input.value <= 0:
                    ui.notify('Le montant doit être positif', type='negative')
                    return

                montant_val = float(montant_input.value)
                frais_val = float(frais_input.value or 0) if type_input.value in ('achat', 'vente') else 0

                with get_session() as session:
                    if is_edit:
                        # ── Modification ──
                        t = session.get(Transaction, transaction_id)
                        old_impact = impact_cash(t.type_operation, t.montant)
                        t.date_operation = date_val
                        t.type_operation = type_input.value
                        t.montant = montant_val
                        t.libelle = libelle_input.value or None
                        new_impact = impact_cash(type_input.value, montant_val)
                        ajuster_cash(session, portefeuille_id, new_impact - old_impact)

                        # Gestion des frais associés
                        if type_input.value in ('achat', 'vente'):
                            existing_frais = None
                            for child in list(t.children):
                                if child.type_operation == 'frais':
                                    existing_frais = child
                                    break

                            if existing_frais:
                                # MAJ des frais existants
                                old_frais_impact = impact_cash('frais', existing_frais.montant)
                                if frais_val > 0:
                                    existing_frais.montant = frais_val
                                    existing_frais.date_operation = date_val
                                    new_frais_impact = impact_cash('frais', frais_val)
                                    ajuster_cash(session, portefeuille_id,
                                                  new_frais_impact - old_frais_impact)
                                else:
                                    # Frais à 0 → on supprime la transaction
                                    ajuster_cash(session, portefeuille_id, -old_frais_impact)
                                    session.delete(existing_frais)
                            elif frais_val > 0:
                                # Création des frais
                                new_frais = Transaction(
                                    portefeuille_id=portefeuille_id,
                                    date_operation=date_val,
                                    type_operation='frais',
                                    montant=frais_val,
                                    libelle=f'Frais - {t.libelle or t.type_operation}',
                                    parent_transaction_id=t.id,
                                )
                                session.add(new_frais)
                                ajuster_cash(session, portefeuille_id,
                                              impact_cash('frais', frais_val))
                    else:
                        # ── Création ──
                        t = Transaction(
                            portefeuille_id=portefeuille_id,
                            date_operation=date_val,
                            type_operation=type_input.value,
                            montant=montant_val,
                            libelle=libelle_input.value or None,
                        )
                        session.add(t)
                        session.flush()
                        ajuster_cash(session, portefeuille_id,
                                      impact_cash(type_input.value, montant_val))

                        # Frais associés (si achat/vente saisi manuellement)
                        if type_input.value in ('achat', 'vente') and frais_val > 0:
                            new_frais = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='frais',
                                montant=frais_val,
                                libelle=f'Frais - {t.libelle or t.type_operation}',
                                parent_transaction_id=t.id,
                            )
                            session.add(new_frais)
                            ajuster_cash(session, portefeuille_id,
                                          impact_cash('frais', frais_val))

                    session.commit()

                ui.notify(
                    'Transaction modifiée' if is_edit else 'Transaction ajoutée',
                    type='positive'
                )
                dialog.close()
                refresh()

            ui.button('Enregistrer', on_click=save).props('unelevated') \
                .classes('bg-blue-600 text-white')

    dialog.open()


def _confirm_delete_transaction(transaction_id, libelle, refresh):
    # On regarde s'il y a des transactions liées (ex: frais d'un achat)
    with get_session() as session:
        t = session.get(Transaction, transaction_id)
        if not t:
            return
        children = list(t.children) if hasattr(t, 'children') else []

    children_info = ''
    if children:
        children_info = (
                f'\n⚠️ {len(children)} transaction(s) liée(s) seront aussi supprimées :\n'
                + '\n'.join(f'  • {ch.libelle or ch.type_operation}' for ch in children)
        )

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4'):
        ui.label('Confirmer la suppression').classes('text-xl font-bold')
        ui.label(f'Supprimer la transaction "{libelle}" ?')
        if children_info:
            ui.label(children_info).classes('text-sm whitespace-pre-line').style(
                'color: #f59e0b'
            )
        ui.label('Le solde de cash sera ajusté en conséquence.').classes('text-sm') \
            .style('color: #f59e0b')

        def do_delete():
            with get_session() as session:
                t = session.get(Transaction, transaction_id)
                if not t:
                    return

                # 1. Supprimer les transactions enfants (frais liés)
                for child in list(t.children):
                    impact_inv = -impact_cash(child.type_operation, child.montant)
                    ajuster_cash(session, child.portefeuille_id, impact_inv)
                    session.delete(child)

                # 2. Supprimer la transaction principale
                impact_inverse = -impact_cash(t.type_operation, t.montant)
                ajuster_cash(session, t.portefeuille_id, impact_inverse)
                session.delete(t)

                session.commit()

            ui.notify(f'"{libelle}" supprimée', type='warning')
            dialog.close()
            refresh()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Annuler', on_click=dialog.close).props('flat')
            ui.button('Supprimer', on_click=do_delete).props('unelevated') \
                .classes('bg-red-600 text-white')

    dialog.open()