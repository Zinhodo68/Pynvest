"""Dialogue d'achat avec 3 modes : Action/ETF, OPCVM, Manuel."""
import asyncio
from datetime import date, datetime
from nicegui import ui
from sqlalchemy import select

from database.db import get_session
from database.models import Position, Transaction, Portefeuille
from utils.formatters import format_money
from services.market_data import (
    search_action_etf, search_fonds_opcvm,
    get_current_price_with_currency, get_currency_rate,
    get_price_at_date_with_currency,
)
from pages.portefeuille_detail._cash_helpers import impact_cash, ajuster_cash


def open_buy_dialog(portefeuille_id, c, refresh):
    """Dialogue d'achat avec 3 modes de sélection (Gère Arbitrage Fonds € pour AV/PER)."""

    state = {'selected': None, 'mode': 'action_etf'}

    with get_session() as session:
        # 🆕 Détection du type de portefeuille pour gérer le Cash / Fonds €
        ptf = session.get(Portefeuille, portefeuille_id)
        is_av_per = ptf.type in ['Assurance-Vie', 'AV', 'PER', 'Assurance Vie']

        if is_av_per:
            fonds_euros_db = session.execute(
                select(Position).where(
                    Position.portefeuille_id == portefeuille_id,
                    Position.categorie == 'Fonds Euro'
                )
            ).scalars().all()
            fonds_euros = {fe.id: {'nom': fe.nom, 'quantite': fe.quantite} for fe in fonds_euros_db}
            cash_dispo = sum(fe['quantite'] for fe in fonds_euros.values())
            label_dispo = 'Fonds € disponibles'
        else:
            cash_pos = session.execute(
                select(Position).where(
                    Position.portefeuille_id == portefeuille_id,
                    Position.nom == 'Cash'
                )
            ).scalar_one_or_none()
            cash_dispo = (cash_pos.quantite if cash_pos else 0) or 0
            fonds_euros = {}
            label_dispo = 'Cash disponible'

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-3').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]}; '
            f'min-width: 650px; max-width: 750px;'
    ):
        ui.label('🛒 Acheter un titre').classes('text-xl font-bold').style(
            f'color: {c["text_primary"]}'
        )

        with ui.row().classes('w-full items-center gap-2 px-3 py-2 rounded-lg').style(
                f'background-color: {"#10b981" if cash_dispo > 0 else "#ef4444"}20;'
        ):
            ui.icon('savings').classes('text-base').style(
                f'color: {"#10b981" if cash_dispo > 0 else "#ef4444"}'
            )
            ui.label(f'{label_dispo} : {format_money(cash_dispo)}').classes(
                'text-sm font-semibold'
            ).style(f'color: {"#10b981" if cash_dispo > 0 else "#ef4444"}')

        ui.label("Type d'actif").classes('text-sm font-medium mt-2').style(
            f'color: {c["text_secondary"]}'
        )

        mode_buttons = {}
        with ui.row().classes('w-full gap-2'):
            for mode_key, mode_label in [
                ('action_etf', '📈 Action / ETF / Crypto'),
                ('opcvm', '💼 OPCVM / SICAV'),
                ('manual', '✍️ Manuel (SCPI, Fonds €, etc)'),
            ]:
                btn = ui.button(mode_label).props('dense').style('flex: 1;')
                mode_buttons[mode_key] = btn

        def update_mode_buttons():
            for key, btn in mode_buttons.items():
                if key == state['mode']:
                    btn.props('unelevated dense')
                    btn.classes('bg-blue-600 text-white', remove='text-slate-700')
                else:
                    btn.props('outline dense')
                    btn.classes(remove='bg-blue-600 text-white')

        search_container = ui.column().classes('w-full gap-2')
        manual_container = ui.column().classes('w-full gap-3')
        form_container = ui.column().classes('w-full gap-3')
        form_container.set_visibility(False)

        def switch_mode(new_mode):
            state['mode'] = new_mode
            state['selected'] = None
            form_container.set_visibility(False)
            update_mode_buttons()

            if new_mode == 'manual':
                search_container.set_visibility(False)
                manual_container.set_visibility(True)
                _render_manual_form()
            else:
                search_container.set_visibility(True)
                manual_container.set_visibility(False)
                manual_container.clear()
                _setup_search()

        for key, btn in mode_buttons.items():
            btn.on('click', lambda k=key: switch_mode(k))

        # ─── MODE 1 & 2 : RECHERCHE ───
        search_input_ref = {'input': None}
        results_container = ui.column().classes('w-full gap-1').style(
            'max-height: 250px; overflow-y: auto;'
        )

        def _setup_search():
            search_container.clear()
            with search_container:
                placeholder_map = {
                    'action_etf': 'ex: Apple, AAPL, MSCI World, BTC...',
                    'opcvm': 'ex: Independance Expansion, LU1832174962...',
                }
                inp = ui.input(
                    placeholder=placeholder_map.get(state['mode'], '')
                ).classes('w-full').props('clearable autofocus')
                search_input_ref['input'] = inp
                inp.on('update:model-value', on_search_change)

        search_task = {'task': None}

        async def do_search(query: str):
            await asyncio.sleep(0.4)
            if not query or len(query) < 2:
                results_container.clear()
                return

            if state['mode'] == 'action_etf':
                results = await asyncio.to_thread(search_action_etf, query, 8)
            elif state['mode'] == 'opcvm':
                results = await asyncio.to_thread(search_fonds_opcvm, query, 8)
            else:
                results = []
            _render_results(results)

        def on_search_change(e):
            if search_task['task'] and not search_task['task'].done():
                search_task['task'].cancel()
            query = e.args if isinstance(e.args, str) else (e.value or '')
            search_task['task'] = asyncio.create_task(do_search(query))

        def _render_results(results):
            results_container.clear()
            if not results:
                with results_container:
                    ui.label('Aucun résultat').classes('text-sm py-2').style(
                        f'color: {c["text_secondary"]}'
                    )
                return

            with results_container:
                for r in results:
                    _render_result_row(r)

        def _render_result_row(r):
            type_colors = {
                'Action': '#3b82f6', 'ETF': '#10b981',
                'Fonds': '#8b5cf6', 'Crypto': '#f97316',
                'Indice': '#64748b',
            }
            type_color = type_colors.get(r.get('type', ''), '#64748b')

            with ui.row().classes(
                    'w-full items-center gap-3 p-2 rounded-lg cursor-pointer'
            ).style(f'background-color: {c["card_border"]}30;') \
                    .on('click', lambda res=r: select_ticker(res)):
                ui.label(r.get('type', '?')).classes(
                    'text-xs font-bold px-2 py-1 rounded'
                ).style(
                    f'background-color: {type_color}30; color: {type_color}; '
                    f'min-width: 60px; text-align: center;'
                )
                with ui.column().classes('gap-0').style('flex: 1; min-width: 0;'):
                    ui.label(r.get('name', '')).classes('text-sm font-medium').style(
                        f'color: {c["text_primary"]}; '
                        f'overflow: hidden; text-overflow: ellipsis; '
                        f'white-space: nowrap;'
                    )
                    sub = r.get('symbol', '')
                    if r.get('isin') and r.get('isin') != sub:
                        sub = f'{r["isin"]} • {r.get("exchange", "")}'
                    elif r.get('exchange'):
                        sub = f'{sub} • {r["exchange"]}'
                    ui.label(sub).classes('text-xs').style(
                        f'color: {c["text_secondary"]}'
                    )
                ui.label(r.get('currency', '')).classes('text-xs font-semibold') \
                    .style(
                    f'color: {c["text_secondary"]}; min-width: 40px; text-align: right;'
                )

        def select_ticker(ticker_data):
            state['selected'] = ticker_data
            results_container.clear()
            if search_input_ref['input']:
                search_input_ref['input'].value = (
                    f'{ticker_data.get("name", "")} ({ticker_data.get("symbol", "")})'
                )
            ui.notify(f'Récupération du cours...', type='info')
            asyncio.create_task(_load_and_show(ticker_data))

        async def _load_and_show(ticker_data):
            source = 'boursorama' if state['mode'] == 'opcvm' else 'yahoo'
            symbol_or_url = (ticker_data.get('url') if source == 'boursorama'
                             else ticker_data.get('symbol'))

            info = await asyncio.to_thread(
                get_current_price_with_currency, symbol_or_url, source
            )
            ticker_data['current_price'] = info['price']
            if info['currency']:
                ticker_data['currency'] = info['currency']
            ticker_data['source'] = source
            _render_purchase_form(ticker_data)
            form_container.set_visibility(True)

        # ─── MODE 3 : MANUEL ───
        def _render_manual_form():
            manual_container.clear()
            with manual_container:
                with ui.row().classes('w-full gap-3'):
                    nom_input = ui.input('Nom du titre *') \
                        .classes('flex-1') \
                        .props('placeholder="ex: SCPI Primovie"')

                    # 🆕 Ajout du type "Fonds Euro"
                    cat_input = ui.select(
                        {
                            'Fonds Euro': 'Fonds Euro',
                            'SCPI': 'SCPI',
                            'Fonds': 'Fonds / OPCVM',
                            'Action': 'Action',
                            'ETF': 'ETF',
                            'Obligation': 'Obligation',
                            'UC': 'Unité de Compte',
                            'Projet': 'Projet (crowdfunding)',
                            'Autre': 'Autre',
                        },
                        value='SCPI', label='Catégorie *'
                    ).classes('flex-1')

                with ui.row().classes('w-full gap-3'):
                    code_input = ui.input('Code / ISIN (optionnel)') \
                        .classes('flex-1') \
                        .props('placeholder="ex: FR0011053068"')
                    devise_input = ui.select(
                        {'EUR': 'EUR €', 'USD': 'USD $', 'GBP': 'GBP £'},
                        value='EUR', label='Devise'
                    ).classes('w-32')

                def go_to_purchase():
                    if not nom_input.value or not nom_input.value.strip():
                        ui.notify('Le nom est obligatoire', type='negative')
                        return
                    ticker_data = {
                        'name': nom_input.value.strip(),
                        'symbol': code_input.value or nom_input.value.strip()[:20],
                        'isin': code_input.value or None,
                        'type': cat_input.value,
                        'exchange': 'Manuel',
                        'currency': devise_input.value,
                        'source': 'manual',
                        'current_price': None,
                    }
                    state['selected'] = ticker_data
                    _render_purchase_form(ticker_data)
                    form_container.set_visibility(True)

                with ui.row().classes('w-full justify-end mt-2'):
                    ui.button('Continuer →', on_click=go_to_purchase) \
                        .props('unelevated').classes('bg-blue-600 text-white')

        # ─── FORMULAIRE D'ACHAT ───
        def _render_purchase_form(t):
            form_container.clear()
            updating = {'value': False}

            with form_container:
                with ui.card().classes('w-full p-4 rounded-lg').style(
                        f'background-color: {c["card_border"]}30; '
                        f'border: 1px solid {c["card_border"]};'
                ):
                    with ui.row().classes('w-full items-center justify-between'):
                        with ui.column().classes('gap-0'):
                            ui.label(t['name']).classes('text-base font-bold').style(
                                f'color: {c["text_primary"]}'
                            )
                            sub = f'{t.get("symbol", "")} • {t.get("type", "")} • {t.get("currency", "EUR")}'
                            ui.label(sub).classes('text-xs').style(
                                f'color: {c["text_secondary"]}'
                            )

                # Date
                date_today_fr = date.today().strftime('%d/%m/%Y')
                with ui.input("Date d'achat", value=date_today_fr).classes('w-full') \
                        .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input:
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

                # Prix
                prix_input = ui.number(
                    f'Prix unitaire ({t.get("currency", "EUR")}) *',
                    value=t.get('current_price') or 0,
                    format='%.4f', min=0
                ).classes('w-full')

                price_info_label = ui.label('').classes('text-xs italic px-2').style(
                    f'color: {c["text_secondary"]}; min-height: 16px;'
                )

                price_state = {
                    'manually_modified': False,
                    'last_auto_value': t.get('current_price') or 0,
                }

                if t.get('current_price'):
                    price_info_label.text = (
                        f"💹 Cours actuel du marché : {t['current_price']:.4f} "
                        f"{t.get('currency', 'EUR')}"
                    )

                async def update_price_for_date():
                    if price_state['manually_modified']:
                        return
                    if t.get('source') == 'manual':
                        return

                    try:
                        target_date = datetime.strptime(
                            date_input.value, '%d/%m/%Y'
                        ).date()
                    except (ValueError, TypeError):
                        return

                    if target_date == date.today():
                        if t.get('current_price'):
                            updating['value'] = True
                            prix_input.value = t['current_price']
                            price_state['last_auto_value'] = t['current_price']
                            updating['value'] = False
                            price_info_label.text = (
                                f"💹 Cours actuel du marché : "
                                f"{t['current_price']:.4f} "
                                f"{t.get('currency', 'EUR')}"
                            )
                            update_montant_from_qte()
                        return

                    price_info_label.text = '⏳ Récupération du cours historique...'

                    source = t.get('source', 'yahoo')
                    symbol_or_url = (t.get('url') if source == 'boursorama'
                                     else t.get('symbol'))

                    try:
                        info = await asyncio.to_thread(
                            get_price_at_date_with_currency,
                            symbol_or_url, source, target_date
                        )

                        if info['price'] is not None:
                            updating['value'] = True
                            prix_input.value = round(info['price'], 4)
                            price_state['last_auto_value'] = info['price']
                            updating['value'] = False
                            price_info_label.text = (
                                f"💹 Cours du marché au {target_date.strftime('%d/%m/%Y')} : "
                                f"{info['price']:.4f} {info.get('currency', 'EUR')}"
                            )
                            update_montant_from_qte()
                        else:
                            price_info_label.text = (
                                f"⚠️ Cours historique non disponible "
                                f"(saisie manuelle requise)"
                            )
                    except Exception as e:
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

                # 🆕 Sélecteur du Fonds Euro (Visible uniquement pour AV/PER)
                source_fonds_input = None
                if is_av_per and t.get('type') != 'Fonds Euro':
                    if not fonds_euros:
                        ui.label('⚠️ Aucun Fonds € existant pour financer cet achat.').classes(
                            'text-red-500 text-sm font-bold mt-2')
                    else:
                        options = {fe_id: f"{fe_data['nom']} ({format_money(fe_data['quantite'])})" for fe_id, fe_data
                                   in fonds_euros.items()}
                        source_fonds_input = ui.select(
                            options,
                            label='Fonds € source (pour le paiement) *',
                            value=list(options.keys())[0]
                        ).classes('w-full mt-2')

                # Frais
                frais_input = ui.number(
                    'Frais (€)', value=0, format='%.2f', min=0
                ).classes('w-full')

                ui.label("Saisissez l'un OU l'autre").classes('text-xs italic mt-2') \
                    .style(f'color: {c["text_secondary"]}')

                with ui.row().classes('w-full gap-3'):
                    is_action = t.get('type') == 'Action'
                    qte_format = '%g' if is_action else '%.4f'
                    qte_step = 1 if is_action else 0.0001

                    quantite_input = ui.number(
                        '🔢 Quantité', value=0,
                        format=qte_format, min=0, step=qte_step
                    ).classes('flex-1')

                    montant_input = ui.number(
                        f'💶 Montant ({t.get("currency", "EUR")})', value=0,
                        format='%.2f', min=0
                    ).classes('flex-1')

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
                            new_qte = m / p
                            new_qte = int(new_qte) if is_action else round(new_qte, 4)
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
                        m = float(montant_input.value or 0)
                        p = float(prix_input.value or 0)
                        f = float(frais_input.value or 0)
                        cur = t.get('currency', 'EUR')

                        if cur != 'EUR':
                            summary_label.text = (
                                f'📦 {q:g} parts × {p:.4f} {cur} = {m:.2f} {cur}\n'
                                f'💸 + {f:.2f} € de frais\n'
                                f'⚠️ Conversion {cur}→EUR à la sauvegarde'
                            )
                        else:
                            total = m + f
                            warning = ''
                            if total > cash_dispo and t.get('type') != 'Fonds Euro':
                                warning = (f'\n⚠️ Solde insuffisant '
                                           f'({format_money(cash_dispo)} dispo)')
                            summary_label.text = (
                                f'📦 {q:g} × {format_money(p, decimals=2)} '
                                f'= {format_money(m, decimals=2)}\n'
                                f'💸 + {format_money(f, decimals=2)} frais\n'
                                f'💰 Total : {format_money(total, decimals=2)}'
                                f'{warning}'
                            )
                    except (TypeError, ValueError):
                        summary_label.text = '💡 Saisissez quantité ou montant'

                update_summary()

                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('Annuler', on_click=dialog.close).props('flat')

                    def save_achat():
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
                        if is_action and q != int(q):
                            ui.notify('Quantité entière requise pour une action',
                                      type='negative')
                            return

                        frais = float(frais_input.value or 0)

                        prix_eur = p_unit
                        cur = t.get('currency', 'EUR')
                        if cur != 'EUR':
                            rate = get_currency_rate(cur, 'EUR')
                            if rate is None:
                                ui.notify(f'Conversion {cur}→EUR impossible',
                                          type='negative')
                                return
                            prix_eur = p_unit * rate

                        montant_titres_eur = q * prix_eur
                        total_eur = montant_titres_eur + frais

                        with get_session() as session:

                            # 🆕 VÉRIFICATION DU SOLDE (Cash ou Fonds €)
                            fe_pos = None
                            if t.get('type') != 'Fonds Euro':  # Si on ne crée pas un fonds euro
                                if is_av_per:
                                    if not source_fonds_input or not source_fonds_input.value:
                                        ui.notify("Veuillez sélectionner un Fonds € source", type='warning')
                                        return
                                    fe_id = source_fonds_input.value
                                    fe_pos = session.get(Position, fe_id)
                                    cash_now = fe_pos.quantite or 0
                                else:
                                    cash = session.execute(
                                        select(Position).where(
                                            Position.portefeuille_id == portefeuille_id,
                                            Position.nom == 'Cash'
                                        )
                                    ).scalar_one_or_none()
                                    cash_now = (cash.quantite if cash else 0) or 0

                                if cash_now < total_eur:
                                    ui.notify(
                                        f'Solde insuffisant ({format_money(cash_now)} dispo)',
                                        type='warning'
                                    )
                                    return

                            stmt = select(Position).where(
                                Position.portefeuille_id == portefeuille_id,
                            )
                            if t.get('symbol'):
                                stmt = stmt.where(
                                    (Position.ticker == t['symbol']) |
                                    (Position.nom == t['name'])
                                )
                            else:
                                stmt = stmt.where(Position.nom == t['name'])

                            existing = session.execute(stmt).scalar_one_or_none()

                            if existing:
                                old_qty = existing.quantite or 0
                                old_pru = existing.prix_moyen or 0
                                new_qty = old_qty + q
                                new_pru = ((old_qty * old_pru) + (q * prix_eur)) / new_qty
                                existing.quantite = new_qty
                                existing.prix_moyen = new_pru
                            else:
                                cours_marche = prix_eur
                                if t.get('source') in ('yahoo', 'boursorama') and t.get('current_price'):
                                    cours_marche = t['current_price']
                                    if cur != 'EUR':
                                        cours_marche = t['current_price'] * (
                                                get_currency_rate(cur, 'EUR') or 1
                                        )

                                new_pos = Position(
                                    portefeuille_id=portefeuille_id,
                                    nom=t['name'],
                                    code=t.get('isin'),
                                    ticker=t.get('symbol') if t.get('source') != 'manual' else None,
                                    categorie=t.get('type', 'Autre'),
                                    quantite=q,
                                    prix_moyen=prix_eur,
                                    cours_actuel=cours_marche,
                                    devise='EUR',
                                    date_ouverture=date_val,
                                    auto_update=(t.get('source') != 'manual' and t.get('type') != 'Fonds Euro'),
                                )
                                session.add(new_pos)

                            tx_achat = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='achat',
                                montant=montant_titres_eur,
                                libelle=f'Achat {q:g} × {t["name"][:30]}',
                                ticker=t.get('symbol') if t.get('source') != 'manual' else None,
                                code=t.get('isin'),
                                nom_titre=t['name'],
                                categorie=t.get('type', 'Autre'),
                                quantite=q,
                                prix_unitaire=prix_eur,
                            )
                            session.add(tx_achat)
                            session.flush()

                            # 🆕 PAIEMENT / DÉDUCTION DU SOLDE
                            if t.get('type') != 'Fonds Euro':
                                if is_av_per:
                                    fe_pos.quantite -= total_eur

                                    tx_vente_fe = Transaction(
                                        portefeuille_id=portefeuille_id,
                                        date_operation=date_val,
                                        type_operation='vente',
                                        montant=montant_titres_eur,
                                        libelle=f'Arbitrage vers {t["name"][:30]}',
                                        nom_titre=fe_pos.nom,
                                        categorie='Fonds Euro',
                                        quantite=montant_titres_eur,
                                        prix_unitaire=1.0,
                                        parent_transaction_id=tx_achat.id
                                    )
                                    session.add(tx_vente_fe)
                                else:
                                    ajuster_cash(session, portefeuille_id,
                                                 impact_cash('achat', montant_titres_eur))

                            if frais > 0:
                                tx_frais = Transaction(
                                    portefeuille_id=portefeuille_id,
                                    date_operation=date_val,
                                    type_operation='frais',
                                    montant=frais,
                                    libelle=f'Frais courtage - {t["name"][:30]}',
                                    parent_transaction_id=tx_achat.id,
                                )
                                session.add(tx_frais)
                                if not is_av_per and t.get('type') != 'Fonds Euro':
                                    ajuster_cash(session, portefeuille_id,
                                                 impact_cash('frais', frais))

                            session.commit()

                        ui.notify(f'✅ Achat de {q:g} × {t["name"][:30]} effectué',
                                  type='positive')
                        dialog.close()
                        refresh()

                    ui.button("🛒 Confirmer l'achat", on_click=save_achat) \
                        .props('unelevated').classes('bg-emerald-600 text-white')

        switch_mode('action_etf')

    dialog.open()