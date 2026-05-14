"""Dialogue de vente d'un titre détenu."""
import asyncio
from datetime import date, datetime
from nicegui import ui
from sqlalchemy import select

from database.db import get_session
from database.models import Position, Transaction, Portefeuille  # Import de Portefeuille
from utils.formatters import format_money, format_percent, get_perf_color
from services.market_data import (
    get_current_price_with_currency,
    get_currency_rate,
    get_price_at_date_with_currency,
)
from pages.portefeuille_detail._cash_helpers import impact_cash, ajuster_cash


def open_sell_dialog(portefeuille_id, c, refresh):
    """Dialogue de vente d'une position détenue."""

    with get_session() as session:
        portefeuille = session.get(Portefeuille, portefeuille_id)  # Récupérer le portefeuille
        if not portefeuille:
            ui.notify("Portefeuille introuvable", type='negative')
            return

        # Récupérer toutes les positions vendables (hors Cash)
        positions = session.execute(
            select(Position).where(
                Position.portefeuille_id == portefeuille_id,
                Position.quantite > 0,
                ~Position.categorie.in_(['Cash', 'Fonds €', 'Fonds Euro']),
            ).order_by(Position.nom)
        ).scalars().all()
        positions_data = [p.to_dict() for p in positions]

        # Récupérer les Fonds Euro si c'est une Assurance-Vie ou un PER
        fonds_euro_positions = []
        if portefeuille.type in ['Assurance-Vie', 'PER']:  # <-- MODIFIÉ pour inclure 'PER'
            fonds_euro_positions = session.execute(
                select(Position).where(
                    Position.portefeuille_id == portefeuille_id,
                    Position.categorie.in_(['Fonds €', 'Fonds Euro']),
                    Position.quantite > 0,
                ).order_by(Position.nom)
            ).scalars().all()

    if not positions_data:
        ui.notify("Aucune position à vendre dans ce portefeuille",
                  type='warning')
        return

    state = {
        'selected_pos': None,
        'selected_fonds_euro_id': None  # Pour stocker le choix du Fonds Euro
    }

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-3').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]}; '
            f'min-width: 600px; max-width: 700px;'
    ):
        ui.label('💹 Vendre un titre').classes('text-xl font-bold').style(
            f'color: {c["text_primary"]}'
        )

        # ── Sélection de la position ──
        ui.label('Position à vendre').classes('text-sm font-medium mt-2').style(
            f'color: {c["text_secondary"]}'
        )

        pos_options = {
            p['id']: f"{p['nom']} ({p['quantite']:g} parts à {p['prix_moyen']:.2f}€)"
            for p in positions_data
        }

        # Container du formulaire de vente (caché au départ)
        form_container = ui.column().classes('w-full gap-3')
        form_container.set_visibility(False)

        def on_position_change(e):
            """Charge le formulaire pour la position sélectionnée."""
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
                            ui.label(pos['nom']).classes('text-base font-bold').style(
                                f'color: {c["text_primary"]}'
                            )
                            sub = (
                                f'{pos.get("ticker") or pos.get("code") or ""} • '
                                f'{pos.get("categorie", "")}'
                            )
                            ui.label(sub).classes('text-xs').style(
                                f'color: {c["text_secondary"]}'
                            )

                    # Mini KPIs
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
                            ui.label(format_money(pos['cours_actuel'] or 0,
                                                  decimals=2)) \
                                .classes('text-base font-bold').style(
                                f'color: {c["text_primary"]}'
                            )

                # ── Formulaire ──
                # 🆕 Détecter la source du cours pour cette position
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
                        .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input:
                    with ui.menu().props('no-parent-event') as menu:
                        # 🆕 Référence au date picker pour écouter ses changements
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

                # Prix de vente (pré-rempli avec le cours actuel)
                cours_initial = pos['cours_actuel'] or pos['prix_moyen']
                prix_input = ui.number(
                    'Prix de vente unitaire (€) *',
                    value=cours_initial,
                    format='%.4f', min=0
                ).classes('w-full')

                # 🆕 Indicateur de la source du prix
                price_info_label = ui.label('').classes('text-xs italic px-2').style(
                    f'color: {c["text_secondary"]}; min-height: 16px;'
                )

                # 🆕 Flag pour détecter les modifications manuelles
                price_state = {
                    'manually_modified': False,
                    'last_auto_value': cours_initial,
                }

                # Initialiser le label
                if source != 'manual':
                    price_info_label.text = (
                        f"💹 Cours actuel du marché : {cours_initial:.4f} €"
                    )
                else:
                    price_info_label.text = (
                        f"ℹ️ Position manuelle : pas d'auto-remplissage du cours"
                    )

                # 🆕 Fonction d'auto-update du prix selon la date
                async def update_price_for_date():
                    """Récupère le cours historique pour la date sélectionnée."""
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

                    # Si c'est aujourd'hui → on utilise le cours_actuel de la position
                    if target_date == date.today():
                        updating['value'] = True
                        prix_input.value = cours_initial
                        price_state['last_auto_value'] = cours_initial
                        updating['value'] = False
                        price_info_label.text = (
                            f"💹 Cours actuel du marché : {cours_initial:.4f} €"
                        )
                        update_montant_from_qte()
                        return

                    # Sinon : récupération historique
                    price_info_label.text = '⏳ Récupération du cours historique...'

                    try:
                        info = await asyncio.to_thread(
                            get_price_at_date_with_currency,
                            symbol_or_url, source, target_date
                        )

                        if info['price'] is not None:
                            # Conversion en EUR si nécessaire
                            price_eur = info['price']
                            if info.get('currency') and info['currency'] != 'EUR':
                                rate = await asyncio.to_thread(
                                    get_currency_rate,
                                    info['currency'], 'EUR'
                                )
                                if rate:
                                    price_eur = info['price'] * rate

                            updating['value'] = True
                            prix_input.value = round(price_eur, 4)
                            price_state['last_auto_value'] = price_eur
                            updating['value'] = False
                            price_info_label.text = (
                                f"💹 Cours du marché au "
                                f"{target_date.strftime('%d/%m/%Y')} : "
                                f"{price_eur:.4f} €"
                            )
                            update_montant_from_qte()
                        else:
                            price_info_label.text = (
                                "⚠️ Cours historique non disponible "
                                "(saisie manuelle requise)"
                            )
                    except Exception as e:
                        price_info_label.text = f"⚠️ Erreur : {e}"

                # 🆕 Détection de la modification manuelle
                def on_price_change(e):
                    """Détecte si le prix a été modifié à la main."""
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

                # 🆕 Quand la date change → reset flag + recalcul
                def on_date_change(e):
                    """Réinitialise le flag manuel et déclenche la MAJ du prix."""
                    price_state['manually_modified'] = False
                    asyncio.create_task(update_price_for_date())

                # Frais
                frais_input = ui.number(
                    'Frais de courtage (€)', value=0, format='%.2f', min=0
                ).classes('w-full')

                # Quantité / Montant liés
                ui.label("Saisissez l'un OU l'autre").classes('text-xs italic mt-2') \
                    .style(f'color: {c["text_secondary"]}')

                with ui.row().classes('w-full gap-3'):
                    # 🆕 Toutes les catégories autorisent des fractions
                    is_action = False  # Conservé pour compatibilité downstream
                    quantite_input = ui.number(
                        '🔢 Quantité à vendre',
                        value=pos['quantite'],  # Par défaut : tout vendre
                        format='%.4f', min=0, step=0.0001,
                        max=pos['quantite']
                    ).classes('flex-1')

                    montant_input = ui.number(
                        '💶 Montant (€)',
                        value=pos['quantite'] * cours_initial,
                        format='%.2f', min=0
                    ).classes('flex-1')

                # 🆕 Pour les Assurance-Vie/PER, un sélecteur de Fonds Euro
                if portefeuille.type in ['Assurance-Vie', 'PER']:  # <-- MODIFIÉ
                    ui.label('Destination du produit de la vente').classes('text-sm font-medium mt-2').style(
                        f'color: {c["text_secondary"]}'
                    )
                    fonds_euro_options = {
                        f.id: f"{f.nom} ({format_money(f.quantite * f.prix_moyen, decimals=2)})"
                        for f in fonds_euro_positions
                    }
                    if fonds_euro_options:
                        fonds_euro_select = ui.select(
                            fonds_euro_options,
                            label='Sélectionnez un Fonds Euro de destination *',
                            on_change=lambda e: state.update(selected_fonds_euro_id=e.value)
                        ).classes('w-full')
                        # Pré-sélectionner le premier Fonds Euro si disponible
                        if fonds_euro_positions:
                            fonds_euro_select.value = fonds_euro_positions[0].id
                            state['selected_fonds_euro_id'] = fonds_euro_positions[0].id
                    else:
                        ui.label("⚠️ Aucun Fonds Euro actif pour cet Assurance-Vie/PER.").classes(
                            'text-xs text-red-500')  # <-- MODIFIÉ

                # ── Bouton "Tout vendre" ──
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

                # ── Synchronisation ──
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
                    """Recalcule la quantité depuis montant ÷ prix (toujours fractionnaire)."""
                    if updating['value']:
                        return
                    try:
                        m = float(montant_input.value or 0)
                        p = float(prix_input.value or 0)
                        if p > 0:
                            new_qte = round(m / p, 4)
                            new_qte = min(new_qte, pos['quantite'])  # Cap au max détenu
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
                # 🆕 Remplacement : on utilise on_price_change au lieu d'une lambda
                prix_input.on('update:model-value', on_price_change)
                frais_input.on('update:model-value', lambda _: update_summary())

                # 🆕 Écouter les changements de date
                date_picker.on('update:model-value', on_date_change)
                date_input.on('blur', on_date_change)

                # ── Récapitulatif avec +/- value ──
                summary_label = ui.label().classes(
                    'text-sm font-medium px-3 py-2 rounded-lg whitespace-pre-line'
                ).style(
                    f'background-color: {c["card_border"]}; color: {c["text_primary"]};'
                )

                def update_summary():
                    """Affiche le récap en recalculant TOUJOURS depuis quantité × prix."""
                    try:
                        q = float(quantite_input.value or 0)
                        p = float(prix_input.value or 0)
                        f = float(frais_input.value or 0)
                        pru = pos['prix_moyen']

                        # 🆕 Toujours recalculer m depuis q × p
                        m = round(q * p, 2)

                        montant_net = m - f
                        cout_revient = q * pru
                        plus_value = montant_net - cout_revient
                        pv_pct = (plus_value / cout_revient * 100) if cout_revient > 0 else 0

                        pv_emoji = '✅' if plus_value >= 0 else '❌'
                        warning = ''
                        if q > pos['quantite']:
                            warning = (f'\n⚠️ Quantité trop élevée '
                                       f'(max : {pos["quantite"]:g})')
                        if q == pos['quantite']:
                            warning += '\n💡 Vente totale → la position sera supprimée'

                        summary_label.text = (
                            f'📦 {q:g} × {format_money(p, decimals=2)} '
                            f'= {format_money(m, decimals=2)}\n'
                            f'💸 - {format_money(f, decimals=2)} de frais\n'
                            f'💰 Net encaissé : {format_money(montant_net, decimals=2)}\n'
                            f'📊 Coût de revient : {format_money(cout_revient, decimals=2)} '
                            f'({q:g} × {format_money(pru, decimals=2)})\n'
                            f'{pv_emoji} +/- value réalisée : '
                            f'{format_money(plus_value, decimals=2)} '
                            f'({format_percent(pv_pct)})'
                            f'{warning}'
                        )
                        if portefeuille.type in ['Assurance-Vie', 'PER'] and not state['selected_fonds_euro_id'] and (
                                q > 0 or f > 0):
                            summary_label.text += "\n\n🚨 Choisissez un Fonds Euro de destination !"

                    except (TypeError, ValueError):
                        summary_label.text = '💡 Saisissez quantité ou montant'

                update_summary()

                # ── Boutons d'action ──
                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('Annuler', on_click=dialog.close).props('flat')

                    def save_vente():
                        # Validations
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

                        # Vérification quantité
                        if q > pos['quantite']:
                            ui.notify(
                                f'Quantité trop élevée (max : {pos["quantite"]:g})',
                                type='negative'
                            )
                            return



                        # Validation spécifique Assurance-Vie / PER
                        if portefeuille.type in ['Assurance-Vie', 'PER'] and not state[
                            'selected_fonds_euro_id']:
                            ui.notify('Veuillez sélectionner un Fonds Euro de destination.', type='negative')
                            return

                        montant_brut = q * p_unit
                        montant_net = montant_brut - frais

                        with get_session() as session:
                            # Récupération de la position
                            position = session.get(Position, pos['id'])
                            if not position:
                                ui.notify('Position introuvable', type='negative')
                                return

                            # MAJ ou suppression de la position du titre vendu
                            new_qty = (position.quantite or 0) - q
                            if new_qty <= 0.0001:  # Vente totale (tolérance)
                                session.delete(position)
                            else:
                                position.quantite = new_qty
                                # Le PRU reste INCHANGÉ après une vente partielle

                            # 🆕 Transaction enrichie avec les nouveaux champs pour la vente
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

                            # --- GESTION DU FLUX DE TRÉSORERIE DE LA VENTE ---
                            if portefeuille.type in ['Assurance-Vie', 'PER']:
                                # Récupérer le Fonds Euro de destination
                                fonds_euro_cible = session.get(Position, state['selected_fonds_euro_id'])
                                if not fonds_euro_cible:
                                    ui.notify("Fonds Euro de destination introuvable", type='negative')
                                    session.rollback()
                                    return

                                # Créer une transaction de versement dans le Fonds Euro
                                tx_versement_fonds_euro = Transaction(
                                    portefeuille_id=portefeuille_id,
                                    date_operation=date_val,
                                    type_operation='versement',
                                    montant=montant_brut,
                                    libelle=f'Arbitrage IN (produit de vente {pos["nom"][:20]}) vers {fonds_euro_cible.nom[:20]}',
                                    nom_titre=fonds_euro_cible.nom,
                                    categorie=fonds_euro_cible.categorie,
                                    quantite=montant_brut / fonds_euro_cible.prix_moyen if fonds_euro_cible.prix_moyen > 0 else 0,
                                    prix_unitaire=fonds_euro_cible.prix_moyen,
                                    parent_transaction_id=tx_vente.id,
                                )
                                session.add(tx_versement_fonds_euro)

                                # Mettre à jour la position du Fonds Euro directement
                                fonds_euro_cible.quantite += (
                                    montant_brut / fonds_euro_cible.prix_moyen if fonds_euro_cible.prix_moyen > 0 else 0)

                                # Frais liés (si > 0) : impacts le Fonds Euro, pas le cash global
                                if frais > 0:
                                    tx_frais_fonds_euro = Transaction(
                                        portefeuille_id=portefeuille_id,
                                        date_operation=date_val,
                                        type_operation='frais',
                                        montant=frais,
                                        libelle=f'Frais vente {pos["nom"][:20]} (déduits de {fonds_euro_cible.nom[:20]})',
                                        nom_titre=fonds_euro_cible.nom,
                                        categorie=fonds_euro_cible.categorie,
                                        quantite=frais / fonds_euro_cible.prix_moyen if fonds_euro_cible.prix_moyen > 0 else 0,
                                        prix_unitaire=fonds_euro_cible.prix_moyen,
                                        parent_transaction_id=tx_vente.id,
                                    )
                                    session.add(tx_frais_fonds_euro)
                                    fonds_euro_cible.quantite -= (
                                        frais / fonds_euro_cible.prix_moyen if fonds_euro_cible.prix_moyen > 0 else 0)

                            else:  # PEA/CTO : crédit du cash
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

                        # 🆕 Backfill cours historiques + valorisations (hors session)
                        try:
                            from services.backfill import (
                                backfill_cours_historique, backfill_valorisations
                            )
                            # Si la position vendue avait un ticker Yahoo, rafraîchir l'historique
                            if pos.get('ticker'):
                                backfill_cours_historique(portefeuille_id)
                            # Toujours recalculer les valorisations (cash + positions)
                            backfill_valorisations(portefeuille_id)
                        except Exception as e:
                            print(f'⚠️ Backfill échoué après vente : {e}')

                        # Notification avec +/- value
                        cout = q * pos['prix_moyen']
                        pv = montant_net - cout
                        pv_emoji = '✅' if pv >= 0 else '❌'
                        ui.notify(
                            f'{pv_emoji} Vente effectuée. '
                            f'+/- value : {format_money(pv, decimals=2)}',
                            type='positive' if pv >= 0 else 'warning',
                            timeout=4000
                        )
                        dialog.close()
                        refresh()

                    ui.button("💹 Confirmer la vente", on_click=save_vente) \
                        .props('unelevated').classes('bg-pink-600 text-white')

    dialog.open()