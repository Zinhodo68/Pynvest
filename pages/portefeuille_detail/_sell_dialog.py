"""Dialogue de vente d'un titre détenu."""
import asyncio
from datetime import date, datetime
from nicegui import ui
from sqlalchemy import select

from database.db import get_session
from database.models import Position, Transaction, Portefeuille
from utils.formatters import format_money, format_percent, get_perf_color
from services.market_data import (
    get_current_price_with_currency,
    get_currency_rate,
    get_price_at_date_with_currency,
)
from pages.portefeuille_detail._cash_helpers import impact_cash, ajuster_cash
from services.labels import get_display_name


def open_sell_dialog(portefeuille_id, c, refresh, refresh_chart=None):
    """Dialogue de vente d'une position détenue."""
    # ✅ Capture du contexte client utilisateur d'origine (IHM)
    client = ui.context.client

    with get_session() as session:
        portefeuille = session.get(Portefeuille, portefeuille_id)
        if not portefeuille:
            ui.notify("Portefeuille introuvable", type='negative')
            return

        positions = session.execute(
            select(Position).where(
                Position.portefeuille_id == portefeuille_id,
                Position.quantite > 0,
                ~Position.categorie.in_(['Cash', 'Fonds €', 'Fonds Euro']),
            ).order_by(Position.nom)
        ).scalars().all()
        positions_data = [p.to_dict() for p in positions]

        fonds_euro_positions = []
        if portefeuille.type in ['Assurance-Vie', 'PER']:
            fonds_euro_positions = session.execute(
                select(Position).where(
                    Position.portefeuille_id == portefeuille_id,
                    Position.categorie.in_(['Fonds €', 'Fonds Euro']),
                    Position.quantite > 0,
                ).order_by(Position.nom)
            ).scalars().all()

        # Snapshot du type portefeuille hors session
        portefeuille_type = portefeuille.type

    if not positions_data:
        ui.notify("Aucune position à vendre dans ce portefeuille", type='warning')
        return

    # Pré-calcul des noms d'affichage pour chaque position
    for p in positions_data:
        p['display_name'] = get_display_name(
            ticker=p.get('ticker'),
            code=p.get('code'),
            fallback=p['nom']
        )

    # Snapshot des fonds euro hors session
    fonds_euro_positions_data = [
        {
            'id': f.id,
            'nom': f.nom,
            'quantite': f.quantite,
            'prix_moyen': f.prix_moyen,
            'categorie': f.categorie,
        }
        for f in fonds_euro_positions
    ]

    state = {
        'selected_pos': None,
        'selected_fonds_euro_id': None
    }

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-3').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]}; '
            f'min-width: 600px; max-width: 700px;'
    ):
        ui.label('💹 Vendre un titre').classes('text-xl font-bold').style(
            f'color: {c["text_primary"]}'
        )

        ui.label('Position à vendre').classes('text-sm font-medium mt-2').style(
            f'color: {c["text_secondary"]}'
        )

        pos_options = {
            p['id']: f"{p['display_name']} ({p['quantite']:g} parts à {p['prix_moyen']:.2f}€)"
            for p in positions_data
        }

        form_container = ui.column().classes('w-full gap-3')
        form_container.set_visibility(False)

        def on_position_change(e):
            pos_id = e.value
            if not pos_id:
                form_container.set_visibility(False)
                return
            pos = next((p for p in positions_data if p['id'] == pos_id), None)
            if pos:
                state['selected_pos'] = pos
                _render_sell_form(pos)
                form_container.set_visibility(True)

        position_select = ui.select(
            pos_options,
            label='Sélectionnez la position',
            on_change=on_position_change,
        ).classes('w-full')

        def _render_sell_form(pos):
            form_container.clear()
            updating = {'value': False}

            with form_container:
                # ── Récap de la position ──
                with ui.card().classes('w-full p-4 rounded-lg').style(
                        f'background-color: {c["card_border"]}30; '
                        f'border: 1px solid {c["card_border"]};'
                ):
                    with ui.row().classes('w-full items-center justify-between'):
                        with ui.column().classes('gap-0'):
                            ui.label(pos['display_name']).classes(
                                'text-base font-bold'
                            ).style(f'color: {c["text_primary"]}')
                            sub = (
                                f'{pos.get("ticker") or pos.get("code") or ""} • '
                                f'{pos.get("categorie", "")}'
                            )
                            ui.label(sub).classes('text-xs').style(
                                f'color: {c["text_secondary"]}'
                            )

                    with ui.row().classes('w-full gap-4 mt-3'):
                        with ui.column().classes('gap-0').style('flex: 1;'):
                            ui.label('QUANTITÉ DÉTENUE').classes(
                                'text-xs font-semibold tracking-wider'
                            ).style(f'color: {c["text_secondary"]}')
                            ui.label(f'{pos["quantite"]:g}').classes(
                                'text-base font-bold'
                            ).style(f'color: {c["text_primary"]}')

                        with ui.column().classes('gap-0').style('flex: 1;'):
                            ui.label('PRU').classes(
                                'text-xs font-semibold tracking-wider'
                            ).style(f'color: {c["text_secondary"]}')
                            ui.label(format_money(pos['prix_moyen'], decimals=2)) \
                                .classes('text-base font-bold').style(
                                f'color: {c["text_primary"]}'
                            )

                        with ui.column().classes('gap-0').style('flex: 1;'):
                            ui.label('COURS ACTUEL').classes(
                                'text-xs font-semibold tracking-wider'
                            ).style(f'color: {c["text_secondary"]}')
                            ui.label(format_money(pos['cours_actuel'] or 0, decimals=2)) \
                                .classes('text-base font-bold').style(
                                f'color: {c["text_primary"]}')

                # ── Source du cours ──
                if pos.get('ticker'):
                    source = 'yahoo'
                    symbol_or_url = pos['ticker']
                elif pos.get('code'):
                    source = 'boursorama'
                    symbol_or_url = pos['code']
                else:
                    source = 'manual'
                    symbol_or_url = None

                # Date
                date_today_fr = date.today().strftime('%d/%m/%Y')
                with ui.input("Date de vente", value=date_today_fr).classes('w-full') \
                        .props('mask="##/##/####" placeholder="JJ/MM/AAAA" onfocus="this.select()"') as date_input:
                    with ui.menu().props('no-parent-event') as menu:
                        date_picker = ui.date().bind_value(date_input).props(
                            'mask="DD/MM/YYYY"'
                        )
                        with date_picker:
                            with ui.row().classes('justify-end'):
                                ui.button('Fermer', on_click=menu.close).props('flat')
                    with date_input.add_slot('append'):
                        ui.icon('edit_calendar').on('click', menu.open).classes(
                            'cursor-pointer'
                        )

                cours_initial = pos['cours_actuel'] or pos['prix_moyen']
                prix_input = ui.number(
                    'Prix de vente unitaire (€) *',
                    value=cours_initial,
                    format='%.4f', min=0
                ).classes('w-full').props('onfocus="this.select()"')

                price_info_label = ui.label('').classes('text-xs italic px-2').style(
                    f'color: {c["text_secondary"]}; min-height: 16px;'
                )

                price_state = {
                    'manually_modified': False,
                    'last_auto_value': cours_initial,
                }

                if source != 'manual':
                    price_info_label.text = (
                        f"💹 Cours actuel du marché : {cours_initial:.4f} €"
                    )
                else:
                    price_info_label.text = (
                        "ℹ️ Position manuelle : pas d'auto-remplissage du cours"
                    )

                # ✅ Sécurisation de l'IHM via le contexte client
                async def update_price_for_date():
                    if price_state['manually_modified']:
                        return
                    if source == 'manual':
                        return
                    try:
                        target_date = datetime.strptime(
                            date_input.value, '%d/%m/%Y'
                        ).date()
                    except (ValueError, TypeError):
                        return

                    if target_date == date.today():
                        updating['value'] = True
                        with client:
                            prix_input.value = cours_initial
                            prix_input.run_method('select')  # <-- Ajoutez ceci
                            price_state['last_auto_value'] = cours_initial
                        updating['value'] = False
                        with client:
                            price_info_label.text = (
                                f"💹 Cours actuel du marché : {cours_initial:.4f} €"
                            )
                        update_montant_from_qte()
                        return

                    with client:
                        price_info_label.text = '⏳ Récupération du cours historique...'

                    try:
                        info = await asyncio.to_thread(
                            get_price_at_date_with_currency,
                            symbol_or_url, source, target_date
                        )

                        if info['price'] is not None:
                            price_eur = info['price']
                            if info.get('currency') and info['currency'] != 'EUR':
                                rate = await asyncio.to_thread(
                                    get_currency_rate, info['currency'], 'EUR'
                                )
                                if rate:
                                    price_eur = info['price'] * rate

                            updating['value'] = True
                            with client:
                                prix_input.value = round(price_eur, 4)
                                prix_input.run_method('select')  # <-- Ajoutez ceci
                                price_state['last_auto_value'] = price_eur
                            updating['value'] = False
                            with client:
                                price_info_label.text = (
                                    f"💹 Cours du marché au "
                                    f"{target_date.strftime('%d/%m/%Y')} : "
                                    f"{price_eur:.4f} €"
                                )
                            update_montant_from_qte()
                        else:
                            with client:
                                price_info_label.text = (
                                    "⚠️ Cours historique non disponible "
                                    "(saisie manuelle requise)"
                                )
                    except Exception as e:
                        with client:
                            price_info_label.text = f"⚠️ Erreur : {e}"

                def on_price_change(e):
                    if updating['value']:
                        return
                    try:
                        new_value = float(prix_input.value or 0)
                        if abs(new_value - price_state['last_auto_value']) > 0.0001:
                            price_state['manually_modified'] = True
                            price_info_label.text = "✏️ Prix modifié manuellement"
                    except (TypeError, ValueError):
                        pass
                    update_montant_from_qte()

                def on_date_change(e):
                    price_state['manually_modified'] = False
                    asyncio.create_task(update_price_for_date())

                frais_input = ui.number(
                    'Frais de courtage (€)', value=0, format='%.2f', min=0
                ).classes('w-full').props('onfocus="this.select()"')

                ui.label("Saisissez l'un OU l'autre").classes('text-xs italic mt-2') \
                    .style(f'color: {c["text_secondary"]}')

                with ui.row().classes('w-full gap-3'):
                    quantite_input = ui.number(
                        '🔢 Quantité à vendre',
                        value=pos['quantite'],
                        format='%.4f', min=0, step=0.0001,
                        max=pos['quantite']
                    ).classes('flex-1').props('onfocus="this.select()"')

                    montant_input = ui.number(
                        '💶 Montant (€)',
                        value=pos['quantite'] * cours_initial,
                        format='%.2f', min=0
                    ).classes('flex-1').props('onfocus="this.select()"')

                if portefeuille_type in ['Assurance-Vie', 'PER']:
                    ui.label('Destination du produit de la vente').classes(
                        'text-sm font-medium mt-2'
                    ).style(f'color: {c["text_secondary"]}')
                    fonds_euro_options = {
                        f['id']: f"{f['nom']} ({format_money(f['quantite'] * f['prix_moyen'], decimals=2)})"
                        for f in fonds_euro_positions_data
                    }
                    if fonds_euro_options:
                        fonds_euro_select = ui.select(
                            fonds_euro_options,
                            label='Sélectionnez un Fonds Euro de destination *',
                            on_change=lambda e: state.update(selected_fonds_euro_id=e.value)
                        ).classes('w-full')
                        if fonds_euro_positions_data:
                            fonds_euro_select.value = fonds_euro_positions_data[0]['id']
                            state['selected_fonds_euro_id'] = fonds_euro_positions_data[0]['id']
                    else:
                        ui.label(
                            "⚠️ Aucun Fonds Euro actif pour cet Assurance-Vie/PER."
                        ).classes('text-xs text-red-500')

                with ui.row().classes('w-full justify-end'):
                    def sell_all():
                        updating['value'] = True
                        quantite_input.value = pos['quantite']
                        montant_input.value = round(
                            pos['quantite'] * float(prix_input.value or 0), 2
                        )
                        updating['value'] = False
                        update_summary()

                    ui.button('🎯 Tout vendre', on_click=sell_all) \
                        .props('flat dense').style(
                        f'color: {c["text_secondary"]}; font-size: 0.75rem;'
                    )

                def update_montant_from_qte():
                    if updating['value']:
                        return
                    try:
                        q = float(quantite_input.value or 0)
                        p = float(prix_input.value or 0)
                        updating['value'] = True
                        montant_input.value = round(q * p, 2)
                        updating['value'] = False
                        update_summary()
                    except (TypeError, ValueError):
                        pass

                def update_qte_from_montant():
                    if updating['value']:
                        return
                    try:
                        m = float(montant_input.value or 0)
                        p = float(prix_input.value or 0)
                        if p > 0:
                            new_qte = round(m / p, 4)
                            new_qte = min(new_qte, pos['quantite'])
                            updating['value'] = True
                            quantite_input.value = new_qte
                            updating['value'] = False
                        update_summary()
                    except (TypeError, ValueError):
                        pass

                quantite_input.on('update:model-value',
                                  lambda _: update_montant_from_qte())
                montant_input.on('update:model-value',
                                 lambda _: update_qte_from_montant())
                prix_input.on('update:model-value', on_price_change)
                frais_input.on('update:model-value', lambda _: update_summary())
                date_picker.on('update:model-value', on_date_change)
                date_input.on('blur', on_date_change)

                summary_label = ui.label().classes(
                    'text-sm font-medium px-3 py-2 rounded-lg whitespace-pre-line'
                ).style(
                    f'background-color: {c["card_border"]}; color: {c["text_primary"]};'
                )

                def update_summary():
                    try:
                        q = float(quantite_input.value or 0)
                        p = float(prix_input.value or 0)
                        f = float(frais_input.value or 0)
                        pru = pos['prix_moyen']
                        m = round(q * p, 2)
                        montant_net = m - f
                        cout_revient = q * pru
                        plus_value = montant_net - cout_revient
                        pv_pct = (
                            plus_value / cout_revient * 100
                        ) if cout_revient > 0 else 0

                        pv_emoji = '✅' if plus_value >= 0 else '❌'
                        warning = ''
                        if q > pos['quantite']:
                            warning = (
                                f'\n⚠️ Quantité trop élevée '
                                f'(max : {pos["quantite"]:g})'
                            )
                        if q == pos['quantite']:
                            warning += '\n💡 Vente totale → la position sera supprimée'

                        summary_label.text = (
                            f'📦 {q:g} × {format_money(p, decimals=2)} '
                            f'= {format_money(m, decimals=2)}\n'
                            f'💸 - {format_money(f, decimals=2)} de frais\n'
                            f'💰 Net encaissé : {format_money(montant_net, decimals=2)}\n'
                            f'📊 Coût de revient : {format_money(cout_revient, decimals=2)} '
                            f'({q:g} × {format_money(pru, decimals=2)})\n'
                            f'{"✅" if plus_value >= 0 else "❌"} +/- value réalisée : '
                            f'{format_money(plus_value, decimals=2)} '
                            f'({format_percent(pv_pct)})'
                            f'{warning}'
                        )
                        if (portefeuille_type in ['Assurance-Vie', 'PER']
                                and not state['selected_fonds_euro_id']
                                and (q > 0 or f > 0)):
                            summary_label.text += (
                                "\n\n🚨 Choisissez un Fonds Euro de destination !"
                            )
                    except (TypeError, ValueError):
                        summary_label.text = '💡 Saisissez quantité ou montant'

                update_summary()

                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('Annuler', on_click=dialog.close).props('flat')

                    async def save_vente():
                        try:
                            date_val = datetime.strptime(
                                date_input.value, '%d/%m/%Y'
                            ).date()
                        except (ValueError, TypeError):
                            ui.notify('Date invalide', type='negative')
                            return
                        if not prix_input.value or prix_input.value <= 0:
                            ui.notify('Prix invalide', type='negative')
                            return
                        if not quantite_input.value or quantite_input.value <= 0:
                            ui.notify('Quantité invalide', type='negative')
                            return

                        q = float(quantite_input.value)
                        p_unit = float(prix_input.value)
                        frais = float(frais_input.value or 0)

                        if q > pos['quantite']:
                            ui.notify(
                                f'Quantité trop élevée (max : {pos["quantite"]:g})',
                                type='negative'
                            )
                            return

                        if (portefeuille_type in ['Assurance-Vie', 'PER']
                                and not state['selected_fonds_euro_id']):
                            ui.notify(
                                'Veuillez sélectionner un Fonds Euro de destination.',
                                type='negative'
                            )
                            return

                        montant_brut = q * p_unit
                        montant_net = montant_brut - frais

                        # ── Phase 1 : commit BDD (rapide) ──
                        need_backfill = False

                        with get_session() as session:
                            position = session.get(Position, pos['id'])
                            if not position:
                                ui.notify('Position introuvable', type='negative')
                                return

                            new_qty = (position.quantite or 0) - q
                            if new_qty <= 0.0001:
                                session.delete(position)
                            else:
                                position.quantite = new_qty

                            tx_vente = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='vente',
                                montant=montant_brut,
                                libelle=f'Vente {q:g} × {pos["nom"][:30]}',
                                ticker=pos.get('ticker'),
                                code=pos.get('code'),
                                nom_titre=pos['nom'],
                                categorie=pos.get('categorie'),
                                quantite=q,
                                prix_unitaire=p_unit,
                            )
                            session.add(tx_vente)
                            session.flush()

                            if portefeuille_type in ['Assurance-Vie', 'PER']:
                                fonds_euro_cible = session.get(
                                    Position, state['selected_fonds_euro_id']
                                )
                                if not fonds_euro_cible:
                                    ui.notify(
                                        "Fonds Euro de destination introuvable",
                                        type='negative'
                                    )
                                    session.rollback()
                                    return

                                tx_versement_fonds_euro = Transaction(
                                    portefeuille_id=portefeuille_id,
                                    date_operation=date_val,
                                    type_operation='versement',
                                    montant=montant_brut,
                                    libelle=(
                                        f'Arbitrage IN (produit de vente {pos["nom"][:20]}) '
                                        f'vers {fonds_euro_cible.nom[:20]}'
                                    ),
                                    nom_titre=fonds_euro_cible.nom,
                                    categorie=fonds_euro_cible.categorie,
                                    quantite=(
                                        montant_brut / fonds_euro_cible.prix_moyen
                                        if fonds_euro_cible.prix_moyen > 0 else 0
                                    ),
                                    prix_unitaire=fonds_euro_cible.prix_moyen,
                                    parent_transaction_id=tx_vente.id,
                                )
                                session.add(tx_versement_fonds_euro)
                                fonds_euro_cible.quantite += (
                                    montant_brut / fonds_euro_cible.prix_moyen
                                    if fonds_euro_cible.prix_moyen > 0 else 0
                                )

                                if frais > 0:
                                    tx_frais_fonds_euro = Transaction(
                                        portefeuille_id=portefeuille_id,
                                        date_operation=date_val,
                                        type_operation='frais',
                                        montant=frais,
                                        libelle=(
                                            f'Frais vente {pos["nom"][:20]} '
                                            f'(déduits de {fonds_euro_cible.nom[:20]})'
                                        ),
                                        nom_titre=fonds_euro_cible.nom,
                                        categorie=fonds_euro_cible.categorie,
                                        quantite=(
                                            frais / fonds_euro_cible.prix_moyen
                                            if fonds_euro_cible.prix_moyen > 0 else 0
                                        ),
                                        prix_unitaire=fonds_euro_cible.prix_moyen,
                                        parent_transaction_id=tx_vente.id,
                                    )
                                    session.add(tx_frais_fonds_euro)
                                    fonds_euro_cible.quantite -= (
                                        frais / fonds_euro_cible.prix_moyen
                                        if fonds_euro_cible.prix_moyen > 0 else 0
                                    )

                            else:
                                ajuster_cash(
                                    session, portefeuille_id,
                                    impact_cash('vente', montant_brut)
                                )
                                if frais > 0:
                                    tx_frais = Transaction(
                                        portefeuille_id=portefeuille_id,
                                        date_operation=date_val,
                                        type_operation='frais',
                                        montant=frais,
                                        libelle=f'Frais vente - {pos["nom"][:30]}',
                                        parent_transaction_id=tx_vente.id,
                                    )
                                    session.add(tx_frais)
                                    ajuster_cash(
                                        session, portefeuille_id,
                                        impact_cash('frais', frais)
                                    )

                            session.commit()
                            need_backfill = bool(pos.get('ticker'))

                        # ── Phase 2 : feedback immédiat ──
                        cout = q * pos['prix_moyen']
                        pv = montant_net - cout
                        ui.notify(
                            f'{"✅" if pv >= 0 else "❌"} Vente effectuée. '
                            f'+/- value : {format_money(pv, decimals=2)}',
                            type='positive' if pv >= 0 else 'warning',
                            timeout=4000
                        )
                        dialog.close()
                        refresh()

                        # ── Phase 3 : backfill en arrière-plan (sécurisé avec le client) ──
                        asyncio.create_task(
                            _run_backfill_async(
                                portefeuille_id=portefeuille_id,
                                refresh=refresh,
                                client=client,
                                need_cours=need_backfill,
                                refresh_chart=refresh_chart,
                            )
                        )

                    ui.button("💹 Confirmer la vente", on_click=save_vente) \
                        .props('unelevated').classes('bg-pink-600 text-white')

    dialog.open()


# ✅ Ajout du paramètre 'client' pour l'exécution threadée asynchrone sécurisée
async def _run_backfill_async(
    portefeuille_id: int,
    refresh,
    client,
    need_cours: bool = True,
    refresh_chart=None,
):
    """Exécute le backfill dans un thread séparé, puis rafraîchit l'UI sans erreur de slot."""
    from services.backfill import backfill_cours_historique, backfill_valorisations

    # ✅ On entre dans le contexte du client utilisateur pour afficher la notification de départ
    with client:
        notif = ui.notification(
            "📈 Mise à jour de l'historique en cours...",
            type='ongoing',
            spinner=True,
            timeout=None,
        )

    try:
        # backfill_cours uniquement si la position avait un ticker Yahoo
        if need_cours:
            await asyncio.to_thread(backfill_cours_historique, portefeuille_id)

        await asyncio.to_thread(backfill_valorisations, portefeuille_id)

        # ✅ Une fois terminé, on ré-entre dans le contexte client pour modifier l'IHM
        with client:
            notif.dismiss()
            ui.notify('📈 Historique mis à jour', type='positive', timeout=3000)

            # ✅ Ne pas reconstruire toute la page si on peut éviter
            if refresh_chart:
                refresh_chart()
            else:
                refresh()

    except Exception as e:
        # ✅ Gestion des erreurs sous contexte client
        with client:
            notif.dismiss()
            ui.notify(
                f'⚠️ Mise à jour historique échouée : {e}',
                type='warning',
                timeout=5000,
            )
        print(f'⚠️ Backfill async échoué pour portefeuille #{portefeuille_id}: {e}')