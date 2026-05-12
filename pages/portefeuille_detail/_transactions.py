"""Card des transactions + dialogue d'ajout/édition."""
import math
from datetime import date, datetime
from nicegui import ui
from sqlalchemy import select

from database.db import get_session
from database.models import Transaction, Portefeuille, Position
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
            'interets': '#eab308',
        }
        type_icons = {
            'versement': 'arrow_downward', 'retrait': 'arrow_upward',
            'dividende': 'paid', 'frais': 'remove_circle',
            'achat': 'shopping_cart', 'vente': 'sell',
            'interets': 'trending_up',
        }

        with ui.column().classes('w-full gap-2').style(
                'max-height: 500px; overflow-y: auto;'
        ):
            for t in reversed(main_transactions):
                type_color = type_colors.get(t['type'], '#64748b')
                type_icon = type_icons.get(t['type'], 'circle')
                sign = '+' if t['type'] in ('versement', 'dividende', 'vente', 'interets') else '-'

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
                        display_libelle = t['libelle'] or t['type'].capitalize()
                        if t['type'] == 'dividende':
                            if (t.get('quantite') is not None and t.get('quantite') > 0 and
                                    t.get('prix_unitaire') is not None and t.get('prix_unitaire') > 0):
                                display_libelle += ' (C)'
                            else:
                                display_libelle += ' (D)'
                        # (NOUVEAU AMÉLIORATION) Indiquer si les frais sont en parts
                        elif t['type'] == 'frais':
                            if (t.get('quantite') is not None and t.get('quantite') > 0 and
                                    t.get('prix_unitaire') is not None and t.get('prix_unitaire') > 0):
                                display_libelle += ' (en parts)'

                        ui.label(display_libelle).classes(
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

                        # (MODIFIÉ) Afficher l'actif source + détails de parts si dividende (C) ou frais en parts
                        if t['type'] == 'dividende' and t.get('nom_titre'):
                            sub_text += f' • Actif: {t["nom_titre"]}'
                            if (t.get('quantite') is not None and t.get('quantite') > 0 and
                                    t.get('prix_unitaire') is not None and t.get('prix_unitaire') > 0):
                                sub_text += f' ({t["quantite"]:g} parts @ {t["prix_unitaire"]:.4f}€)'
                        # (NOUVEAU AMÉLIORATION) Détails pour les frais en parts
                        elif t['type'] == 'frais' and t.get('nom_titre') and \
                                (t.get('quantite') is not None and t.get('quantite') > 0 and
                                 t.get('prix_unitaire') is not None and t.get('prix_unitaire') > 0):
                            sub_text += f' • Actif: {t["nom_titre"]} ({t["quantite"]:g} parts @ {t["prix_unitaire"]:.4f}€)'

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
    """Création ou édition d'une transaction (Gère le cash PEA et les Fonds € AV)."""
    is_edit = transaction_id is not None

    data = {
        'date_operation': date.today().isoformat(),
        'type_operation': 'versement',
        'montant': 0.0,
        'libelle': '',
        'source_position_id': None,
        # (NOUVEAU AMÉLIORATION) Initialiser l'état du toggle frais
        'initial_fee_type': 'cash',  # 'cash' ou 'parts'
        'initial_fee_parts_quantity': 0.0,
    }
    frais_existants = 0

    # 1. Détection du type de portefeuille et récupération des Fonds € / Actifs sources de dividendes / Actifs pour frais en parts
    with get_session() as session:
        ptf = session.get(Portefeuille, portefeuille_id)
        is_av_per = ptf.type in ['Assurance-Vie', 'AV', 'PER', 'Assurance Vie']

        fonds_euros_dict = {}
        if is_av_per:
            fonds_euros_db = session.execute(
                select(Position).where(
                    Position.portefeuille_id == portefeuille_id,
                    Position.categorie == 'Fonds Euro'
                )
            ).scalars().all()
            for fe in fonds_euros_db:
                fonds_euros_dict[fe.id] = fe.nom

        # Récupérer les positions qui peuvent être des sources de dividendes ou des cibles pour frais en parts
        chargeable_positions_db = session.execute(  # (MODIFIÉ) Renommé pour être plus générique
            select(Position).where(
                Position.portefeuille_id == portefeuille_id,
                Position.categorie.not_in(['Fonds Euro', 'Cash'])
            )
        ).scalars().all()
        chargeable_positions_options = {  # (MODIFIÉ) Renommé
            pos.id: {'nom': pos.nom, 'quantite': pos.quantite, 'cours_actuel': pos.cours_actuel}
            for pos in chargeable_positions_db
        }

        if is_edit:
            t = session.get(Transaction, transaction_id)
            if t:
                data['date_operation'] = t.date_operation.isoformat()
                data['type_operation'] = t.type_operation
                data['montant'] = t.montant
                data['libelle'] = t.libelle or ''

                # Charger la source si applicable (pour dividende et frais en parts)
                if t.nom_titre:
                    source_pos_from_tx = session.execute(
                        select(Position.id).where(
                            Position.portefeuille_id == portefeuille_id,
                            Position.nom == t.nom_titre,
                            Position.categorie.not_in(['Fonds Euro', 'Cash'])
                        )
                    ).scalar_one_or_none()
                    if source_pos_from_tx:
                        data['source_position_id'] = source_pos_from_tx

                # (NOUVEAU AMÉLIORATION) Charger l'état initial des frais en parts pour l'édition
                if t.type_operation == 'frais':
                    if t.quantite is not None and t.quantite > 0 and \
                            t.prix_unitaire is not None and t.prix_unitaire > 0:
                        data['initial_fee_type'] = 'parts'
                        data['initial_fee_parts_quantity'] = t.quantite
                    else:
                        data['initial_fee_type'] = 'cash'

    # --- DÉFINITIONS DE VARIABLES NÉCESSAIRES AVANT LE DIALOGUE ---
    is_initial_achat_vente_edit = is_edit and data['type_operation'] in ('achat', 'vente')

    date_initiale_fr = date.fromisoformat(data['date_operation']).strftime('%d/%m/%Y')

    last_dividend_input_changed = {'value': None}
    # (NOUVEAU AMÉLIORATION) État pour gérer la double saisie frais en parts
    last_fees_parts_input_changed = {'value': None}  # 'deduct_qty' ou 'final_qty'

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]}; '
            f'min-width: 450px;'
    ):
        ui.label('Modifier la transaction' if is_edit else 'Ajouter une transaction') \
            .classes('text-xl font-bold').style(f'color: {c["text_primary"]}')

        type_options = {
            'versement': '💰 Versement',
            'retrait': '💸 Retrait',
            'achat': '🛒 Achat de titre',
            'vente': '💹 Vente de titre',
            'dividende': '🎁 Dividende',
            'frais': '⚠️ Frais',
        }
        if is_av_per:
            type_options['interets'] = '📈 Intérêts Fonds €'

        type_input = None
        fonds_euro_select = None
        dividend_source_select = None  # Reste pour la clarté du code des dividendes
        fees_asset_select = None  # (NOUVEAU AMÉLIORATION) Sélecteur pour l'actif des frais en parts
        no_chargeable_assets_label = None  # (NOUVEAU AMÉLIORATION) Pour l'avertissement quand pas d'actifs pour frais en parts
        no_dividend_sources_label = None  # Reste pour la clarté
        reinvest_checkbox = None
        fee_type_toggle = None  # (NOUVEAU AMÉLIORATION) Toggle pour les frais
        date_input_ui_element = None
        date_picker = None
        montant_input = None
        dividend_per_share_input = None
        dividend_parts_input = None
        fees_parts_to_deduct_input = None  # (NOUVEAU AMÉLIORATION)
        fees_final_parts_qty_input = None  # (NOUVEAU AMÉLIORATION)
        current_fees_parts_qty_label = None  # (NOUVEAU AMÉLIORATION)
        libelle_input = None
        frais_input = None  # Ceci est pour les frais liés aux Achat/Vente, pas pour le type 'frais'
        info_label = None

        def on_type_change(e):
            if not is_edit:
                if e.value == 'achat':
                    dialog.close()
                    from pages.portefeuille_detail._buy_dialog import open_buy_dialog
                    open_buy_dialog(portefeuille_id, c, refresh)
                    return
                elif e.value == 'vente':
                    dialog.close()
                    from pages.portefeuille_detail._sell_dialog import open_sell_dialog
                    open_sell_dialog(portefeuille_id, c, refresh)
                    return
            update_visibility()

        # --- CRÉATION DES ÉLÉMENTS UI DANS LE BON ORDRE ---

        type_input = ui.select(
            type_options,
            value=data['type_operation'],
            label="Type d'opération",
            on_change=on_type_change,
        ).classes('w-full')

        if is_edit and data['type_operation'] not in ('achat', 'vente'):
            type_input.props('readonly')

        if is_av_per:
            if not fonds_euros_dict:
                ui.label("⚠️ Aucun Fonds € n'existe. Créez-en un via Achat > Manuel pour pouvoir faire des versements.") \
                    .classes('text-red-500 text-xs font-bold')
            else:
                fonds_euro_select = ui.select(
                    fonds_euros_dict,
                    label="Fonds € cible *",
                    value=list(fonds_euros_dict.keys())[0] if fonds_euros_dict else None
                ).classes('w-full')

        # Sélecteur de l'actif source pour les dividendes
        if chargeable_positions_options:  # (MODIFIÉ) Utiliser la liste générique
            dividend_source_select = ui.select(
                {idx: d['nom'] for idx, d in chargeable_positions_options.items()},
                label='Actif source du dividende *',
                value=data['source_position_id'] if is_edit and data.get('source_position_id') and data[
                    'type_operation'] == 'dividende' else None  # (MODIFIÉ) Charger si c'est un dividende
            ).classes('w-full')
            # (NOUVEAU AMÉLIORATION) Sélecteur pour l'actif des frais en parts (partage la même liste d'options)
            fees_asset_select = ui.select(
                {idx: d['nom'] for idx, d in chargeable_positions_options.items()},
                label='Actif à débiter (parts) *',
                value=data['source_position_id'] if is_edit and data.get('source_position_id') and data[
                    'type_operation'] == 'frais' else None  # (MODIFIÉ) Charger si c'est un frais en parts
            ).classes('w-full')
        else:
            # (MODIFIÉ) Avertissement générique pour l'absence d'actifs chargeables
            no_chargeable_assets_label = ui.label("⚠️ Aucun actif (hors Cash/Fonds €) trouvé dans ce portefeuille.") \
                .classes('text-red-500 text-xs font-bold')
            # no_dividend_sources_label n'est plus nécessaire car remplacé par no_chargeable_assets_label

        reinvest_checkbox = ui.checkbox(
            'Dividende réinvesti en parts',
            value=False
        ).classes('mt-0')

        # (NOUVEAU AMÉLIORATION) Toggle pour le type de frais (cash ou parts)
        fee_type_toggle = ui.toggle(
            {'cash': 'Frais en euros', 'parts': 'Frais en parts'},
            value=data['initial_fee_type'] if is_edit and data['type_operation'] == 'frais' else 'cash',
        ).classes('w-full').props('toggle-color="primary" spread')

        with ui.input('Date', value=date_initiale_fr).classes('w-full') \
                .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input_ui_element:
            with ui.menu().props('no-parent-event') as menu:
                date_picker = ui.date().bind_value(date_input_ui_element).props('mask="DD/MM/YYYY"')
                with date_picker:
                    with ui.row().classes('justify-end'):
                        ui.button('Fermer', on_click=menu.close).props('flat')
            with date_input_ui_element.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes(
                    'cursor-pointer'
                )

        montant_input = ui.number('Montant (€)',  # (MODIFIÉ) Label générique pour les flux, y compris frais cash
                                  value=data['montant'],
                                  format='%.2f', min=0).classes('w-full')
        dividend_per_share_input = ui.number('Dividende par part (€)',
                                             value=0.0,
                                             format='%.4f', min=0).classes('w-full')
        dividend_parts_input = ui.number('Nombre de parts réinvesties *',
                                         value=0.0,
                                         format='%.4f', min=0, step=0.01).classes('w-full')

        # (NOUVEAU AMÉLIORATION) Champs pour les frais en parts
        current_fees_parts_qty_label = ui.label("Quantité actuelle : 0.0 parts").classes('text-sm text-gray-500')
        fees_parts_to_deduct_input = ui.number('Quantité de parts à prélever *', value=0.0,
                                               format='%.4f', min=0, step=0.01).classes('w-full')
        fees_final_parts_qty_input = ui.number('Quantité finale de parts *', value=0.0,
                                               format='%.4f', min=0, step=0.01).classes('w-full')

        libelle_input = ui.input('Libellé (optionnel)', value=data['libelle']) \
            .classes('w-full')

        frais_input = ui.number(  # Champ pour les frais associés aux Achat/Vente, devrait être toujours caché ici
            '⚠️ Frais associés (€)', value=frais_existants,
            format='%.2f', min=0
        ).classes('w-full')

        info_label = ui.label().classes('text-xs px-3 py-2 rounded-lg whitespace-pre-line').style(
            f'background-color: {c["card_border"]}; color: {c["text_secondary"]};'
        )

        # (NOUVEAU AMÉLIORATION) Fonction pour gérer les calculs des frais en parts
        def update_fees_parts_amounts(source_input):
            if type_input.value != 'frais' or fee_type_toggle.value != 'parts':
                return

            if not fees_asset_select or not fees_asset_select.value:
                current_fees_parts_qty_label.text = "Quantité actuelle : 0.0 parts"
                fees_parts_to_deduct_input.value = 0.0
                fees_final_parts_qty_input.value = 0.0
                return

            if last_fees_parts_input_changed['value'] == source_input:
                last_fees_parts_input_changed['value'] = None
                return

            selected_id = fees_asset_select.value
            current_qty = chargeable_positions_options.get(selected_id, {}).get('quantite', 0)
            current_fees_parts_qty_label.text = f"Quantité actuelle : {current_qty:g} parts"

            if current_qty > 0:
                if source_input == 'deduct_qty':
                    deduct_val = float(fees_parts_to_deduct_input.value or 0)
                    final_val = current_qty - deduct_val
                    last_fees_parts_input_changed['value'] = 'final_qty'
                    fees_final_parts_qty_input.value = round(max(0.0, final_val), 4)  # Ne pas descendre en dessous de 0
                elif source_input == 'final_qty':
                    final_val = float(fees_final_parts_qty_input.value or 0)
                    deduct_val = current_qty - final_val
                    last_fees_parts_input_changed['value'] = 'deduct_qty'
                    fees_parts_to_deduct_input.value = round(max(0.0, deduct_val), 4)
            else:  # Quantité actuelle est 0
                fees_parts_to_deduct_input.value = 0.0
                fees_final_parts_qty_input.value = 0.0

        def update_dividend_amounts(source_input):
            if type_input.value != 'dividende' or reinvest_checkbox.value:
                return

            if not dividend_source_select or not dividend_source_select.value:
                montant_input.value = 0.0
                dividend_per_share_input.value = 0.0
                return

            if last_dividend_input_changed['value'] == source_input:
                last_dividend_input_changed['value'] = None
                return

            selected_id = dividend_source_select.value
            current_qty = chargeable_positions_options.get(selected_id, {}).get('quantite', 0)  # (MODIFIÉ)

            if current_qty > 0:
                if source_input == 'total':
                    total_val = float(montant_input.value or 0)
                    per_share_val = total_val / current_qty
                    last_dividend_input_changed['value'] = 'per_share'
                    dividend_per_share_input.value = round(per_share_val, 4)
                elif source_input == 'per_share':
                    per_share_val = float(dividend_per_share_input.value or 0)
                    total_val = per_share_val * current_qty
                    last_dividend_input_changed['value'] = 'total'
                    montant_input.value = round(total_val, 2)
            else:
                if source_input == 'total':
                    last_dividend_input_changed['value'] = 'per_share'
                    dividend_per_share_input.value = 0.0
                elif source_input == 'per_share':
                    last_dividend_input_changed['value'] = 'total'
                    montant_input.value = 0.0

        def update_dynamic_fields():
            current_type = type_input.value
            current_date_year = date_input_ui_element.value[-4:] if len(date_input_ui_element.value) == 10 else ''

            if current_type == 'versement':
                libelle_input.props('placeholder="ex: Versement programmé"')
            elif current_type == 'retrait':
                libelle_input.props('placeholder="ex: Retrait pour projet immobilier"')
            elif current_type == 'interets':
                libelle_input.props(f'placeholder="ex: Intérêts annuels {current_date_year}"')
            elif current_type == 'dividende':
                selected_id = dividend_source_select.value if dividend_source_select else None
                source_name = chargeable_positions_options.get(selected_id, {}).get('nom', 'Actif')  # (MODIFIÉ)
                if reinvest_checkbox.value:
                    libelle_input.props(f'placeholder="ex: Dividende réinvesti {source_name}"')
                else:
                    libelle_input.props(f'placeholder="ex: Dividende {source_name}"')

                if not reinvest_checkbox.value:
                    update_dividend_amounts('total')
            elif current_type == 'frais':
                selected_id = fees_asset_select.value if fees_asset_select else None  # (NOUVEAU AMÉLIORATION)
                source_name = chargeable_positions_options.get(selected_id, {}).get('nom',
                                                                                    'Actif')  # (NOUVEAU AMÉLIORATION)
                if fee_type_toggle.value == 'parts':  # (NOUVEAU AMÉLIORATION)
                    libelle_input.props(f'placeholder="ex: Frais de gestion - {source_name} (parts)"')
                    update_fees_parts_amounts('deduct_qty')  # (NOUVEAU AMÉLIORATION)
                else:
                    libelle_input.props('placeholder="ex: Frais de gestion annuels"')
            else:
                libelle_input.props('')

            # Remplissage automatique du libellé si vide et type de transaction spécifique
            if not libelle_input.value or \
                    (current_type == 'interets' and libelle_input.value.startswith("Intérêts annuels")) or \
                    (current_type == 'dividende' and libelle_input.value.startswith("Dividende -")) or \
                    (current_type == 'frais' and libelle_input.value.startswith(
                        "Frais de gestion -")):  # (NOUVEAU AMÉLIORATION)
                if current_type == 'interets':
                    libelle_input.value = f"Intérêts annuels {current_date_year}" if current_date_year else ""
                elif current_type == 'dividende' and dividend_source_select and dividend_source_select.value:
                    source_name = chargeable_positions_options[dividend_source_select.value]['nom']  # (MODIFIÉ)
                    if reinvest_checkbox.value:
                        libelle_input.value = f"Dividende réinvesti - {source_name}"
                    else:
                        libelle_input.value = f"Dividende - {source_name}"
                # (NOUVEAU AMÉLIORATION) Remplir le libellé pour les frais
                elif current_type == 'frais':
                    selected_id = fees_asset_select.value if fees_asset_select else None
                    source_name = chargeable_positions_options.get(selected_id, {}).get('nom', 'Actif')
                    if fee_type_toggle.value == 'parts':
                        libelle_input.value = f"Frais de gestion - {source_name} (parts)"
                    else:
                        libelle_input.value = f"Frais de gestion {current_date_year}" if current_date_year else "Frais de gestion"

            # Nettoyer le libellé pour les autres types si on a une valeur auto-générée qui ne correspond plus
            if current_type not in ('interets', 'dividende', 'frais') and \
                    libelle_input.value.startswith(
                        ("Intérêts annuels", "Dividende -", "Frais de gestion -")):  # (MODIFIÉ)
                libelle_input.value = ''

        def update_visibility():
            val = type_input.value

            is_reinvesting_dividend = reinvest_checkbox.value and val == 'dividende'
            is_fees_in_parts = val == 'frais' and fee_type_toggle.value == 'parts'  # (NOUVEAU AMÉLIORATION)

            target_str = "du Fonds € sélectionné" if is_av_per and not is_reinvesting_dividend and not is_fees_in_parts else 'de la position "Cash"'  # (MODIFIÉ)

            # (MODIFIÉ) Messages d'info plus précis pour les frais
            if is_reinvesting_dividend:
                info_label.text = f'🎁 Le dividende sera réinvesti en parts de l\'actif. Pas d\'impact sur le solde {target_str}.'
            elif is_fees_in_parts:  # (NOUVEAU AMÉLIORATION)
                info_label.text = f'⚠️ Les frais seront prélevés en parts de l\'actif sélectionné. Pas d\'impact sur le solde {target_str}.'
            else:
                messages = {
                    'versement': f'💰 Le montant viendra alimenter le solde {target_str}',
                    'retrait': f'💸 Le montant sera prélevé {target_str}',
                    'achat': '🛒 Achat (formulaire dédié)',
                    'vente': '💹 Vente (formulaire dédié)',
                    'dividende': f'🎁 Le dividende viendra alimenter le solde {target_str} et sera lié à l\'actif source.',
                    'frais': f'⚠️ Les frais seront prélevés {target_str}',
                    'interets': '📈 Les intérêts annuels viendront s\'ajouter au Fonds € (n\'impacte pas le Total Versé pour les perfs)'
                }
                info_label.text = messages.get(val, '')

            is_visible_for_flux = val not in ('achat', 'vente')

            # Gérer la visibilité de chaque élément
            date_input_ui_element.set_visibility(is_visible_for_flux)
            libelle_input.set_visibility(is_visible_for_flux)
            frais_input.set_visibility(
                False)  # Ce champ est pour les frais liés à achat/vente, pas pour le type 'frais' autonome

            # (MODIFIÉ) Visibilité des champs spécifiques au DIVIDENDE
            if val == 'dividende':
                if dividend_source_select: dividend_source_select.set_visibility(True)
                # (REVERT) no_dividend_sources_label devient no_chargeable_assets_label
                if no_chargeable_assets_label: no_chargeable_assets_label.set_visibility(
                    not chargeable_positions_options and not is_av_per)  # (MODIFIÉ)
                reinvest_checkbox.set_visibility(True)

                montant_input.set_visibility(not is_reinvesting_dividend)
                dividend_per_share_input.set_visibility(not is_reinvesting_dividend)
                dividend_parts_input.set_visibility(is_reinvesting_dividend)

                if fees_asset_select: fees_asset_select.set_visibility(False)  # (NOUVEAU AMÉLIORATION)
                fee_type_toggle.set_visibility(False)  # (NOUVEAU AMÉLIORATION)
                current_fees_parts_qty_label.set_visibility(False)  # (NOUVEAU AMÉLIORATION)
                fees_parts_to_deduct_input.set_visibility(False)  # (NOUVEAU AMÉLIORATION)
                fees_final_parts_qty_input.set_visibility(False)  # (NOUVEAU AMÉLIORATION)


            # (NOUVEAU AMÉLIORATION) Visibilité des champs spécifiques aux FRAIS
            elif val == 'frais':
                # Masquer les champs dividende
                if dividend_source_select: dividend_source_select.set_visibility(False)
                reinvest_checkbox.set_visibility(False)
                dividend_per_share_input.set_visibility(False)
                dividend_parts_input.set_visibility(False)

                # Afficher les champs frais
                fee_type_toggle.set_visibility(True)
                if no_chargeable_assets_label: no_chargeable_assets_label.set_visibility(
                    not chargeable_positions_options and fee_type_toggle.value == 'parts')  # (MODIFIÉ)

                if fee_type_toggle.value == 'cash':
                    montant_input.set_visibility(True)
                    if fees_asset_select: fees_asset_select.set_visibility(False)
                    current_fees_parts_qty_label.set_visibility(False)
                    fees_parts_to_deduct_input.set_visibility(False)
                    fees_final_parts_qty_input.set_visibility(False)
                else:  # frais en parts
                    montant_input.set_visibility(False)
                    if fees_asset_select: fees_asset_select.set_visibility(True)
                    current_fees_parts_qty_label.set_visibility(True)
                    fees_parts_to_deduct_input.set_visibility(True)
                    fees_final_parts_qty_input.set_visibility(True)

            # (MODIFIÉ) Pour les autres types de flux (versement, retrait, interets)
            else:
                if dividend_source_select: dividend_source_select.set_visibility(False)
                if fees_asset_select: fees_asset_select.set_visibility(False)  # (NOUVEAU AMÉLIORATION)
                if no_chargeable_assets_label: no_chargeable_assets_label.set_visibility(False)  # (MODIFIÉ)
                reinvest_checkbox.set_visibility(False)
                fee_type_toggle.set_visibility(False)  # (NOUVEAU AMÉLIORATION)
                montant_input.set_visibility(is_visible_for_flux)
                dividend_per_share_input.set_visibility(False)
                dividend_parts_input.set_visibility(False)
                current_fees_parts_qty_label.set_visibility(False)  # (NOUVEAU AMÉLIORATION)
                fees_parts_to_deduct_input.set_visibility(False)  # (NOUVEAU AMÉLIORATION)
                fees_final_parts_qty_input.set_visibility(False)  # (NOUVEAU AMÉLIORATION)

            if is_av_per and fonds_euro_select:
                fonds_euro_select.set_visibility(val in ('versement', 'retrait', 'interets') or \
                                                 (val == 'dividende' and not is_reinvesting_dividend) or \
                                                 (val == 'frais' and not is_fees_in_parts))  # (MODIFIÉ)

            update_dynamic_fields()

            # --- CONFIGURATION DES ÉCOUTEURS D'ÉVÉNEMENTS APRÈS LA CRÉATION ET LA LOGIQUE DE VISIBILITÉ INITIALE ---

        type_input.on('update:model-value', update_visibility)
        if dividend_source_select:
            dividend_source_select.on('update:model-value', update_dynamic_fields)

        montant_input.on('update:model-value', lambda: update_dividend_amounts('total'))
        dividend_per_share_input.on('update:model-value', lambda: update_dividend_amounts('per_share'))

        reinvest_checkbox.on('update:model-value', update_visibility)

        # (NOUVEAU AMÉLIORATION) Écouteurs pour le toggle de frais et les champs de parts
        fee_type_toggle.on('update:model-value', update_visibility)
        if fees_asset_select:
            fees_asset_select.on('update:model-value', lambda: update_fees_parts_amounts('deduct_qty'))
            fees_asset_select.on('update:model-value', update_dynamic_fields)  # Pour le libellé auto
        fees_parts_to_deduct_input.on('update:model-value', lambda: update_fees_parts_amounts('deduct_qty'))
        fees_final_parts_qty_input.on('update:model-value', lambda: update_fees_parts_amounts('final_qty'))

        date_input_ui_element.on('update:model-value', update_dynamic_fields)
        date_picker.on('update:model-value', update_dynamic_fields)

        update_visibility()

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat')

            def save():
                try:
                    date_val = datetime.strptime(date_input_ui_element.value, '%d/%m/%Y').date()
                except (ValueError, TypeError):
                    ui.notify('Date invalide', type='negative')
                    return

                type_val = type_input.value
                is_reinvesting_current_state = reinvest_checkbox.value and type_val == 'dividende'
                is_fees_in_parts_current_state = fee_type_toggle.value == 'parts' and type_val == 'frais'  # (NOUVEAU AMÉLIORATION)

                # Récupération des valeurs des champs
                montant_val_for_tx = float(montant_input.value or 0)  # Montant principal pour cash/autres
                parts_reinvesties = float(dividend_parts_input.value or 0)  # Pour dividende C
                parts_a_prelever_frais = float(
                    fees_parts_to_deduct_input.value or 0)  # (NOUVEAU AMÉLIORATION) Pour frais en parts

                # --- VALIDATIONS ---
                if type_val == 'dividende':
                    if not dividend_source_select or not dividend_source_select.value:
                        ui.notify("Veuillez sélectionner l'actif source du dividende.", type='negative')
                        return

                    if is_reinvesting_current_state:
                        if not parts_reinvesties or parts_reinvesties <= 0:
                            ui.notify("Le nombre de parts réinvesties doit être supérieur à zéro.", type='negative')
                            return
                    else:  # Mode dividende cash
                        if not montant_val_for_tx or montant_val_for_tx <= 0:
                            ui.notify("Le montant total du dividende doit être positif.", type='negative')
                            return
                        if is_av_per and (not fonds_euro_select or not fonds_euro_select.value):
                            ui.notify("Veuillez sélectionner un Fonds € cible.", type='negative')
                            return

                # (NOUVEAU AMÉLIORATION) Validations spécifiques aux frais
                elif type_val == 'frais':
                    if is_fees_in_parts_current_state:
                        if not fees_asset_select or not fees_asset_select.value:
                            ui.notify("Veuillez sélectionner l'actif dont les parts seront prélevées.", type='negative')
                            return
                        if not parts_a_prelever_frais or parts_a_prelever_frais <= 0:
                            ui.notify("La quantité de parts à prélever doit être supérieure à zéro.", type='negative')
                            return
                        # Vérifier la quantité disponible
                        selected_asset_qty = chargeable_positions_options.get(fees_asset_select.value, {}).get(
                            'quantite', 0)
                        if parts_a_prelever_frais > selected_asset_qty:
                            ui.notify(f"Quantité de parts insuffisante. Disponible: {selected_asset_qty:g}",
                                      type='negative')
                            return
                    else:  # Frais en euros
                        if not montant_val_for_tx or montant_val_for_tx <= 0:
                            ui.notify("Le montant des frais doit être positif.", type='negative')
                            return
                        if is_av_per and (not fonds_euro_select or not fonds_euro_select.value):
                            ui.notify("Veuillez sélectionner un Fonds € cible pour le prélèvement des frais.",
                                      type='negative')
                            return

                # Autres types de transactions (versement, retrait, interets)
                else:
                    if not montant_val_for_tx or montant_val_for_tx <= 0:
                        ui.notify("Le montant doit être positif.", type='negative')
                        return
                    if is_av_per and (not fonds_euro_select or not fonds_euro_select.value):
                        ui.notify("Veuillez sélectionner un Fonds € cible.", type='negative')
                        return

                # --- DÉBUT DE LA LOGIQUE DE SAUVEGARDE EN BDD ---
                with get_session() as session:
                    def update_fonds_euro(fe_id, type_op, montant):
                        fe = session.get(Position, fe_id)
                        if not fe: return
                        if type_op in ['versement', 'dividende', 'interets']:
                            fe.quantite += montant
                        elif type_op in ['retrait', 'frais']:
                            fe.quantite -= montant

                    if is_edit:
                        ui.notify(
                            "L'édition des transactions de flux (versement, retrait, dividende, intérêts, frais) "
                            "n'est pas supportée directement dans ce dialogue. "
                            "Veuillez la supprimer et la recréer si nécessaire.",
                            type='warning'
                        )
                        return

                    # --- CRÉATION D'UNE NOUVELLE TRANSACTION (mode `is_edit=False`) ---
                    libelle = libelle_input.value
                    if not libelle:
                        if type_val == 'interets':
                            libelle = f"Intérêts annuels {date_val.year}"
                        elif type_val == 'dividende':
                            selected_source_name = chargeable_positions_options.get(dividend_source_select.value)[
                                'nom']  # (MODIFIÉ)
                            libelle = f"Dividende réinvesti - {selected_source_name}" if is_reinvesting_current_state else f"Dividende - {selected_source_name}"
                        elif type_val == 'versement':
                            libelle = 'Versement'
                        elif type_val == 'retrait':
                            libelle = 'Retrait'
                        elif type_val == 'frais':
                            selected_source_name = chargeable_positions_options.get(fees_asset_select.value)[
                                'nom'] if fees_asset_select and fees_asset_select.value else 'Génériques'  # (NOUVEAU AMÉLIORATION)
                            libelle = f"Frais de gestion - {selected_source_name} (parts)" if is_fees_in_parts_current_state else f"Frais de gestion {date_val.year}"

                    t_final = None  # Initialiser pour pouvoir l'utiliser après les if/else

                    if type_val == 'dividende':
                        source_pos_for_tx = session.get(Position, dividend_source_select.value)

                        if is_reinvesting_current_state:
                            price_at_reinvestment = source_pos_for_tx.cours_actuel or 0
                            if price_at_reinvestment == 0:
                                ui.notify(
                                    f"Impossible de réinvestir : cours actuel de {source_pos_for_tx.nom} est de 0. Veuillez le mettre à jour.",
                                    type='negative')
                                session.rollback()
                                return

                            montant_total_dividende_final = parts_reinvesties * price_at_reinvestment

                            old_qty = source_pos_for_tx.quantite or 0
                            old_pru = source_pos_for_tx.prix_moyen or 0
                            new_qty = old_qty + parts_reinvesties
                            if old_qty == 0:
                                new_pru = price_at_reinvestment
                            else:
                                new_pru = ((old_qty * old_pru) + (parts_reinvesties * price_at_reinvestment)) / new_qty

                            source_pos_for_tx.quantite = new_qty
                            source_pos_for_tx.prix_moyen = new_pru

                            t_final = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='dividende',
                                montant=montant_total_dividende_final,
                                libelle=libelle,
                                nom_titre=source_pos_for_tx.nom,
                                ticker=source_pos_for_tx.ticker,
                                code=source_pos_for_tx.code,
                                categorie=source_pos_for_tx.categorie,
                                quantite=parts_reinvesties,
                                prix_unitaire=price_at_reinvestment,
                            )
                            session.add(t_final)

                        else:  # Dividende payé en cash
                            t_final = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='dividende',
                                montant=montant_val_for_tx,
                                libelle=libelle,
                                nom_titre=source_pos_for_tx.nom,
                                ticker=source_pos_for_tx.ticker,
                                code=source_pos_for_tx.code,
                                categorie=source_pos_for_tx.categorie,
                                quantite=None,
                                prix_unitaire=None,
                            )
                            session.add(t_final)
                            session.flush()

                            if is_av_per:
                                update_fonds_euro(fonds_euro_select.value, type_val, montant_val_for_tx)
                            else:
                                ajuster_cash(session, portefeuille_id, impact_cash(type_val, montant_val_for_tx))

                    # (NOUVEAU AMÉLIORATION) Logique de création pour les frais
                    elif type_val == 'frais':
                        if is_fees_in_parts_current_state:
                            source_pos_for_fees = session.get(Position, fees_asset_select.value)
                            price_at_deduction = source_pos_for_fees.cours_actuel or 0
                            if price_at_deduction == 0:
                                ui.notify(
                                    f"Impossible de prélever les frais : cours actuel de {source_pos_for_fees.nom} est de 0. Veuillez le mettre à jour.",
                                    type='negative')
                                session.rollback()
                                return

                            # Valeur monétaire des parts prélevées
                            montant_frais_final = parts_a_prelever_frais * price_at_deduction

                            # Réduire la quantité de la position. Le PRU reste inchangé.
                            source_pos_for_fees.quantite -= parts_a_prelever_frais

                            t_final = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='frais',
                                montant=montant_frais_final,  # Valeur monétaire des frais en parts
                                libelle=libelle,
                                nom_titre=source_pos_for_fees.nom,
                                ticker=source_pos_for_fees.ticker,
                                code=source_pos_for_fees.code,
                                categorie=source_pos_for_fees.categorie,
                                quantite=parts_a_prelever_frais,  # Quantité de parts prélevées
                                prix_unitaire=price_at_deduction,  # Prix des parts au moment du prélèvement
                            )
                            session.add(t_final)
                        else:  # Frais en euros (comportement par défaut)
                            t_final = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='frais',
                                montant=montant_val_for_tx,
                                libelle=libelle,
                                # Si c'est AV/PER et que le prélèvement est sur un Fonds €, on le trace
                                nom_titre=fonds_euros_dict.get(fonds_euro_select.value) if (
                                            is_av_per and fonds_euro_select and fonds_euro_select.value) else None,
                                categorie='Fonds Euro' if (
                                            is_av_per and fonds_euro_select and fonds_euro_select.value) else None,
                                quantite=montant_val_for_tx if (
                                            is_av_per and fonds_euro_select and fonds_euro_select.value) else None,
                                # La quantité est le montant pour un Fonds Euro
                                prix_unitaire=1.0 if (
                                            is_av_per and fonds_euro_select and fonds_euro_select.value) else None,
                            )
                            session.add(t_final)
                            session.flush()  # Nécessaire pour les impacts cash/fonds euro

                            if is_av_per:
                                update_fonds_euro(fonds_euro_select.value, type_val, montant_val_for_tx)
                            else:
                                ajuster_cash(session, portefeuille_id, impact_cash(type_val, montant_val_for_tx))

                    # Autres types de transactions (versement, retrait, interets)
                    else:
                        t_final = Transaction(
                            portefeuille_id=portefeuille_id,
                            date_operation=date_val,
                            type_operation=type_val,
                            montant=montant_val_for_tx,
                            libelle=libelle,
                        )
                        if is_av_per and fonds_euro_select and fonds_euro_select.value:
                            target_fe_pos = session.get(Position, fonds_euro_select.value)
                            if target_fe_pos:
                                t_final.nom_titre = target_fe_pos.nom
                                t_final.categorie = 'Fonds Euro'
                                t_final.quantite = montant_val_for_tx
                                t_final.prix_unitaire = 1.0
                        session.add(t_final)
                        session.flush()

                        if is_av_per:
                            update_fonds_euro(fonds_euro_select.value, type_val, montant_val_for_tx)
                        else:
                            ajuster_cash(session, portefeuille_id, impact_cash(type_val, montant_val_for_tx))

                    session.commit()

                ui.notify('Transaction ajoutée', type='positive')
                dialog.close()
                refresh()

            ui.button('Enregistrer', on_click=save).props('unelevated') \
                .classes('bg-blue-600 text-white')

    dialog.open()


def _confirm_delete_transaction(transaction_id, libelle, refresh):
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

                portefeuille = session.get(Portefeuille, t.portefeuille_id)
                is_av_per_for_tx = portefeuille.type in ['Assurance-Vie', 'AV', 'PER', 'Assurance Vie']
                fonds_euro_id_affected = None
                if is_av_per_for_tx and t.nom_titre and t.categorie == 'Fonds Euro' \
                        and t.type_operation in ['versement', 'retrait', 'interets', 'frais', 'dividende']:
                    fe_pos = session.execute(
                        select(Position).where(
                            Position.portefeuille_id == t.portefeuille_id,
                            Position.nom == t.nom_titre,
                            Position.categorie == 'Fonds Euro'
                        )
                    ).scalar_one_or_none()
                    if fe_pos:
                        fonds_euro_id_affected = fe_pos.id

                # Gérer la suppression d'un dividende réinvesti en parts
                if (t.type_operation == 'dividende' and t.quantite is not None and t.quantite > 0 and
                        t.prix_unitaire is not None and t.prix_unitaire > 0 and t.nom_titre):
                    source_pos = session.execute(
                        select(Position).where(
                            Position.portefeuille_id == t.portefeuille_id,
                            Position.nom == t.nom_titre,
                        )
                    ).scalar_one_or_none()

                    if source_pos:
                        parts_a_retirer = t.quantite

                        old_qty = source_pos.quantite or 0
                        old_pru = source_pos.prix_moyen or 0

                        if old_qty <= parts_a_retirer:
                            source_pos.quantite = 0
                            source_pos.prix_moyen = 0
                        else:
                            new_qty = old_qty - parts_a_retirer
                            if new_qty > 0:
                                new_pru = ((old_qty * old_pru) - (parts_a_retirer * t.prix_unitaire)) / new_qty
                                source_pos.quantite = new_qty
                                source_pos.prix_moyen = new_pru
                            else:
                                source_pos.quantite = 0
                                source_pos.prix_moyen = 0

                # (NOUVEAU AMÉLIORATION) Gérer la suppression d'un frais en parts
                elif (t.type_operation == 'frais' and t.quantite is not None and t.quantite > 0 and
                      t.prix_unitaire is not None and t.prix_unitaire > 0 and t.nom_titre):
                    source_pos = session.execute(
                        select(Position).where(
                            Position.portefeuille_id == t.portefeuille_id,
                            Position.nom == t.nom_titre,
                        )
                    ).scalar_one_or_none()

                    if source_pos:
                        parts_a_rajouter = t.quantite
                        # Quand on supprime un frais en parts, on rajoute les parts.
                        # Le PRU des parts existantes ne change pas.
                        source_pos.quantite += parts_a_rajouter
                        # Le prix moyen n'est pas modifié ici, car la déduction/ajout de frais
                        # n'est pas censée modifier le coût moyen d'acquisition des parts restantes/ajoutées.

                else:  # Gestion des autres types de transactions (y compris dividende cash et frais cash)
                    # Annuler l'impact des transactions enfants (frais liés)
                    for child in list(t.children):
                        if child.type_operation == 'frais':
                            if is_av_per_for_tx and fonds_euro_id_affected:
                                fe = session.get(Position, fonds_euro_id_affected)
                                if fe: fe.quantite += child.montant
                            else:
                                impact_inv = -impact_cash(child.type_operation, child.montant)
                                ajuster_cash(session, child.portefeuille_id, impact_inv)
                            session.delete(child)

                    # Annuler l'impact de la transaction principale sur le cash/Fonds Euro
                    if is_av_per_for_tx and fonds_euro_id_affected:
                        fe = session.get(Position, fonds_euro_id_affected)
                        if fe:
                            if t.type_operation in ['versement', 'dividende', 'interets']:
                                fe.quantite -= t.montant
                            elif t.type_operation in ['retrait', 'frais']:
                                fe.quantite += t.montant
                    else:
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