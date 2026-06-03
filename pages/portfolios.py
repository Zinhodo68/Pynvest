import uuid
from datetime import date, datetime
from pathlib import Path

from nicegui import ui, events
from sqlalchemy import select, func

from components.layout import page_layout
from components.refresh import refresh_layout
from theme import get_colors
from database.db import get_session, get_all_membres
from database.models import Membre, Portefeuille
from pages.portefeuilles_data import TYPES_PORTEFEUILLE, get_type_info
from pages.portefeuille_detail._chart import render_chart

from utils.formatters import format_money, format_percent, format_date_fr, get_perf_color

UPLOADS_DIR = Path(__file__).parent.parent / 'uploads' / 'logos'
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def render(member: str = None):
    route = f'/portefeuilles/{member}' if member else '/portefeuilles'
    is_dark = page_layout(active_route=route)
    c = get_colors(is_dark)

    membre_data = None
    if member:
        with get_session() as session:
            stmt = select(Membre).where(func.lower(Membre.prenom) == member.lower())
            m = session.execute(stmt).scalar_one_or_none()
            if m:
                membre_data = m.to_dict()

    container = ui.column().classes('w-full p-6 gap-4')

    def refresh():
        container.clear()
        with container:
            _render_content(c, is_dark, refresh, membre_data, member)

    refresh()


# ─────────────────────────────────────────────
# Contenu principal
# ─────────────────────────────────────────────

def _render_content(c, is_dark, refresh, membre_data, member_param):
    # En-tête
    with ui.row().classes('w-full items-center justify-between'):
        with ui.row().classes('items-center gap-4'):
            if membre_data:
                with ui.element('div').classes(
                    'w-14 h-14 rounded-full flex items-center justify-center'
                ).style(f'background-color: {membre_data["couleur"]}'):
                    ui.label(membre_data['initiales']).classes(
                        'text-white font-bold text-lg'
                    )
                with ui.column().classes('gap-0'):
                    ui.label(f'Portefeuilles de {membre_data["prenom"]}') \
                        .classes('text-2xl font-bold').style(f'color: {c["text_primary"]}')
                    ui.label(membre_data['role']).style(f'color: {c["text_secondary"]}')
            elif member_param and not membre_data:
                ui.label(f'Membre "{member_param}" introuvable') \
                    .classes('text-2xl font-bold').style(f'color: {c["text_primary"]}')
            else:
                with ui.column().classes('gap-1'):
                    ui.label('Tous les portefeuilles').classes('text-2xl font-bold').style(
                        f'color: {c["text_primary"]}'
                    )
                    ui.label("Vue d'ensemble de tous les portefeuilles familiaux.") \
                        .style(f'color: {c["text_secondary"]}')

        ui.button(
            '+ Nouveau portefeuille',
            on_click=lambda: _open_dialog(
                c, refresh,
                default_membre_id=membre_data['id'] if membre_data else None
            )
        ).props('unelevated').classes('bg-blue-600 text-white')

    # ──────────────────────────────────────────────────────────────────
    # Récupération des portefeuilles + stats pré-calculées
    # ⚡ 1 requête SQL agrégée au lieu de ~4N lazy-loads
    # ──────────────────────────────────────────────────────────────────
    with get_session() as session:
        from sqlalchemy.orm import selectinload
        from services.portfolio_stats import preload_stats

        stmt = (
            select(Portefeuille)
            .options(
                selectinload(Portefeuille.proprietaire),
                selectinload(Portefeuille.valorisations),
                selectinload(Portefeuille.transactions),
            )
            .order_by(Portefeuille.id)
        )
        if membre_data:
            stmt = stmt.where(Portefeuille.proprietaire_id == membre_data['id'])

        portefeuilles = session.execute(stmt).scalars().all()

        # ⚡ Pré-charge valorisation, total_verse, nb_transactions en 1 query
        preload_stats(session, portefeuilles)



        # Historique agrégé du patrimoine (sur les portefeuilles affichés)
        patrimoine_valorisations, patrimoine_transactions = _build_patrimoine_chart_data(portefeuilles)

        # to_dict() utilise le cache → 0 lazy-load
        portefeuilles_data = []
        for item in portefeuilles:
            if isinstance(item, dict):
                portefeuilles_data.append(item)
            elif hasattr(item, "to_dict") and callable(item.to_dict):
                portefeuilles_data.append(
                    item.to_dict(include_rendement_annualise=False)
                )
            else:
                # Dernier recours : on essaie de convertir en dict
                try:
                    portefeuilles_data.append(dict(item))
                except Exception:
                    portefeuilles_data.append(item)

    if not portefeuilles_data:
        with ui.card().classes('w-full p-12 rounded-xl items-center').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]};'
        ):
            ui.icon('account_balance_wallet').classes('text-6xl').style(
                f'color: {c["text_secondary"]}'
            )
            ui.label('Aucun portefeuille').classes('text-lg mt-4').style(
                f'color: {c["text_primary"]}'
            )
            ui.label('Cliquez sur "Nouveau portefeuille" pour commencer.').style(
                f'color: {c["text_secondary"]}'
            )
        return

    # 📊 Bandeau de KPIs globaux
    _render_kpi_bandeau(portefeuilles_data, c, is_dark)

    # 📈 Bandeau dépliable d'évolution du patrimoine agrégé
    _render_patrimoine_chart_card(
        patrimoine_valorisations,
        patrimoine_transactions,
        c,
        is_dark,
    )

    # Grille des portefeuilles
    with ui.row().classes('w-full gap-4 flex-wrap'):
        for p in portefeuilles_data:
            _render_portefeuille_card(p, c, is_dark, refresh)


# ─────────────────────────────────────────────
# Graphique patrimoine agrégé
# ─────────────────────────────────────────────

def _build_patrimoine_chart_data(portefeuilles):
    """Construit les séries agrégées pour le graphique patrimoine.

    Pour chaque date de valorisation connue, on additionne la dernière
    valorisation disponible de chaque portefeuille affiché. Les transactions
    sont concaténées pour permettre au graphique de recalculer le capital
    investi et la performance globale.
    """
    valos_by_portefeuille = {}
    all_valo_dates = set()
    transactions = []

    for p in portefeuilles:
        p_valos = []
        for v in getattr(p, 'valorisations', []) or []:
            if not v.date_valeur:
                continue
            date_iso = v.date_valeur.isoformat()
            p_valos.append((date_iso, float(v.montant or 0)))
            all_valo_dates.add(date_iso)

        valos_by_portefeuille[p.id] = sorted(p_valos, key=lambda item: item[0])

        for t in getattr(p, 'transactions', []) or []:
            if not t.date_operation:
                continue
            transactions.append({
                'id': t.id,
                'date': t.date_operation.isoformat(),
                'type': t.type_operation,
                'montant': float(t.montant or 0),
                'libelle': t.libelle,
                'parent_transaction_id': t.parent_transaction_id,
            })

    aggregate_valorisations = []
    last_by_portefeuille = {pid: 0.0 for pid in valos_by_portefeuille}
    index_by_portefeuille = {pid: 0 for pid in valos_by_portefeuille}

    for date_iso in sorted(all_valo_dates):
        for pid, p_valos in valos_by_portefeuille.items():
            idx = index_by_portefeuille[pid]
            while idx < len(p_valos) and p_valos[idx][0] <= date_iso:
                last_by_portefeuille[pid] = p_valos[idx][1]
                idx += 1
            index_by_portefeuille[pid] = idx

        aggregate_valorisations.append({
            'date': date_iso,
            'montant': round(sum(last_by_portefeuille.values()), 2),
        })

    return aggregate_valorisations, sorted(transactions, key=lambda t: t['date'])


def _render_patrimoine_chart_card(valorisations, transactions, c, is_dark):
    """Bandeau dépliable d'évolution du patrimoine global."""
    accent_color = '#3b82f6'

    with ui.card().classes('w-full p-0 rounded-xl overflow-hidden').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]};'
    ):
        with ui.expansion(
            text='Évolution du patrimoine',
            icon='show_chart',
            value=False,
        ).classes('w-full').style(
            f'color: {c["text_primary"]};'
        ) as expansion:
            expansion.props('dense header-class="text-lg font-bold"')

            if not valorisations:
                with ui.column().classes('w-full items-center py-8 gap-2'):
                    ui.icon('show_chart').classes('text-5xl').style(
                        f'color: {c["text_secondary"]}'
                    )
                    ui.label('Aucune valorisation enregistrée').style(
                        f'color: {c["text_secondary"]}'
                    )
            else:
                with ui.column().classes('w-full px-4 pb-4'):
                    render_chart(
                        valorisations,
                        transactions,
                        accent_color,
                        c,
                        is_dark,
                    )


# ─────────────────────────────────────────────
# KPIs globaux
# ─────────────────────────────────────────────

def _render_kpi_bandeau(portefeuilles_data, c, is_dark):
    """Bandeau de KPIs agrégés au-dessus de la grille."""
    from services.perf_xirr import get_xirr_for_portefeuilles

    total_valo = sum(p['valorisation_actuelle'] for p in portefeuilles_data)
    total_verse = sum(p['total_verse'] for p in portefeuilles_data)
    total_pv = total_valo - total_verse
    perf_pct = (total_pv / total_verse * 100) if total_verse > 0 else 0

    portefeuille_ids = [p['id'] for p in portefeuilles_data]
    rendement_annualise_global = get_xirr_for_portefeuilles(
        portefeuille_ids,
        current_value=total_valo,
    )

    kpis = [
        (
            'Patrimoine total',
            format_money(total_valo),
            'account_balance_wallet',
            '#3b82f6',
        ),
        (
            'Capital investi',
            format_money(total_verse),
            'savings',
            '#a855f7',
        ),
        (
            '+/- value latente',
            format_money(total_pv),
            'trending_up' if total_pv >= 0 else 'trending_down',
            get_perf_color(total_pv),
        ),
        (
            'Performance',
            format_percent(perf_pct),
            'percent',
            get_perf_color(perf_pct),
        ),
        (
            'TRI annualisé',
            format_percent(rendement_annualise_global)
            if rendement_annualise_global is not None else '—',
            'speed',
            get_perf_color(rendement_annualise_global)
            if rendement_annualise_global is not None else '#64748b',
        ),
        (
            'Nb portefeuilles',
            str(len(portefeuilles_data)),
            'wallet',
            '#64748b',
        ),
    ]

    with ui.row().classes('w-full flex-wrap gap-4 mb-2'):
        for title, value, icon, color in kpis:
            with ui.card().classes('flex-1 min-w-[150px] p-4 gap-1').style(
                f'background-color: {c["card_bg"]}; border: 1px solid {c["card_border"]};'
            ):
                with ui.row().classes('items-center gap-2 w-full justify-between'):
                    ui.label(title).classes('text-xs font-semibold uppercase tracking-wider').style(f'color: {c["text_secondary"]}')
                    ui.icon(icon).classes('text-lg').style(f'color: {color}')
                ui.label(value).classes('text-xl font-bold').style(f'color: {c["text_primary"]}')

# ─────────────────────────────────────────────
# Carte portefeuille
# ─────────────────────────────────────────────

def _render_portefeuille_card(p, c, is_dark, refresh):
    type_info = get_type_info(p['type'])
    accent_color = type_info['couleur']
    perf_color = get_perf_color(p['plus_value'])
    is_positive = p['plus_value'] >= 0

    # Carte cliquable qui mène au détail
    with ui.card().classes(
        'p-0 rounded-xl overflow-hidden cursor-pointer transition'
    ).style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'width: 340px; '
        f'transition: transform 0.15s, box-shadow 0.15s;'
    ).on('mouseenter', lambda card=None: None) \
     .on('click', lambda pid=p['id']: ui.navigate.to(f'/portefeuille/{pid}')):

        # Bandeau coloré + actions
        with ui.element('div').classes('w-full px-5 py-3').style(
            f'background: linear-gradient(135deg, {accent_color}, {accent_color}cc);'
        ):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon(type_info['icon']).classes('text-white text-base')
                    ui.label(p['type']).classes(
                        'text-white text-xs font-bold tracking-wider uppercase'
                    )

                # Menu actions
                menu_btn = ui.button(icon='more_vert').props(
                    'flat round dense size=sm'
                ).style('color: white;')
                menu_btn.on('click.stop', lambda: None)
                with menu_btn:
                    with ui.menu():
                        ui.menu_item(
                            'Voir le détail',
                            on_click=lambda pid=p['id']:
                            ui.navigate.to(f'/portefeuille/{pid}')
                        )
                        if p['url_gestion']:
                            ui.menu_item(
                                'Ouvrir le site',
                                on_click=lambda url=p['url_gestion']:
                                ui.navigate.to(url, new_tab=True)
                            )
                        ui.menu_item(
                            'Modifier',
                            on_click=lambda pid=p['id']:
                            _open_dialog(c, refresh, portefeuille_id=pid)
                        )
                        ui.menu_item(
                            'Supprimer',
                            on_click=lambda pid=p['id'], name=p['nom_affiche']:
                            _confirm_delete(pid, name, refresh)
                        )

        # ─── Corps : logo + établissement + propriétaire ───
        with ui.column().classes('w-full p-5 gap-4'):
            # Ligne logo + infos
            with ui.row().classes('items-center gap-3 w-full'):
                if p['logo_path']:
                    ui.image(f'/uploads/logos/{p["logo_path"]}').classes(
                        'rounded-lg object-contain'
                    ).style(
                        'width: 48px; height: 48px; '
                        'background-color: white; padding: 4px;'
                    )
                else:
                    with ui.element('div').classes(
                        'rounded-lg flex items-center justify-center'
                    ).style(
                        f'width: 48px; height: 48px; '
                        f'background-color: {accent_color}20;'
                    ):
                        ui.icon(type_info['icon']).classes('text-2xl').style(
                            f'color: {accent_color}'
                        )

                with ui.column().classes('gap-0').style('flex: 1; min-width: 0;'):
                    ui.label(p['etablissement'] or 'Sans établissement') \
                        .classes('font-semibold').style(
                        f'color: {c["text_primary"]}; '
                        f'overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
                    )
                    if p['date_creation']:
                        ui.label(f'Ouvert le {format_date_fr(p["date_creation"])}') \
                            .classes('text-xs').style(f'color: {c["text_secondary"]}')

                if p['proprietaire_initiales']:
                    badge = ui.element('div').classes(
                        'rounded-md flex items-center justify-center'
                    ).style(
                        f'background-color: {p["proprietaire_couleur"]}; '
                        f'min-width: 36px; height: 32px; padding: 0 8px;'
                    )
                    with badge:
                        ui.label(p['proprietaire_initiales']).classes(
                            'text-white text-xs font-bold'
                        )
                        ui.tooltip(p['proprietaire_nom'])

            # ─── Valorisation principale ───
            with ui.column().classes('w-full gap-1 py-2'):
                ui.label('VALORISATION ACTUELLE').classes(
                    'text-xs font-semibold tracking-wider'
                ).style(f'color: {c["text_secondary"]}')
                ui.label(format_money(p['valorisation_actuelle'])) \
                    .classes('text-3xl font-bold').style(f'color: {c["text_primary"]}')

                # +/- value et perf en ligne
                with ui.row().classes('items-center gap-3 mt-1'):
                    arrow = '▲' if is_positive else '▼'
                    ui.label(
                        f'{arrow} {format_money(abs(p["plus_value"]))}'
                    ).classes('text-sm font-semibold').style(f'color: {perf_color}')
                    ui.label(format_percent(p['rendement_total_pct'])) \
                        .classes('text-sm font-semibold px-2 py-0.5 rounded').style(
                        f'background-color: {perf_color}20; color: {perf_color};'
                    )

            # Séparateur
            ui.element('div').classes('h-px w-full').style(
                f'background-color: {c["card_border"]}'
            )

            # ─── Stats secondaires ───
            with ui.row().classes('w-full gap-2'):
                _stat_block('Versé', format_money(p['total_verse']), c)
                _stat_block(
                    'Perf.',
                    format_percent(p['rendement_total_pct']),
                    c,
                    color=get_perf_color(p['rendement_total_pct']),
                )
                _stat_block('Mvts', str(p['nb_transactions']), c)


def _stat_block(label, value, c, color=None):
    """Petit bloc de stat dans le bas de carte."""
    with ui.column().classes('gap-0').style('flex: 1;'):
        ui.label(label.upper()).classes('text-xs').style(
            f'color: {c["text_secondary"]}; font-size: 0.65rem; letter-spacing: 0.05em;'
        )
        ui.label(value).classes('text-sm font-semibold').style(
            f'color: {color or c["text_primary"]}'
        )


# ─────────────────────────────────────────────
# Dialogue création/édition
# ─────────────────────────────────────────────

def _open_dialog(c, refresh, portefeuille_id: int = None, default_membre_id: int = None):
    from database.models import Position

    is_edit = portefeuille_id is not None
    data = {
        'type': 'PEA', 'etablissement': '',
        'date_creation': None, 'logo_path': None, 'url_gestion': '',
        'notes': '', 'proprietaire_id': default_membre_id,
    }

    # Stockage des fonds euros existants si on est en édition
    fonds_euros_existants = []

    if is_edit:
        with get_session() as session:
            p = session.get(Portefeuille, portefeuille_id)
            if p:
                data = p.to_dict()
                # On récupère les fonds euros existants (max 2 attendus)
                if p.type in ['Assurance-Vie', 'AV', 'PER', 'Assurance Vie']:
                    fe_db = session.execute(
                        select(Position).where(
                            Position.portefeuille_id == portefeuille_id,
                            Position.categorie == 'Fonds Euro'
                        ).order_by(Position.id)
                    ).scalars().all()
                    for fe in fe_db:
                        fonds_euros_existants.append({
                            'id': fe.id,
                            'nom': fe.nom
                        })

    membres = get_all_membres()
    membre_options = {m['id']: f'{m["prenom"]} {m["nom"]}' for m in membres}
    type_options = {t['value']: t['label'] for t in TYPES_PORTEFEUILLE}

    date_initiale_fr = ''
    if data['date_creation']:
        date_initiale_fr = date.fromisoformat(
            data['date_creation']
        ).strftime('%d/%m/%Y')

    logo_state = {
        'filename': data['logo_path'],
        'old_filename': data['logo_path'] if is_edit else None,
    }

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'min-width: 500px; max-width: 600px;'
    ):
        ui.label('Modifier le portefeuille' if is_edit else 'Nouveau portefeuille') \
            .classes('text-xl font-bold').style(f'color: {c["text_primary"]}')

        type_input = ui.select(
            type_options, value=data['type'],
            label='Type de portefeuille *'
        ).classes('w-full')

        proprietaire_input = ui.select(
            membre_options,
            value=data['proprietaire_id'],
            label='Propriétaire *'
        ).classes('w-full')

        if not membres:
            ui.label('⚠ Aucun membre. Ajoutez-en dans la page Famille.').style(
                'color: #f59e0b; font-size: 0.75rem;'
            )

        # Aperçu du nom auto-généré
        preview_label = ui.label().classes(
            'text-sm font-medium px-3 py-2 rounded-lg'
        ).style(
            f'background-color: {c["card_border"]}; color: {c["text_primary"]};'
        )

        # ─── GESTION DES FONDS EUROS ───
        fonds_euro_container = ui.column().classes('w-full gap-2 p-3 rounded-lg').style(
            f'background-color: {c["card_border"]}30; border: 1px dashed {c["card_border"]};'
        )
        fonds_euro_inputs = {}

        def update_fonds_euros_ui():
            fonds_euro_container.clear()
            type_val = type_input.value or ''
            is_av_per = type_val in ['Assurance-Vie', 'AV', 'PER', 'Assurance Vie']

            if is_av_per:
                fonds_euro_container.set_visibility(True)
                with fonds_euro_container:
                    ui.label('💶 Configuration des Fonds Euros').classes('text-sm font-bold').style(
                        f'color: {c["text_primary"]}')
                    ui.label(
                        "Saisissez le nom de vos Fonds €. Laissez vide si vous n'en avez pas ou qu'un seul.").classes(
                        'text-xs').style(f'color: {c["text_secondary"]}')

                    # Récupération des valeurs existantes
                    nom_1 = fonds_euros_existants[0]['nom'] if len(fonds_euros_existants) > 0 else 'Fonds Euro'
                    nom_2 = fonds_euros_existants[1]['nom'] if len(fonds_euros_existants) > 1 else ''

                    fonds_euro_inputs['fe_1'] = ui.input('Nom du Fonds € n°1', value=nom_1).classes('w-full').props(
                        'placeholder="ex: Suravenir Rendement"')
                    fonds_euro_inputs['fe_2'] = ui.input('Nom du Fonds € n°2 (Optionnel)', value=nom_2).classes(
                        'w-full').props('placeholder="ex: Suravenir Opportunités"')

                    if is_edit and len(fonds_euros_existants) > 0:
                        ui.label('ℹ️ La modification du nom ici mettra à jour la position existante.').classes(
                            'text-xs italic mt-1').style(f'color: {c["text_secondary"]}')
            else:
                fonds_euro_container.set_visibility(False)
                fonds_euro_inputs.clear()

        def update_preview():
            type_val = type_input.value or '...'
            prop_id = proprietaire_input.value
            prop_name = ''
            if prop_id and prop_id in membre_options:
                prop_name = membre_options[prop_id].split(' ')[0]
            if prop_name:
                preview_label.text = f'📋 Nom affiché : {type_val} — {prop_name}'
            else:
                preview_label.text = f'📋 Nom affiché : {type_val}'

            update_fonds_euros_ui()

        update_preview()
        type_input.on('update:model-value', lambda _: update_preview())
        proprietaire_input.on('update:model-value', lambda _: update_preview())

        etab_input = ui.input(
            'Établissement (banque / assurance / site)',
            value=data['etablissement'] or ''
        ).classes('w-full').props(
            'placeholder="ex: Boursorama, Crédit Agricole, Linxea..."'
        )

        with ui.input("Date d'ouverture", value=date_initiale_fr) \
                .classes('w-full') \
                .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input:
            with ui.menu().props('no-parent-event') as menu:
                with ui.date().bind_value(date_input).props('mask="DD/MM/YYYY"'):
                    with ui.row().classes('justify-end'):
                        ui.button('Fermer', on_click=menu.close).props('flat')
            with date_input.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes(
                    'cursor-pointer'
                )

        url_input = ui.input(
            'URL de gestion en ligne', value=data['url_gestion'] or ''
        ).classes('w-full').props(
            'placeholder="https://..."'
        )

        # ── Logo : upload direct sur disque ──
        ui.label("Logo de l'établissement").style(f'color: {c["text_secondary"]}')

        logo_container = ui.row().classes('items-center gap-4 w-full')

        def render_logo_zone():
            logo_container.clear()
            with logo_container:
                with ui.element('div').classes(
                    'rounded-lg flex items-center justify-center overflow-hidden'
                ).style(
                    f'width: 64px; height: 64px; background-color: white; '
                    f'border: 1px solid {c["card_border"]};'
                ):
                    if logo_state['filename']:
                        ui.image(
                            f'/uploads/logos/{logo_state["filename"]}'
                        ).style(
                            'max-width:100%; max-height:100%; object-fit:contain;'
                        )
                    else:
                        ui.icon('image').classes('text-2xl').style(
                            f'color: {c["text_secondary"]}'
                        )

                with ui.column().classes('gap-1 flex-1'):
                    upload = ui.upload(
                        on_upload=handle_upload,
                        auto_upload=True,
                        max_file_size=2_000_000,
                    ).props(
                        'accept=".png,.jpg,.jpeg,.svg,.webp" '
                        'flat dense label="Choisir un logo"'
                    ).classes('w-full')

                    if logo_state['filename']:
                        ui.button('Retirer le logo', on_click=remove_logo) \
                            .props('flat dense').style(
                            'color: #ef4444; font-size: 0.75rem;'
                        )

        async def handle_upload(e: events.UploadEventArguments):
            uploaded_file = e.file
            filename = getattr(uploaded_file, 'filename', 'upload.png')
            if not filename:
                filename = getattr(uploaded_file, 'name', 'upload.png')

            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'png'
            if ext not in ('png', 'jpg', 'jpeg', 'svg', 'webp'):
                ui.notify('Format non supporté (png, jpg, svg, webp)', type='negative')
                return

            content = await uploaded_file.read()
            if isinstance(content, str):
                content = content.encode()

            if not content:
                ui.notify('Fichier vide', type='negative')
                return

            new_filename = f'{uuid.uuid4().hex}.{ext}'
            file_path = UPLOADS_DIR / new_filename
            try:
                file_path.write_bytes(content)
            except Exception as ex:
                ui.notify(f'Erreur sauvegarde : {ex}', type='negative')
                return

            previous = logo_state['filename']
            if previous and previous != logo_state['old_filename']:
                old = UPLOADS_DIR / previous
                if old.exists():
                    old.unlink()

            logo_state['filename'] = new_filename
            ui.notify('Logo uploadé ✓', type='positive')
            render_logo_zone()

        def remove_logo():
            if logo_state['filename'] and logo_state['filename'] != logo_state['old_filename']:
                f = UPLOADS_DIR / logo_state['filename']
                if f.exists():
                    f.unlink()
            logo_state['filename'] = None
            ui.notify('Logo retiré', type='info')
            render_logo_zone()

        render_logo_zone()

        notes_input = ui.textarea(
            'Notes (optionnel)', value=data['notes'] or ''
        ).classes('w-full').props('rows=2')

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            def cancel():
                if (logo_state['filename']
                        and logo_state['filename'] != logo_state['old_filename']):
                    f = UPLOADS_DIR / logo_state['filename']
                    if f.exists():
                        f.unlink()
                dialog.close()

            ui.button('Annuler', on_click=cancel).props('flat').style(
                f'color: {c["text_secondary"]}'
            )

            def save():
                if not type_input.value:
                    ui.notify('Le type est obligatoire', type='negative')
                    return
                if not proprietaire_input.value:
                    ui.notify('Le propriétaire est obligatoire', type='negative')
                    return

                date_val = None
                if date_input.value:
                    try:
                        date_val = datetime.strptime(
                            date_input.value, '%d/%m/%Y'
                        ).date()
                    except ValueError:
                        ui.notify(
                            'Format de date invalide (JJ/MM/AAAA)',
                            type='negative'
                        )
                        return

                if (logo_state['old_filename']
                        and logo_state['old_filename'] != logo_state['filename']):
                    old = UPLOADS_DIR / logo_state['old_filename']
                    if old.exists():
                        old.unlink()

                with get_session() as session:
                    # Sauvegarde du Portefeuille
                    if is_edit:
                        p = session.get(Portefeuille, portefeuille_id)
                        p.type = type_input.value
                        p.etablissement = etab_input.value or None
                        p.date_creation = date_val
                        p.logo_path = logo_state['filename']
                        p.url_gestion = url_input.value or None
                        p.notes = notes_input.value or None
                        p.proprietaire_id = proprietaire_input.value
                    else:
                        p = Portefeuille(
                            type=type_input.value,
                            etablissement=etab_input.value or None,
                            date_creation=date_val,
                            logo_path=logo_state['filename'],
                            url_gestion=url_input.value or None,
                            notes=notes_input.value or None,
                            proprietaire_id=proprietaire_input.value,
                        )
                        session.add(p)
                        session.flush()  # Pour avoir le p.id

                    # Sauvegarde des Fonds Euros
                    is_av_per = p.type in ['Assurance-Vie', 'AV', 'PER', 'Assurance Vie']

                    if is_av_per and fonds_euro_inputs:
                        noms_saisis = []
                        if fonds_euro_inputs.get('fe_1') and fonds_euro_inputs['fe_1'].value and fonds_euro_inputs['fe_1'].value.strip():
                            noms_saisis.append(fonds_euro_inputs['fe_1'].value.strip())
                        if fonds_euro_inputs.get('fe_2') and fonds_euro_inputs['fe_2'].value and fonds_euro_inputs['fe_2'].value.strip():
                            noms_saisis.append(fonds_euro_inputs['fe_2'].value.strip())

                        # Création ou MAJ
                        for i, nom in enumerate(noms_saisis):
                            if is_edit and i < len(fonds_euros_existants):
                                # Mise à jour d'un FE existant
                                fe = session.get(Position, fonds_euros_existants[i]['id'])
                                if fe:
                                    fe.nom = nom
                            else:
                                # Création d'un nouveau FE
                                new_fe = Position(
                                    portefeuille_id=p.id,
                                    nom=nom,
                                    categorie='Fonds Euro',
                                    quantite=0.0,
                                    prix_moyen=1.0,
                                    cours_actuel=1.0,
                                    devise='EUR',
                                    date_ouverture=date_val or date.today(),
                                    auto_update=False
                                )
                                session.add(new_fe)

                    session.commit()

                ui.notify(
                    'Portefeuille modifié' if is_edit else 'Portefeuille créé',
                    type='positive'
                )
                dialog.close()
                refresh()
                refresh_layout()

            ui.button('Enregistrer', on_click=save).props('unelevated') \
                .classes('bg-blue-600 text-white')

        dialog.open()


# ─────────────────────────────────────────────
# Confirmation suppression
# ─────────────────────────────────────────────

def _confirm_delete(portefeuille_id: int, name: str, refresh):
    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4'):
        ui.label('Confirmer la suppression').classes('text-xl font-bold')
        ui.label(f'Voulez-vous vraiment supprimer "{name}" ?')
        ui.label('Cette action est irréversible.').classes('text-sm').style(
            'color: #ef4444'
        )

        def do_delete():
            with get_session() as session:
                p = session.get(Portefeuille, portefeuille_id)
                if p:
                    if p.logo_path:
                        logo_file = UPLOADS_DIR / p.logo_path
                        if logo_file.exists():
                            logo_file.unlink()
                    session.delete(p)
                    session.commit()
            ui.notify(f'"{name}" a été supprimé', type='warning')
            dialog.close()
            refresh()
            refresh_layout()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Annuler', on_click=dialog.close).props('flat')
            ui.button('Supprimer', on_click=do_delete).props('unelevated') \
                .classes('bg-red-600 text-white')

        dialog.open()
