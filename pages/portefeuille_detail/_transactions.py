"""Card des transactions + dialogue d'ajout/édition + filtres."""
import asyncio
import math
from datetime import date, datetime
from nicegui import ui
from sqlalchemy import select

from database.db import get_session
from database.models import Transaction, Portefeuille, Position
from utils.formatters import format_money, format_date_fr
from pages.portefeuille_detail._cash_helpers import impact_cash, ajuster_cash
from services.labels import get_display_name


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Backfill async
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _run_backfill_async(portefeuille_id: int, need_cours: bool = False):
    """Backfill non-bloquant après toute transaction."""
    from services.backfill import backfill_cours_historique, backfill_valorisations

    notif = ui.notification(
        "📈 Recalcul de l'historique en cours...",
        type='ongoing',
        spinner=True,
        timeout=None,
    )
    try:
        if need_cours:
            await asyncio.to_thread(backfill_cours_historique, portefeuille_id)
        await asyncio.to_thread(backfill_valorisations, portefeuille_id)
        notif.dismiss()
        ui.notify('📈 Historique mis à jour', type='positive', timeout=3000)
    except Exception as e:
        notif.dismiss()
        ui.notify(f'⚠️ Recalcul échoué : {e}', type='warning', timeout=5000)
        print(f'⚠️ Backfill async échoué pour portefeuille #{portefeuille_id}: {e}')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constantes visuelles partagées
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TYPE_COLORS = {
    'versement': '#10b981', 'retrait': '#ef4444',
    'dividende': '#3b82f6', 'frais': '#f97316',
    'achat': '#8b5cf6', 'vente': '#ec4899',
    'interets': '#eab308',
}

TYPE_ICONS = {
    'versement': 'arrow_downward', 'retrait': 'arrow_upward',
    'dividende': 'paid', 'frais': 'remove_circle',
    'achat': 'shopping_cart', 'vente': 'sell',
    'interets': 'trending_up',
}

TYPE_LABELS = {
    'versement': 'Versement', 'retrait': 'Retrait',
    'dividende': 'Dividende', 'frais': 'Frais',
    'achat': 'Achat', 'vente': 'Vente',
    'interets': 'Intérêts',
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🆕 Helpers actifs historiques (pour dividendes sur titres vendus)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_historical_assets(session, portefeuille_id: int,
                           active_position_names: set[str]) -> list[dict]:
    """Récupère les titres historiquement détenus dans le portefeuille
    qui ne sont plus en position active.

    Retourne une liste de dicts pseudo-Position pour utilisation dans le select :
        [{'pseudo_id': str, 'nom': str, 'ticker': str, 'code': str,
          'categorie': str, 'quantite': 0, 'cours_actuel': None,
          'is_historical': True}, ...]

    Les pseudo_id sont des strings préfixés 'HIST_' pour les distinguer
    des IDs entiers des Position réelles.
    """
    # On extrait les actifs distincts depuis les transactions d'achat
    # qui ont un nom_titre et qui ne sont pas Cash/Fonds Euro
    rows = session.execute(
        select(
            Transaction.nom_titre,
            Transaction.ticker,
            Transaction.code,
            Transaction.categorie,
        ).where(
            Transaction.portefeuille_id == portefeuille_id,
            Transaction.type_operation == 'achat',
            Transaction.nom_titre.is_not(None),
            Transaction.categorie.not_in(['Fonds Euro', 'Fonds €', 'Cash']),
        ).distinct()
    ).all()

    historical = []
    seen_names = set()
    for nom, ticker, code, categorie in rows:
        if not nom or nom in active_position_names or nom in seen_names:
            continue
        seen_names.add(nom)
        historical.append({
            'pseudo_id': f'HIST_{nom}',
            'nom': nom,
            'ticker': ticker,
            'code': code,
            'categorie': categorie or 'Action',
            'quantite': 0,
            'cours_actuel': None,
            'is_historical': True,
        })

    # Trier par nom
    historical.sort(key=lambda x: x['nom'].lower())
    return historical


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Filtres
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_unique_assets(transactions: list[dict]) -> dict[str, str]:
    """Extrait les actifs uniques depuis les transactions (pour le filtre)."""
    assets = {}
    for t in transactions:
        nom = t.get('nom_titre')
        if nom and nom not in ('Cash',) and t.get('type') in ('achat', 'vente', 'dividende', 'frais'):
            display = get_display_name(
                ticker=t.get('ticker'),
                code=t.get('code'),
                fallback=nom,
            )
            assets[nom] = display
    return dict(sorted(assets.items(), key=lambda x: x[1].lower()))


def _apply_filters(transactions: list[dict], filters: dict) -> list[dict]:
    """Applique les filtres actifs sur la liste de transactions."""
    result = transactions

    # Filtre par type
    active_types = filters.get('types', set())
    if active_types:
        result = [t for t in result if t['type'] in active_types]

    # Filtre par actif
    active_asset = filters.get('asset')
    if active_asset:
        result = [t for t in result if t.get('nom_titre') == active_asset]

    # Filtre par date début
    date_from = filters.get('date_from')
    if date_from:
        result = [t for t in result if t['date'] >= date_from]

    # Filtre par date fin
    date_to = filters.get('date_to')
    if date_to:
        result = [t for t in result if t['date'] <= date_to]

    # Filtre par recherche texte
    search_text = (filters.get('search') or '').strip().lower()
    if search_text:
        result = [
            t for t in result
            if search_text in (t.get('libelle') or '').lower()
            or search_text in (t.get('nom_titre') or '').lower()
            or search_text in str(t.get('montant', ''))
        ]

    return result


def _count_active_filters(filters: dict) -> int:
    """Compte le nombre de filtres actifs."""
    count = 0
    if filters.get('types'):
        count += 1
    if filters.get('asset'):
        count += 1
    if filters.get('date_from'):
        count += 1
    if filters.get('date_to'):
        count += 1
    if (filters.get('search') or '').strip():
        count += 1
    return count


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Rendu principal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_transactions_card(transactions, c, is_dark, refresh, portefeuille_id,
                             full_width=False):
    # Séparer les transactions principales des frais liés
    main_transactions = [t for t in transactions if not t.get('parent_transaction_id')]
    frais_by_parent = {}
    for t in transactions:
        if t.get('parent_transaction_id'):
            parent_id = t['parent_transaction_id']
            frais_by_parent.setdefault(parent_id, []).append(t)

    # Cache display names
    display_name_cache = {}

    def resolve_display_name(tx: dict) -> str | None:
        if not tx.get('nom_titre'):
            return None
        key = (tx.get('ticker'), tx.get('code'), tx.get('nom_titre'))
        if key not in display_name_cache:
            display_name_cache[key] = get_display_name(
                ticker=tx.get('ticker'),
                code=tx.get('code'),
                fallback=tx['nom_titre'],
            )
        return display_name_cache[key]

    # ── État des filtres ──
    filters = {
        'types': set(),
        'asset': None,
        'date_from': None,
        'date_to': None,
        'search': None,
    }
    filter_state = {'expanded': False}

    # Actifs uniques pour le select
    unique_assets = _extract_unique_assets(main_transactions)

    with ui.card().classes('p-5 rounded-xl w-full').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]};'
    ):
        # ── Header ──
        with ui.row().classes('w-full items-center justify-between mb-1'):
            with ui.column().classes('gap-0'):
                ui.label('Transactions').classes('text-lg font-bold').style(
                    f'color: {c["text_primary"]}'
                )
                count_label = ui.label(
                    f'{len(main_transactions)} mouvement(s)'
                ).classes('text-xs').style(f'color: {c["text_secondary"]}')

            with ui.row().classes('items-center gap-1'):
                # ── Bouton filtre avec badge ──
                filter_btn_container = ui.element('div').classes('relative')
                with filter_btn_container:
                    filter_btn = ui.button(
                        icon='filter_list',
                        on_click=lambda: toggle_filters()
                    ).props('flat round dense size=sm').style(
                        f'color: {c["text_secondary"]};'
                    ).tooltip('Filtrer les transactions')

                    # Badge compteur (caché si 0)
                    filter_badge = ui.badge('0').props('floating color="primary"').style(
                        'font-size: 9px; min-width: 16px; height: 16px; padding: 0 4px;'
                    )
                    filter_badge.set_visibility(False)

                ui.button(
                    '+ Transaction',
                    on_click=lambda: open_transaction_dialog(portefeuille_id, c, refresh)
                ).props('unelevated dense').classes('bg-blue-600 text-white')

        # ── Panneau de filtres (replié par défaut) ──
        filter_panel = ui.column().classes('w-full gap-2 mb-2')
        filter_panel.set_visibility(False)

        with filter_panel:
            # Ligne 1 : chips de type
            with ui.row().classes('w-full items-center gap-1 flex-wrap'):
                ui.icon('label').classes('text-sm').style(
                    f'color: {c["text_secondary"]}; opacity: 0.6;'
                )

                type_chips = {}
                for type_key, type_label in TYPE_LABELS.items():
                    type_color = TYPE_COLORS[type_key]
                    chip = ui.element('div').classes(
                        'px-2 py-0.5 rounded-full cursor-pointer text-xs font-medium '
                        'select-none'
                    ).style(
                        f'border: 1px solid {type_color}40; '
                        f'color: {c["text_secondary"]}; '
                        f'transition: all 0.15s ease;'
                    )
                    with chip:
                        ui.label(type_label)

                    def make_toggle(key=type_key, el=chip, color=type_color):
                        def toggle():
                            if key in filters['types']:
                                filters['types'].discard(key)
                                el.style(
                                    f'border: 1px solid {color}40; '
                                    f'color: {c["text_secondary"]}; '
                                    f'background-color: transparent;'
                                )
                            else:
                                filters['types'].add(key)
                                el.style(
                                    f'border: 1px solid {color}; '
                                    f'color: {color}; '
                                    f'background-color: {color}15;'
                                )
                            apply_and_refresh()
                        return toggle

                    chip.on('click', make_toggle())
                    type_chips[type_key] = chip

            # Ligne 2 : actif + dates + recherche
            with ui.row().classes('w-full items-end gap-2 flex-wrap'):
                # Select actif
                asset_options = {'': '— Tous les actifs —'}
                asset_options.update(unique_assets)
                asset_select = ui.select(
                    asset_options,
                    value='',
                    label='Actif',
                    on_change=lambda e: _on_asset_change(e.value),
                ).classes('flex-1').style(
                    'min-width: 140px; max-width: 200px;'
                ).props('dense options-dense outlined')

                # Date début
                with ui.input(
                    'Depuis', value=''
                ).classes('flex-1').style(
                    'min-width: 110px; max-width: 140px;'
                ).props(
                    'dense outlined mask="##/##/####" placeholder="JJ/MM/AAAA"'
                ) as date_from_input:
                    with ui.menu().props('no-parent-event') as menu_from:
                        dp_from = ui.date().props('mask="DD/MM/YYYY"')
                        dp_from.bind_value(date_from_input)
                        with dp_from:
                            with ui.row().classes('justify-end'):
                                ui.button('OK', on_click=menu_from.close).props('flat dense')
                    with date_from_input.add_slot('append'):
                        ui.icon('event').on('click', menu_from.open).classes(
                            'cursor-pointer text-sm'
                        ).style(f'color: {c["text_secondary"]}')

                # Date fin
                with ui.input(
                    "Jusqu'au", value=''
                ).classes('flex-1').style(
                    'min-width: 110px; max-width: 140px;'
                ).props(
                    'dense outlined mask="##/##/####" placeholder="JJ/MM/AAAA"'
                ) as date_to_input:
                    with ui.menu().props('no-parent-event') as menu_to:
                        dp_to = ui.date().props('mask="DD/MM/YYYY"')
                        dp_to.bind_value(date_to_input)
                        with dp_to:
                            with ui.row().classes('justify-end'):
                                ui.button('OK', on_click=menu_to.close).props('flat dense')
                    with date_to_input.add_slot('append'):
                        ui.icon('event').on('click', menu_to.open).classes(
                            'cursor-pointer text-sm'
                        ).style(f'color: {c["text_secondary"]}')

                # Recherche texte
                search_input = ui.input(
                    placeholder='Rechercher...'
                ).classes('flex-1').style(
                    'min-width: 120px; max-width: 180px;'
                ).props('dense outlined clearable')
                with search_input.add_slot('prepend'):
                    ui.icon('search').classes('text-sm').style(
                        f'color: {c["text_secondary"]}'
                    )

                # Bouton reset
                reset_btn = ui.button(
                    icon='clear_all',
                    on_click=lambda: reset_filters()
                ).props('flat round dense size=sm').style(
                    f'color: {c["text_secondary"]};'
                ).tooltip('Réinitialiser les filtres')

            # Séparateur fin filtres
            ui.element('div').classes('h-px w-full').style(
                f'background-color: {c["card_border"]}; opacity: 0.5;'
            )

        # ── Conteneur des transactions (sera redessiné au filtrage) ──
        tx_list_container = ui.column().classes('w-full gap-2').style(
            'max-height: 500px; overflow-y: auto;'
        )

        # ── Handlers ──
        def _on_asset_change(value):
            filters['asset'] = value if value else None
            apply_and_refresh()

        def _parse_filter_date(value: str) -> str | None:
            """Convertit JJ/MM/AAAA en YYYY-MM-DD pour comparaison ISO."""
            if not value or len(value) != 10:
                return None
            try:
                dt = datetime.strptime(value, '%d/%m/%Y')
                return dt.date().isoformat()
            except (ValueError, TypeError):
                return None

        def _on_date_from_change(_=None):
            filters['date_from'] = _parse_filter_date(date_from_input.value)
            apply_and_refresh()

        def _on_date_to_change(_=None):
            filters['date_to'] = _parse_filter_date(date_to_input.value)
            apply_and_refresh()

        def _on_search_change(_=None):
            filters['search'] = search_input.value
            apply_and_refresh()

        def reset_filters():
            filters['types'] = set()
            filters['asset'] = None
            filters['date_from'] = None
            filters['date_to'] = None
            filters['search'] = None

            asset_select.value = ''
            date_from_input.value = ''
            date_to_input.value = ''
            search_input.value = ''

            # Reset chip styles
            for type_key, chip in type_chips.items():
                color = TYPE_COLORS[type_key]
                chip.style(
                    f'border: 1px solid {color}40; '
                    f'color: {c["text_secondary"]}; '
                    f'background-color: transparent;'
                )

            apply_and_refresh()

        def toggle_filters():
            filter_state['expanded'] = not filter_state['expanded']
            filter_panel.set_visibility(filter_state['expanded'])
            if filter_state['expanded']:
                filter_btn.style(f'color: #3b82f6;')
            else:
                filter_btn.style(f'color: {c["text_secondary"]};')

        def apply_and_refresh():
            """Applique les filtres et redessine la liste."""
            filtered = _apply_filters(main_transactions, filters)
            active_count = _count_active_filters(filters)

            # Mise à jour du badge
            if active_count > 0:
                filter_badge.set_text(str(active_count))
                filter_badge.set_visibility(True)
                filter_btn.style('color: #3b82f6;')
            else:
                filter_badge.set_visibility(False)
                if not filter_state['expanded']:
                    filter_btn.style(f'color: {c["text_secondary"]};')

            # Mise à jour du compteur
            if active_count > 0:
                count_label.set_text(
                    f'{len(filtered)} / {len(main_transactions)} mouvement(s)'
                )
            else:
                count_label.set_text(f'{len(main_transactions)} mouvement(s)')

            _render_transaction_list(filtered)

        def _render_transaction_list(txs: list[dict]):
            """Redessine la liste des transactions filtrées."""
            tx_list_container.clear()
            with tx_list_container:
                if not txs:
                    with ui.column().classes('w-full items-center py-6 gap-1'):
                        icon_name = 'filter_list_off' if _count_active_filters(filters) > 0 \
                            else 'receipt_long'
                        msg = 'Aucune transaction ne correspond aux filtres' \
                            if _count_active_filters(filters) > 0 \
                            else 'Aucune transaction'
                        ui.icon(icon_name).classes('text-4xl').style(
                            f'color: {c["text_secondary"]}'
                        )
                        ui.label(msg).classes('text-sm').style(
                            f'color: {c["text_secondary"]}'
                        )
                        if _count_active_filters(filters) > 0:
                            ui.button(
                                'Réinitialiser les filtres',
                                on_click=reset_filters
                            ).props('flat dense').style(f'color: #3b82f6')
                    return

                for t in reversed(txs):
                    _render_transaction_row(t)

        def _render_transaction_row(t: dict):
            """Affiche une ligne de transaction."""
            type_color = TYPE_COLORS.get(t['type'], '#64748b')
            type_icon = TYPE_ICONS.get(t['type'], 'circle')
            sign = '+' if t['type'] in ('versement', 'dividende', 'vente', 'interets') else '-'

            frais_lies = frais_by_parent.get(t['id'], [])
            total_frais = sum(f['montant'] for f in frais_lies)
            asset_display_name = resolve_display_name(t)

            with ui.row().classes('w-full items-center gap-3 p-2 rounded-lg').style(
                    f'background-color: {c["card_border"]}20;'
            ):
                with ui.element('div').classes(
                        'rounded-full flex items-center justify-center'
                ).style(
                    f'background-color: {type_color}20; '
                    f'width: 32px; height: 32px; min-width: 32px;'
                ):
                    ui.icon(type_icon).classes('text-base').style(f'color: {type_color}')

                with ui.column().classes('gap-0').style('flex: 1; min-width: 0;'):
                    display_libelle = t['libelle'] or t['type'].capitalize()
                    if t['type'] == 'dividende':
                        if (t.get('quantite') is not None and t.get('quantite') > 0 and
                                t.get('prix_unitaire') is not None
                                and t.get('prix_unitaire') > 0):
                            display_libelle += ' (C)'
                        else:
                            display_libelle += ' (D)'
                    elif t['type'] == 'frais':
                        if (t.get('quantite') is not None and t.get('quantite') > 0 and
                                t.get('prix_unitaire') is not None
                                and t.get('prix_unitaire') > 0):
                            display_libelle += ' (en parts)'

                    ui.label(display_libelle).classes('text-sm font-medium').style(
                        f'color: {c["text_primary"]}; '
                        f'overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
                    )

                    sub_text = format_date_fr(t['date'])
                    if total_frais > 0:
                        sub_text += f' • +{format_money(total_frais, decimals=2)} de frais'

                    if t['type'] in ('achat', 'vente') and asset_display_name:
                        sub_text += f' • Actif: {asset_display_name}'
                        if (t.get('quantite') is not None and t.get('quantite') > 0
                                and t.get('prix_unitaire') is not None
                                and t.get('prix_unitaire') > 0):
                            sub_text += (
                                f' ({t["quantite"]:g} parts @ '
                                f'{t["prix_unitaire"]:.4f}€)'
                            )
                    elif t['type'] == 'dividende' and asset_display_name:
                        sub_text += f' • Actif: {asset_display_name}'
                        if (t.get('quantite') is not None and t.get('quantite') > 0
                                and t.get('prix_unitaire') is not None
                                and t.get('prix_unitaire') > 0):
                            sub_text += (
                                f' ({t["quantite"]:g} parts @ '
                                f'{t["prix_unitaire"]:.4f}€)'
                            )
                    elif (t['type'] == 'frais' and asset_display_name
                          and t.get('quantite') is not None and t.get('quantite') > 0
                          and t.get('prix_unitaire') is not None
                          and t.get('prix_unitaire') > 0):
                        sub_text += (
                            f' • Actif: {asset_display_name} '
                            f'({t["quantite"]:g} parts @ {t["prix_unitaire"]:.4f}€)'
                        )

                    ui.label(sub_text).classes('text-xs').style(
                        f'color: {c["text_secondary"]}'
                    )

                ui.label(f'{sign}{format_money(t["montant"], decimals=2)}').classes(
                    'text-sm font-semibold'
                ).style(f'color: {type_color}; white-space: nowrap;')

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

        # ── Binding des événements de filtre ──
        date_from_input.on('blur', _on_date_from_change)
        dp_from.on('update:model-value', _on_date_from_change)
        date_to_input.on('blur', _on_date_to_change)
        dp_to.on('update:model-value', _on_date_to_change)
        search_input.on('update:model-value', _on_search_change)

        # ── Rendu initial ──
        _render_transaction_list(main_transactions)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dialogue de transaction
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def open_transaction_dialog(portefeuille_id, c, refresh, transaction_id: int = None):
    """Création ou édition d'une transaction."""
    is_edit = transaction_id is not None

    data = {
        'date_operation': date.today().isoformat(),
        'type_operation': 'versement',
        'montant': 0.0,
        'libelle': '',
        'source_position_id': None,
        'initial_fee_type': 'cash',
        'initial_fee_parts_quantity': 0.0,
    }
    frais_existants = 0

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

        chargeable_positions_db = session.execute(
            select(Position).where(
                Position.portefeuille_id == portefeuille_id,
                Position.categorie.not_in(['Fonds Euro', 'Cash'])
            )
        ).scalars().all()
        chargeable_positions_options = {
            pos.id: {
                'nom': pos.nom,
                'quantite': pos.quantite,
                'cours_actuel': pos.cours_actuel,
                'ticker': pos.ticker,
                'code': pos.code,
                'categorie': pos.categorie,
                'is_historical': False,
            }
            for pos in chargeable_positions_db
        }

        # 🆕 Ajouter les actifs historiquement détenus (pour dividendes sur titres vendus)
        active_position_names = {pos.nom for pos in chargeable_positions_db}
        historical_assets = _get_historical_assets(
            session, portefeuille_id, active_position_names
        )
        for hist in historical_assets:
            chargeable_positions_options[hist['pseudo_id']] = {
                'nom': hist['nom'],
                'quantite': 0,
                'cours_actuel': None,
                'ticker': hist['ticker'],
                'code': hist['code'],
                'categorie': hist['categorie'],
                'is_historical': True,
            }

        if is_edit:
            t = session.get(Transaction, transaction_id)
            if t:
                data['date_operation'] = t.date_operation.isoformat()
                data['type_operation'] = t.type_operation
                data['montant'] = t.montant
                data['libelle'] = t.libelle or ''

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
                    else:
                        # 🆕 Si la Position n'existe plus, on tente la version historique
                        pseudo_id = f'HIST_{t.nom_titre}'
                        if pseudo_id in chargeable_positions_options:
                            data['source_position_id'] = pseudo_id

                if t.type_operation == 'frais':
                    if t.quantite is not None and t.quantite > 0 and \
                            t.prix_unitaire is not None and t.prix_unitaire > 0:
                        data['initial_fee_type'] = 'parts'
                        data['initial_fee_parts_quantity'] = t.quantite
                    else:
                        data['initial_fee_type'] = 'cash'

    is_initial_achat_vente_edit = is_edit and data['type_operation'] in ('achat', 'vente')
    date_initiale_fr = date.fromisoformat(data['date_operation']).strftime('%d/%m/%Y')
    last_dividend_input_changed = {'value': None}
    last_fees_parts_input_changed = {'value': None}

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
        dividend_source_select = None
        fees_asset_select = None
        no_chargeable_assets_label = None
        no_dividend_sources_label = None
        reinvest_checkbox = None
        fee_type_toggle = None
        date_input_ui_element = None
        date_picker = None
        montant_input = None
        dividend_per_share_input = None
        dividend_parts_input = None
        fees_parts_to_deduct_input = None
        fees_final_parts_qty_input = None
        current_fees_parts_qty_label = None
        libelle_input = None
        frais_input = None
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

        type_input = ui.select(
            type_options,
            value=data['type_operation'],
            label="Type d'opération",
            on_change=on_type_change,
        ).classes('w-full')

        if is_edit:
            type_input.props('readonly')
            if data['type_operation'] in ('achat', 'vente'):
                ui.notify(
                    "L'édition des achats/ventes n'est pas supportée. "
                    "Veuillez supprimer et recréer la transaction.",
                    type='warning', timeout=5000
                )
                ui.timer(0.1, lambda: dialog.close(), once=True)

        if is_av_per:
            if not fonds_euros_dict:
                ui.label(
                    "⚠️ Aucun Fonds € n'existe. Créez-en un via Achat > Manuel "
                    "pour pouvoir faire des versements."
                ).classes('text-red-500 text-xs font-bold')
            else:
                fonds_euro_select = ui.select(
                    fonds_euros_dict,
                    label="Fonds € cible *",
                    value=list(fonds_euros_dict.keys())[0] if fonds_euros_dict else None
                ).classes('w-full')

        if chargeable_positions_options:
            # 🆕 Construire 2 dicts : un pour dividendes (avec historiques),
            # un pour frais en parts (sans historiques, car on ne peut pas
            # débiter des parts d'un titre qu'on ne détient plus)
            dividend_options = {}
            fees_options = {}
            for idx, d in chargeable_positions_options.items():
                if d.get('is_historical'):
                    # Préfixe visuel pour les titres historiques
                    dividend_options[idx] = f"📜 {d['nom']} (vendu)"
                else:
                    dividend_options[idx] = d['nom']
                    fees_options[idx] = d['nom']

            dividend_source_select = ui.select(
                dividend_options,
                label='Actif source du dividende *',
                value=data['source_position_id']
                if is_edit and data.get('source_position_id')
                and data['type_operation'] == 'dividende' else None
            ).classes('w-full')

            if fees_options:
                fees_asset_select = ui.select(
                    fees_options,
                    label='Actif à débiter (parts) *',
                    value=data['source_position_id']
                    if is_edit and data.get('source_position_id')
                    and data['type_operation'] == 'frais'
                    and not str(data.get('source_position_id', '')).startswith('HIST_')
                    else None
                ).classes('w-full')
        else:
            no_chargeable_assets_label = ui.label(
                "⚠️ Aucun actif (hors Cash/Fonds €) trouvé dans ce portefeuille."
            ).classes('text-red-500 text-xs font-bold')

        reinvest_checkbox = ui.checkbox(
            'Dividende réinvesti en parts', value=False
        ).classes('mt-0')

        fee_type_toggle = ui.toggle(
            {'cash': 'Frais en euros', 'parts': 'Frais en parts'},
            value=(data['initial_fee_type']
                   if is_edit and data['type_operation'] == 'frais' else 'cash'),
        ).classes('w-full').props('toggle-color="primary" spread')

        with ui.input('Date', value=date_initiale_fr).classes('w-full') \
                .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input_ui_element:
            with ui.menu().props('no-parent-event') as menu:
                date_picker = ui.date().bind_value(date_input_ui_element).props(
                    'mask="DD/MM/YYYY"'
                )
                with date_picker:
                    with ui.row().classes('justify-end'):
                        ui.button('Fermer', on_click=menu.close).props('flat')
            with date_input_ui_element.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        montant_input = ui.number('Montant (€)', value=data['montant'],
                                  format='%.2f', min=0).classes('w-full')
        dividend_per_share_input = ui.number('Dividende par part (€)', value=0.0,
                                             format='%.4f', min=0).classes('w-full')
        dividend_parts_input = ui.number('Nombre de parts réinvesties *', value=0.0,
                                         format='%.4f', min=0, step=0.01).classes('w-full')
        current_fees_parts_qty_label = ui.label(
            "Quantité actuelle : 0.0 parts"
        ).classes('text-sm text-gray-500')
        fees_parts_to_deduct_input = ui.number(
            'Quantité de parts à prélever *', value=0.0,
            format='%.4f', min=0, step=0.01
        ).classes('w-full')
        fees_final_parts_qty_input = ui.number(
            'Quantité finale de parts *', value=0.0,
            format='%.4f', min=0, step=0.01
        ).classes('w-full')
        libelle_input = ui.input('Libellé (optionnel)', value=data['libelle']).classes('w-full')
        frais_input = ui.number('⚠️ Frais associés (€)', value=frais_existants,
                                format='%.2f', min=0).classes('w-full')
        info_label = ui.label().classes(
            'text-xs px-3 py-2 rounded-lg whitespace-pre-line'
        ).style(f'background-color: {c["card_border"]}; color: {c["text_secondary"]};')

        def _is_historical_id(pid) -> bool:
            """Détecte si un id est un pseudo-id de titre historique."""
            return isinstance(pid, str) and pid.startswith('HIST_')

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
            current_qty = chargeable_positions_options.get(
                selected_id, {}).get('quantite', 0)
            current_fees_parts_qty_label.text = f"Quantité actuelle : {current_qty:g} parts"
            if current_qty > 0:
                if source_input == 'deduct_qty':
                    deduct_val = float(fees_parts_to_deduct_input.value or 0)
                    final_val = current_qty - deduct_val
                    last_fees_parts_input_changed['value'] = 'final_qty'
                    fees_final_parts_qty_input.value = round(max(0.0, final_val), 4)
                elif source_input == 'final_qty':
                    final_val = float(fees_final_parts_qty_input.value or 0)
                    deduct_val = current_qty - final_val
                    last_fees_parts_input_changed['value'] = 'deduct_qty'
                    fees_parts_to_deduct_input.value = round(max(0.0, deduct_val), 4)
            else:
                fees_parts_to_deduct_input.value = 0.0
                fees_final_parts_qty_input.value = 0.0

        def update_dividend_amounts(source_input):
            if type_input.value != 'dividende' or reinvest_checkbox.value:
                return
            if not dividend_source_select or not dividend_source_select.value:
                return
            # 🆕 Pour un titre historique, on ne calcule pas dividende/part
            # car la quantité actuelle est 0
            selected_id = dividend_source_select.value
            if _is_historical_id(selected_id):
                return
            if last_dividend_input_changed['value'] == source_input:
                last_dividend_input_changed['value'] = None
                return
            current_qty = chargeable_positions_options.get(
                selected_id, {}).get('quantite', 0)
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
            current_date_year = (
                date_input_ui_element.value[-4:]
                if len(date_input_ui_element.value) == 10 else ''
            )
            if current_type == 'versement':
                libelle_input.props('placeholder="ex: Versement programmé"')
            elif current_type == 'retrait':
                libelle_input.props('placeholder="ex: Retrait pour projet immobilier"')
            elif current_type == 'interets':
                libelle_input.props(
                    f'placeholder="ex: Intérêts annuels {current_date_year}"'
                )
            elif current_type == 'dividende':
                selected_id = (
                    dividend_source_select.value if dividend_source_select else None
                )
                source_name = chargeable_positions_options.get(
                    selected_id, {}).get('nom', 'Actif')
                if reinvest_checkbox.value:
                    libelle_input.props(
                        f'placeholder="ex: Dividende réinvesti {source_name}"'
                    )
                else:
                    libelle_input.props(
                        f'placeholder="ex: Dividende {source_name}"'
                    )
                if not reinvest_checkbox.value:
                    update_dividend_amounts('total')
            elif current_type == 'frais':
                selected_id = fees_asset_select.value if fees_asset_select else None
                source_name = chargeable_positions_options.get(
                    selected_id, {}).get('nom', 'Actif')
                if fee_type_toggle.value == 'parts':
                    libelle_input.props(
                        f'placeholder="ex: Frais de gestion - {source_name} (parts)"'
                    )
                    update_fees_parts_amounts('deduct_qty')
                else:
                    libelle_input.props('placeholder="ex: Frais de gestion annuels"')
            else:
                libelle_input.props('')

            if not libelle_input.value or \
                    (current_type == 'interets'
                     and libelle_input.value.startswith("Intérêts annuels")) or \
                    (current_type == 'dividende'
                     and libelle_input.value.startswith("Dividende -")) or \
                    (current_type == 'frais'
                     and libelle_input.value.startswith("Frais de gestion -")):
                if current_type == 'interets':
                    libelle_input.value = (
                        f"Intérêts annuels {current_date_year}"
                        if current_date_year else ""
                    )
                elif (current_type == 'dividende' and dividend_source_select
                      and dividend_source_select.value):
                    source_name = chargeable_positions_options[
                        dividend_source_select.value]['nom']
                    if reinvest_checkbox.value:
                        libelle_input.value = f"Dividende réinvesti - {source_name}"
                    else:
                        libelle_input.value = f"Dividende - {source_name}"
                elif current_type == 'frais':
                    selected_id = (
                        fees_asset_select.value if fees_asset_select else None
                    )
                    source_name = chargeable_positions_options.get(
                        selected_id, {}).get('nom', 'Actif')
                    if fee_type_toggle.value == 'parts':
                        libelle_input.value = (
                            f"Frais de gestion - {source_name} (parts)"
                        )
                    else:
                        libelle_input.value = (
                            f"Frais de gestion {current_date_year}"
                            if current_date_year else "Frais de gestion"
                        )

            if current_type not in ('interets', 'dividende', 'frais') and \
                    libelle_input.value.startswith(
                        ("Intérêts annuels", "Dividende -", "Frais de gestion -")):
                libelle_input.value = ''

        def update_visibility():
            val = type_input.value
            is_reinvesting_dividend = reinvest_checkbox.value and val == 'dividende'
            is_fees_in_parts = val == 'frais' and fee_type_toggle.value == 'parts'

            # 🆕 Si l'actif sélectionné pour un dividende est historique,
            # on désactive le réinvestissement (impossible sur un titre vendu)
            selected_div_id = (
                dividend_source_select.value if dividend_source_select else None
            )
            is_div_on_historical = (
                val == 'dividende'
                and selected_div_id is not None
                and _is_historical_id(selected_div_id)
            )
            if is_div_on_historical:
                if reinvest_checkbox.value:
                    reinvest_checkbox.value = False
                is_reinvesting_dividend = False
                reinvest_checkbox.disable()
                reinvest_checkbox.tooltip(
                    "Réinvestissement impossible sur un titre vendu"
                )
            else:
                reinvest_checkbox.enable()
                reinvest_checkbox.tooltip("")

            target_str = (
                "du Fonds € sélectionné"
                if is_av_per and not is_reinvesting_dividend and not is_fees_in_parts
                else 'de la position "Cash"'
            )

            if is_div_on_historical:
                info_label.text = (
                    f'📜 Dividende sur un titre historiquement détenu (vendu). '
                    f'Le montant viendra alimenter le solde {target_str}.'
                )
            elif is_reinvesting_dividend:
                info_label.text = (
                    f'🎁 Le dividende sera réinvesti en parts de l\'actif. '
                    f'Pas d\'impact sur le solde {target_str}.'
                )
            elif is_fees_in_parts:
                info_label.text = (
                    f'⚠️ Les frais seront prélevés en parts de l\'actif sélectionné. '
                    f'Pas d\'impact sur le solde {target_str}.'
                )
            else:
                messages = {
                    'versement': f'💰 Le montant viendra alimenter le solde {target_str}',
                    'retrait': f'💸 Le montant sera prélevé {target_str}',
                    'achat': '🛒 Achat (formulaire dédié)',
                    'vente': '💹 Vente (formulaire dédié)',
                    'dividende': (
                        f'🎁 Le dividende viendra alimenter le solde {target_str} '
                        f'et sera lié à l\'actif source.'
                    ),
                    'frais': f'⚠️ Les frais seront prélevés {target_str}',
                    'interets': (
                        '📈 Les intérêts annuels viendront s\'ajouter au Fonds € '
                        '(n\'impacte pas le Total Versé pour les perfs)'
                    ),
                }
                info_label.text = messages.get(val, '')

            is_visible_for_flux = val not in ('achat', 'vente')
            date_input_ui_element.set_visibility(is_visible_for_flux)
            libelle_input.set_visibility(is_visible_for_flux)
            frais_input.set_visibility(False)

            if val == 'dividende':
                if dividend_source_select:
                    dividend_source_select.set_visibility(True)
                if no_chargeable_assets_label:
                    no_chargeable_assets_label.set_visibility(
                        not chargeable_positions_options and not is_av_per)
                reinvest_checkbox.set_visibility(True)
                montant_input.set_visibility(not is_reinvesting_dividend)
                # 🆕 Ne pas montrer "dividende/part" pour les titres historiques
                dividend_per_share_input.set_visibility(
                    not is_reinvesting_dividend and not is_div_on_historical
                )
                dividend_parts_input.set_visibility(is_reinvesting_dividend)
                if fees_asset_select:
                    fees_asset_select.set_visibility(False)
                fee_type_toggle.set_visibility(False)
                current_fees_parts_qty_label.set_visibility(False)
                fees_parts_to_deduct_input.set_visibility(False)
                fees_final_parts_qty_input.set_visibility(False)
            elif val == 'frais':
                if dividend_source_select:
                    dividend_source_select.set_visibility(False)
                reinvest_checkbox.set_visibility(False)
                dividend_per_share_input.set_visibility(False)
                dividend_parts_input.set_visibility(False)
                fee_type_toggle.set_visibility(True)
                if no_chargeable_assets_label:
                    no_chargeable_assets_label.set_visibility(
                        not chargeable_positions_options
                        and fee_type_toggle.value == 'parts')
                if fee_type_toggle.value == 'cash':
                    montant_input.set_visibility(True)
                    if fees_asset_select:
                        fees_asset_select.set_visibility(False)
                    current_fees_parts_qty_label.set_visibility(False)
                    fees_parts_to_deduct_input.set_visibility(False)
                    fees_final_parts_qty_input.set_visibility(False)
                else:
                    montant_input.set_visibility(False)
                    if fees_asset_select:
                        fees_asset_select.set_visibility(True)
                    current_fees_parts_qty_label.set_visibility(True)
                    fees_parts_to_deduct_input.set_visibility(True)
                    fees_final_parts_qty_input.set_visibility(True)
            else:
                if dividend_source_select:
                    dividend_source_select.set_visibility(False)
                if fees_asset_select:
                    fees_asset_select.set_visibility(False)
                if no_chargeable_assets_label:
                    no_chargeable_assets_label.set_visibility(False)
                reinvest_checkbox.set_visibility(False)
                fee_type_toggle.set_visibility(False)
                montant_input.set_visibility(is_visible_for_flux)
                dividend_per_share_input.set_visibility(False)
                dividend_parts_input.set_visibility(False)
                current_fees_parts_qty_label.set_visibility(False)
                fees_parts_to_deduct_input.set_visibility(False)
                fees_final_parts_qty_input.set_visibility(False)

            if is_av_per and fonds_euro_select:
                fonds_euro_select.set_visibility(
                    val in ('versement', 'retrait', 'interets') or
                    (val == 'dividende' and not is_reinvesting_dividend) or
                    (val == 'frais' and not is_fees_in_parts)
                )

            update_dynamic_fields()

        type_input.on('update:model-value', update_visibility)
        if dividend_source_select:
            dividend_source_select.on('update:model-value', update_visibility)
            dividend_source_select.on('update:model-value', update_dynamic_fields)
        montant_input.on('update:model-value', lambda: update_dividend_amounts('total'))
        dividend_per_share_input.on('update:model-value',
                                    lambda: update_dividend_amounts('per_share'))
        reinvest_checkbox.on('update:model-value', update_visibility)
        fee_type_toggle.on('update:model-value', update_visibility)
        if fees_asset_select:
            fees_asset_select.on('update:model-value',
                                 lambda: update_fees_parts_amounts('deduct_qty'))
            fees_asset_select.on('update:model-value', update_dynamic_fields)
        fees_parts_to_deduct_input.on('update:model-value',
                                      lambda: update_fees_parts_amounts('deduct_qty'))
        fees_final_parts_qty_input.on('update:model-value',
                                      lambda: update_fees_parts_amounts('final_qty'))
        date_input_ui_element.on('update:model-value', update_dynamic_fields)
        date_picker.on('update:model-value', update_dynamic_fields)

        update_visibility()

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat')

            async def save():
                try:
                    date_val = datetime.strptime(
                        date_input_ui_element.value, '%d/%m/%Y'
                    ).date()
                except (ValueError, TypeError):
                    ui.notify('Date invalide', type='negative')
                    return

                type_val = type_input.value
                is_reinvesting_current_state = (
                    reinvest_checkbox.value and type_val == 'dividende'
                )
                is_fees_in_parts_current_state = (
                    fee_type_toggle.value == 'parts' and type_val == 'frais'
                )

                montant_val_for_tx = float(montant_input.value or 0)
                parts_reinvesties = float(dividend_parts_input.value or 0)
                parts_a_prelever_frais = float(fees_parts_to_deduct_input.value or 0)

                # Validations
                if type_val == 'dividende':
                    if not dividend_source_select or not dividend_source_select.value:
                        ui.notify("Veuillez sélectionner l'actif source du dividende.",
                                  type='negative')
                        return
                    # 🆕 Réinvestissement interdit sur titre historique
                    selected_div_id = dividend_source_select.value
                    if _is_historical_id(selected_div_id) and is_reinvesting_current_state:
                        ui.notify(
                            "Impossible de réinvestir un dividende sur un titre vendu.",
                            type='negative'
                        )
                        return
                    if is_reinvesting_current_state:
                        if not parts_reinvesties or parts_reinvesties <= 0:
                            ui.notify("Le nombre de parts doit être > 0.", type='negative')
                            return
                    else:
                        if not montant_val_for_tx or montant_val_for_tx <= 0:
                            ui.notify("Le montant doit être positif.", type='negative')
                            return
                        if is_av_per and (
                                not fonds_euro_select or not fonds_euro_select.value):
                            ui.notify("Sélectionnez un Fonds € cible.", type='negative')
                            return
                elif type_val == 'frais':
                    if is_fees_in_parts_current_state:
                        if not fees_asset_select or not fees_asset_select.value:
                            ui.notify("Sélectionnez l'actif à débiter.", type='negative')
                            return
                        if not parts_a_prelever_frais or parts_a_prelever_frais <= 0:
                            ui.notify("La quantité doit être > 0.", type='negative')
                            return
                        selected_asset_qty = chargeable_positions_options.get(
                            fees_asset_select.value, {}).get('quantite', 0)
                        if parts_a_prelever_frais > selected_asset_qty:
                            ui.notify(
                                f"Parts insuffisantes. Dispo: {selected_asset_qty:g}",
                                type='negative')
                            return
                    else:
                        if not montant_val_for_tx or montant_val_for_tx <= 0:
                            ui.notify("Le montant doit être positif.", type='negative')
                            return
                        if is_av_per and (
                                not fonds_euro_select or not fonds_euro_select.value):
                            ui.notify("Sélectionnez un Fonds € cible.", type='negative')
                            return
                else:
                    if not montant_val_for_tx or montant_val_for_tx <= 0:
                        ui.notify("Le montant doit être positif.", type='negative')
                        return
                    if is_av_per and (
                            not fonds_euro_select or not fonds_euro_select.value):
                        ui.notify("Sélectionnez un Fonds € cible.", type='negative')
                        return

                has_ticker = False

                with get_session() as session:
                    def update_fonds_euro(fe_id, type_op, montant):
                        fe = session.get(Position, fe_id)
                        if not fe:
                            return
                        if type_op in ['versement', 'dividende', 'interets']:
                            fe.quantite += montant
                        elif type_op in ['retrait', 'frais']:
                            fe.quantite -= montant

                    if is_edit:
                        ui.notify(
                            "L'édition n'est pas supportée. "
                            "Supprimez et recréez la transaction.",
                            type='warning'
                        )
                        return

                    libelle = libelle_input.value
                    if not libelle:
                        if type_val == 'interets':
                            libelle = f"Intérêts annuels {date_val.year}"
                        elif type_val == 'dividende':
                            selected_source_name = chargeable_positions_options.get(
                                dividend_source_select.value)['nom']
                            libelle = (
                                f"Dividende réinvesti - {selected_source_name}"
                                if is_reinvesting_current_state
                                else f"Dividende - {selected_source_name}"
                            )
                        elif type_val == 'versement':
                            libelle = 'Versement'
                        elif type_val == 'retrait':
                            libelle = 'Retrait'
                        elif type_val == 'frais':
                            selected_source_name = (
                                chargeable_positions_options.get(
                                    fees_asset_select.value)['nom']
                                if fees_asset_select and fees_asset_select.value
                                else 'Génériques'
                            )
                            libelle = (
                                f"Frais de gestion - {selected_source_name} (parts)"
                                if is_fees_in_parts_current_state
                                else f"Frais de gestion {date_val.year}"
                            )

                    t_final = None

                    if type_val == 'dividende':
                        # 🆕 Gérer le cas titre historique (pseudo_id 'HIST_xxx')
                        selected_div_id = dividend_source_select.value

                        if _is_historical_id(selected_div_id):
                            # Titre vendu : on récupère les infos depuis l'option
                            hist_info = chargeable_positions_options[selected_div_id]
                            t_final = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='dividende',
                                montant=montant_val_for_tx,
                                libelle=libelle,
                                nom_titre=hist_info['nom'],
                                ticker=hist_info['ticker'],
                                code=hist_info['code'],
                                categorie=hist_info['categorie'],
                                quantite=None, prix_unitaire=None,
                            )
                            session.add(t_final)
                            session.flush()
                            if is_av_per:
                                update_fonds_euro(
                                    fonds_euro_select.value, type_val,
                                    montant_val_for_tx)
                            else:
                                ajuster_cash(session, portefeuille_id,
                                             impact_cash(type_val, montant_val_for_tx))
                        else:
                            # Cas standard : Position active
                            source_pos_for_tx = session.get(
                                Position, dividend_source_select.value
                            )
                            if is_reinvesting_current_state:
                                price_at_reinvestment = source_pos_for_tx.cours_actuel or 0
                                if price_at_reinvestment == 0:
                                    ui.notify(
                                        f"Cours actuel de {source_pos_for_tx.nom} = 0.",
                                        type='negative')
                                    session.rollback()
                                    return
                                montant_total = parts_reinvesties * price_at_reinvestment
                                old_qty = source_pos_for_tx.quantite or 0
                                old_pru = source_pos_for_tx.prix_moyen or 0
                                new_qty = old_qty + parts_reinvesties
                                new_pru = (
                                    ((old_qty * old_pru) +
                                     (parts_reinvesties * price_at_reinvestment))
                                    / new_qty if new_qty > 0 else price_at_reinvestment
                                )
                                source_pos_for_tx.quantite = new_qty
                                source_pos_for_tx.prix_moyen = new_pru
                                t_final = Transaction(
                                    portefeuille_id=portefeuille_id,
                                    date_operation=date_val,
                                    type_operation='dividende',
                                    montant=montant_total,
                                    libelle=libelle,
                                    nom_titre=source_pos_for_tx.nom,
                                    ticker=source_pos_for_tx.ticker,
                                    code=source_pos_for_tx.code,
                                    categorie=source_pos_for_tx.categorie,
                                    quantite=parts_reinvesties,
                                    prix_unitaire=price_at_reinvestment,
                                )
                                session.add(t_final)
                            else:
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
                                    quantite=None, prix_unitaire=None,
                                )
                                session.add(t_final)
                                session.flush()
                                if is_av_per:
                                    update_fonds_euro(
                                        fonds_euro_select.value, type_val,
                                        montant_val_for_tx)
                                else:
                                    ajuster_cash(session, portefeuille_id,
                                                 impact_cash(type_val, montant_val_for_tx))

                    elif type_val == 'frais':
                        if is_fees_in_parts_current_state:
                            source_pos = session.get(Position, fees_asset_select.value)
                            price_at_deduction = source_pos.cours_actuel or 0
                            if price_at_deduction == 0:
                                ui.notify(
                                    f"Cours actuel de {source_pos.nom} = 0.",
                                    type='negative')
                                session.rollback()
                                return
                            montant_frais = parts_a_prelever_frais * price_at_deduction
                            source_pos.quantite -= parts_a_prelever_frais
                            t_final = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='frais',
                                montant=montant_frais,
                                libelle=libelle,
                                nom_titre=source_pos.nom,
                                ticker=source_pos.ticker,
                                code=source_pos.code,
                                categorie=source_pos.categorie,
                                quantite=parts_a_prelever_frais,
                                prix_unitaire=price_at_deduction,
                            )
                            session.add(t_final)
                        else:
                            t_final = Transaction(
                                portefeuille_id=portefeuille_id,
                                date_operation=date_val,
                                type_operation='frais',
                                montant=montant_val_for_tx,
                                libelle=libelle,
                                nom_titre=(
                                    fonds_euros_dict.get(fonds_euro_select.value)
                                    if (is_av_per and fonds_euro_select
                                        and fonds_euro_select.value) else None
                                ),
                                categorie=(
                                    'Fonds Euro'
                                    if (is_av_per and fonds_euro_select
                                        and fonds_euro_select.value) else None
                                ),
                                quantite=(
                                    montant_val_for_tx
                                    if (is_av_per and fonds_euro_select
                                        and fonds_euro_select.value) else None
                                ),
                                prix_unitaire=(
                                    1.0
                                    if (is_av_per and fonds_euro_select
                                        and fonds_euro_select.value) else None
                                ),
                            )
                            session.add(t_final)
                            session.flush()
                            if is_av_per:
                                update_fonds_euro(
                                    fonds_euro_select.value, type_val,
                                    montant_val_for_tx)
                            else:
                                ajuster_cash(session, portefeuille_id,
                                             impact_cash(type_val, montant_val_for_tx))
                    else:
                        t_final = Transaction(
                            portefeuille_id=portefeuille_id,
                            date_operation=date_val,
                            type_operation=type_val,
                            montant=montant_val_for_tx,
                            libelle=libelle,
                        )
                        if is_av_per and fonds_euro_select and fonds_euro_select.value:
                            target_fe = session.get(Position, fonds_euro_select.value)
                            if target_fe:
                                t_final.nom_titre = target_fe.nom
                                t_final.categorie = 'Fonds Euro'
                                t_final.quantite = montant_val_for_tx
                                t_final.prix_unitaire = 1.0
                        session.add(t_final)
                        session.flush()
                        if is_av_per:
                            update_fonds_euro(
                                fonds_euro_select.value, type_val, montant_val_for_tx)
                        else:
                            ajuster_cash(session, portefeuille_id,
                                         impact_cash(type_val, montant_val_for_tx))

                    if t_final is not None:
                        if t_final.ticker:
                            has_ticker = True
                        elif (t_final.nom_titre and
                              t_final.categorie not in (
                                  'Fonds Euro', 'Fonds €', 'Cash')):
                            check_pos = session.execute(
                                select(Position).where(
                                    Position.portefeuille_id == portefeuille_id,
                                    Position.nom == t_final.nom_titre,
                                )
                            ).scalar_one_or_none()
                            if check_pos and check_pos.ticker:
                                has_ticker = True

                    session.commit()

                ui.notify('Transaction ajoutée', type='positive')
                dialog.close()
                refresh()

                asyncio.create_task(
                    _run_backfill_async(portefeuille_id, need_cours=has_ticker)
                )

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
        ui.label('Le solde de cash sera ajusté en conséquence.').classes('text-sm').style(
            'color: #f59e0b'
        )

        async def do_delete():
            has_ticker = False
            ptf_id_for_backfill = None

            with get_session() as session:
                t = session.get(Transaction, transaction_id)
                if not t:
                    return

                portefeuille = session.get(Portefeuille, t.portefeuille_id)
                is_av_per_for_tx = portefeuille.type in [
                    'Assurance-Vie', 'AV', 'PER', 'Assurance Vie'
                ]

                if t.type_operation == 'achat':
                    if t.quantite and t.nom_titre:
                        bought_pos = session.execute(
                            select(Position).where(
                                Position.portefeuille_id == t.portefeuille_id,
                                Position.nom == t.nom_titre,
                            )
                        ).scalar_one_or_none()
                        if bought_pos:
                            new_qty = (bought_pos.quantite or 0) - t.quantite
                            if new_qty <= 0.0001:
                                session.delete(bought_pos)
                            else:
                                old_qty = bought_pos.quantite or 0
                                old_pru = bought_pos.prix_moyen or 0
                                old_invest = old_qty * old_pru
                                cancelled = t.quantite * (t.prix_unitaire or 0)
                                new_invest = old_invest - cancelled
                                bought_pos.quantite = new_qty
                                bought_pos.prix_moyen = (
                                    new_invest / new_qty if new_qty > 0 else 0
                                )

                    for child in list(t.children):
                        if child.type_operation == 'vente' and is_av_per_for_tx:
                            if child.nom_titre and child.quantite:
                                fe_pos = session.execute(
                                    select(Position).where(
                                        Position.portefeuille_id == child.portefeuille_id,
                                        Position.nom == child.nom_titre,
                                        Position.categorie.in_(
                                            ['Fonds €', 'Fonds Euro']),
                                    )
                                ).scalar_one_or_none()
                                if fe_pos:
                                    fe_pos.quantite += child.quantite
                        elif child.type_operation == 'frais':
                            if is_av_per_for_tx:
                                if child.nom_titre and child.quantite:
                                    charged = session.execute(
                                        select(Position).where(
                                            Position.portefeuille_id == child.portefeuille_id,
                                            Position.nom == child.nom_titre,
                                        )
                                    ).scalar_one_or_none()
                                    if charged:
                                        charged.quantite += child.quantite
                            else:
                                inv = -impact_cash(child.type_operation, child.montant)
                                ajuster_cash(session, child.portefeuille_id, inv)
                        session.delete(child)

                    if not is_av_per_for_tx:
                        inv = -impact_cash('achat', t.montant)
                        ajuster_cash(session, t.portefeuille_id, inv)

                elif t.type_operation == 'vente':
                    if t.quantite and t.nom_titre and t.prix_unitaire:
                        sold_pos = session.execute(
                            select(Position).where(
                                Position.portefeuille_id == t.portefeuille_id,
                                Position.nom == t.nom_titre,
                            )
                        ).scalar_one_or_none()
                        if sold_pos:
                            sold_pos.quantite += t.quantite
                        else:
                            new_pos = Position(
                                portefeuille_id=t.portefeuille_id,
                                nom=t.nom_titre,
                                ticker=t.ticker,
                                code=t.code,
                                categorie=t.categorie,
                                quantite=t.quantite,
                                prix_moyen=t.prix_unitaire,
                                cours_actuel=t.prix_unitaire,
                            )
                            session.add(new_pos)

                    for child in list(t.children):
                        if child.type_operation == 'versement' and is_av_per_for_tx:
                            if child.nom_titre and child.quantite:
                                fe_pos = session.execute(
                                    select(Position).where(
                                        Position.portefeuille_id == child.portefeuille_id,
                                        Position.nom == child.nom_titre,
                                        Position.categorie.in_(
                                            ['Fonds €', 'Fonds Euro']),
                                    )
                                ).scalar_one_or_none()
                                if fe_pos:
                                    fe_pos.quantite -= child.quantite
                        elif child.type_operation == 'frais':
                            if is_av_per_for_tx:
                                if child.nom_titre and child.quantite:
                                    charged = session.execute(
                                        select(Position).where(
                                            Position.portefeuille_id == child.portefeuille_id,
                                            Position.nom == child.nom_titre,
                                        )
                                    ).scalar_one_or_none()
                                    if charged:
                                        charged.quantite += child.quantite
                            else:
                                inv = -impact_cash(child.type_operation, child.montant)
                                ajuster_cash(session, child.portefeuille_id, inv)
                        session.delete(child)

                    if not is_av_per_for_tx:
                        inv = -impact_cash('vente', t.montant)
                        ajuster_cash(session, t.portefeuille_id, inv)

                elif (t.type_operation == 'dividende' and t.quantite
                      and t.quantite > 0 and t.prix_unitaire
                      and t.prix_unitaire > 0 and t.nom_titre):
                    source_pos = session.execute(
                        select(Position).where(
                            Position.portefeuille_id == t.portefeuille_id,
                            Position.nom == t.nom_titre,
                        )
                    ).scalar_one_or_none()
                    if source_pos:
                        parts = t.quantite
                        old_qty = source_pos.quantite or 0
                        old_pru = source_pos.prix_moyen or 0
                        if old_qty <= parts:
                            source_pos.quantite = 0
                            source_pos.prix_moyen = 0
                        else:
                            new_qty = old_qty - parts
                            new_pru = (
                                ((old_qty * old_pru) - (parts * t.prix_unitaire))
                                / new_qty if new_qty > 0 else 0
                            )
                            source_pos.quantite = new_qty
                            source_pos.prix_moyen = new_pru

                elif (t.type_operation == 'frais' and t.quantite
                      and t.quantite > 0 and t.prix_unitaire
                      and t.prix_unitaire > 0 and t.nom_titre
                      and t.categorie not in ('Fonds €', 'Fonds Euro')):
                    source_pos = session.execute(
                        select(Position).where(
                            Position.portefeuille_id == t.portefeuille_id,
                            Position.nom == t.nom_titre,
                        )
                    ).scalar_one_or_none()
                    if source_pos:
                        source_pos.quantite += t.quantite

                elif (is_av_per_for_tx and t.nom_titre
                      and t.categorie in ('Fonds €', 'Fonds Euro')):
                    fe_pos = session.execute(
                        select(Position).where(
                            Position.portefeuille_id == t.portefeuille_id,
                            Position.nom == t.nom_titre,
                            Position.categorie.in_(['Fonds €', 'Fonds Euro']),
                        )
                    ).scalar_one_or_none()
                    if fe_pos:
                        if t.type_operation in ('versement', 'dividende', 'interets'):
                            fe_pos.quantite -= t.montant
                        elif t.type_operation in ('retrait', 'frais'):
                            fe_pos.quantite += t.montant
                    for child in list(t.children):
                        if child.type_operation == 'frais' and fe_pos:
                            fe_pos.quantite += child.montant
                        session.delete(child)

                else:
                    for child in list(t.children):
                        if child.type_operation == 'frais':
                            inv = -impact_cash(child.type_operation, child.montant)
                            ajuster_cash(session, child.portefeuille_id, inv)
                        session.delete(child)
                    if not is_av_per_for_tx:
                        inv = -impact_cash(t.type_operation, t.montant)
                        ajuster_cash(session, t.portefeuille_id, inv)

                has_ticker = bool(t.ticker)
                if not has_ticker and t.nom_titre \
                        and t.categorie not in ('Fonds Euro', 'Fonds €', 'Cash'):
                    check_pos = session.execute(
                        select(Position).where(
                            Position.portefeuille_id == t.portefeuille_id,
                            Position.nom == t.nom_titre,
                        )
                    ).scalar_one_or_none()
                    if check_pos and check_pos.ticker:
                        has_ticker = True

                ptf_id_for_backfill = t.portefeuille_id
                session.delete(t)
                session.commit()

            ui.notify(f'"{libelle}" supprimée', type='warning')
            dialog.close()
            refresh()

            if ptf_id_for_backfill is not None:
                asyncio.create_task(
                    _run_backfill_async(ptf_id_for_backfill, need_cours=has_ticker)
                )

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Annuler', on_click=dialog.close).props('flat')
            ui.button('Supprimer', on_click=do_delete).props('unelevated') \
                .classes('bg-red-600 text-white')

    dialog.open()