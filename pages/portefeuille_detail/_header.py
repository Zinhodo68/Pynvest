"""En-tête et KPIs de la page détail."""
from nicegui import ui

from theme import get_colors
from utils.formatters import format_money, format_percent, format_date_fr, get_perf_color


# 🆕 Style hover pour la card expandable (shared=True → injecté une seule fois)
ui.add_head_html('''
<style>
.kpi-expandable:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    transition: all 0.2s ease;
}
.kpi-expandable {
    transition: all 0.2s ease;
}
</style>
''', shared=True)


# 🆕 État global d'expansion pour les KPIs
_kpi_expand_state = {'expanded': False, 'portefeuille_id': None}


def render_header(data, type_info, accent_color, c, portefeuille_id, refresh, mono):
    """Header avec retour, identité, infos clés, et boutons d'action."""
    from pages.portefeuille_detail._transactions import open_transaction_dialog
    from pages.portefeuille_detail._mono_support import open_valorisation_dialog

    with ui.card().classes('w-full p-5 rounded-xl').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]};'
    ):
        # Ligne 1 : retour + identité + actions
        with ui.row().classes('w-full items-center justify-between'):
            with ui.row().classes('items-center gap-4'):
                ui.button(icon='arrow_back',
                          on_click=lambda: ui.navigate.to('/portefeuilles')) \
                    .props('flat round dense').style(f'color: {c["text_secondary"]}')

                if data['logo_path']:
                    ui.image(f'/uploads/logos/{data["logo_path"]}').classes(
                        'rounded-lg object-contain'
                    ).style('width: 56px; height: 56px; '
                            'background-color: white; padding: 6px;')
                else:
                    with ui.element('div').classes(
                        'rounded-lg flex items-center justify-center'
                    ).style(f'width: 56px; height: 56px; '
                            f'background-color: {accent_color}20;'):
                        ui.icon(type_info['icon']).classes('text-2xl').style(
                            f'color: {accent_color}'
                        )

                with ui.column().classes('gap-0'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label(data['nom_affiche']).classes('text-2xl font-bold').style(
                            f'color: {c["text_primary"]}'
                        )
                        if data['proprietaire_initiales']:
                            with ui.element('div').classes(
                                'rounded-md flex items-center justify-center'
                            ).style(
                                f'background-color: {data["proprietaire_couleur"]}; '
                                f'min-width: 30px; height: 24px; padding: 0 6px;'
                            ):
                                ui.label(data['proprietaire_initiales']).classes(
                                    'text-white text-xs font-bold'
                                )
                    ui.label(type_info['label']).classes('text-xs uppercase tracking-wider') \
                        .style(f'color: {c["text_secondary"]}; font-weight: 600;')

            # ── Boutons d'action ──
            with ui.row().classes('gap-2 items-center'):
                if data['url_gestion']:
                    ui.button('Site', icon='open_in_new',
                              on_click=lambda url=data['url_gestion']:
                              ui.navigate.to(url, new_tab=True)) \
                        .props('outline').style(
                            f'color: {c["text_primary"]}; '
                            f'border-color: {c["text_secondary"]};'
                        )

                if not mono:
                    ui.button(icon='refresh',
                              on_click=lambda: _refresh_quotes(c, refresh)) \
                        .props('flat round dense') \
                        .style(f'color: {c["text_secondary"]}') \
                        .tooltip('Actualiser les cours')

                ui.button(icon='edit',
                          on_click=lambda: _open_edit_portefeuille(
                              portefeuille_id, c, refresh)) \
                    .props('flat round dense').style(f'color: {c["text_secondary"]}') \
                    .tooltip('Modifier le portefeuille')

                ui.button('+ Valorisation',
                          on_click=lambda: open_valorisation_dialog(
                              portefeuille_id, c, refresh)) \
                    .props('outline').style(
                        f'color: {c["text_primary"]}; '
                        f'border-color: {c["text_secondary"]};'
                    )

        ui.element('div').classes('h-px w-full my-3').style(
            f'background-color: {c["card_border"]}'
        )

        infos = [
            ('event', 'OUVERT LE',
             format_date_fr(data['date_creation']) if data['date_creation'] else '—'),
            ('account_balance', 'ÉTABLISSEMENT', data['etablissement'] or '—'),
            ('person', 'PROPRIÉTAIRE', data['proprietaire_nom'] or '—'),
            ('receipt_long', 'TRANSACTIONS', f'{data["nb_transactions"]} mvt(s)'),
        ]

        with ui.row().classes('w-full gap-6'):
            for icon_name, label, value in infos:
                with ui.row().classes('items-center gap-2').style('flex: 1; min-width: 0;'):
                    ui.icon(icon_name).classes('text-base').style(
                        f'color: {accent_color}; opacity: 0.7;'
                    )
                    with ui.column().classes('gap-0').style('min-width: 0;'):
                        ui.label(label).classes('text-xs font-semibold tracking-wider').style(
                            f'color: {c["text_secondary"]};'
                        )
                        ui.label(value).classes('text-sm font-medium').style(
                            f'color: {c["text_primary"]}; '
                            f'overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
                        )

        if data['notes']:
            ui.element('div').classes('h-px w-full my-3').style(
                f'background-color: {c["card_border"]}'
            )
            with ui.row().classes('items-start gap-2 w-full'):
                ui.icon('notes').classes('text-base mt-0.5').style(
                    f'color: {c["text_secondary"]}'
                )
                ui.label(data['notes']).classes('text-sm').style(
                    f'color: {c["text_secondary"]}; flex: 1;'
                )


def render_kpis(data, accent_color, c, mono, portefeuille_id=None):
    """Bandeau de 5 KPIs avec card 'Perf. Annualisée' expandable.

    Au clic sur la dernière card → les 4 cards de gauche se compressent
    et la dernière s'élargit pour afficher les rendements année par année.
    """
    perf_color = get_perf_color(data['plus_value'])
    is_positive = data['plus_value'] >= 0
    arrow = '▲' if is_positive else '▼'

    # 🆕 Récupérer/réinitialiser l'état d'expansion
    if _kpi_expand_state['portefeuille_id'] != portefeuille_id:
        _kpi_expand_state['expanded'] = False
        _kpi_expand_state['portefeuille_id'] = portefeuille_id

    # Conteneur principal qui sera redessiné au toggle
    kpi_container = ui.row().classes('w-full gap-4 flex-nowrap')

    def render_content():
        kpi_container.clear()
        is_expanded = _kpi_expand_state['expanded']

        with kpi_container:
            # Flex des 4 cards de gauche : compressées si expanded
            left_flex = '0.5' if is_expanded else '1'

            _kpi_card(c, 'VALORISATION', format_money(data['valorisation_actuelle']),
                      'account_balance_wallet', accent_color, flex=left_flex,
                      compact=is_expanded)
            _kpi_card(c, 'CAPITAL INVESTI', format_money(data['total_verse']),
                      'savings', '#a855f7', flex=left_flex, compact=is_expanded)
            _kpi_card(c, 'INTÉRÊTS' if mono else '+/- VALUE',
                      f'{arrow} {format_money(abs(data["plus_value"]))}',
                      'trending_up' if is_positive else 'trending_down', perf_color,
                      flex=left_flex, compact=is_expanded)
            _kpi_card(c, 'PERF. TOTALE', format_percent(data['rendement_total_pct']),
                      'percent', get_perf_color(data['rendement_total_pct']),
                      flex=left_flex, compact=is_expanded)

            # 🆕 5ème card : expandable
            _kpi_card_expandable(
                c, 'PERF. ANNUALISÉE',
                format_percent(data['rendement_annualise_pct']),
                'speed', get_perf_color(data['rendement_annualise_pct']),
                is_expanded=is_expanded,
                portefeuille_id=portefeuille_id,
                on_toggle=toggle_expansion,
            )

    def toggle_expansion():
        _kpi_expand_state['expanded'] = not _kpi_expand_state['expanded']
        render_content()

    render_content()


def _kpi_card(c, label, value, icon, color, flex='1', compact=False):
    """KPI card classique. Si compact=True, version réduite."""
    value_size = 'text-base' if compact else 'text-xl'
    label_size = 'text-xs'
    padding = 'p-3' if compact else 'p-4'

    with ui.card().classes(f'{padding} rounded-xl gap-1').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'flex: {flex}; '
        f'transition: flex 0.3s ease, padding 0.3s ease; '
        f'min-width: 0; overflow: hidden; '
        f'min-height: 92px;'  # 🆕 Hauteur uniforme garantie
    ):
        with ui.row().classes('items-center justify-between w-full flex-nowrap'):
            ui.label(label).classes(f'{label_size} font-semibold tracking-wider').style(
                f'color: {c["text_secondary"]}; '
                f'overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
            )
            if not compact:
                ui.icon(icon).classes('text-base').style(
                    f'color: {color}; opacity: 0.7;'
                )
        ui.label(value).classes(f'{value_size} font-bold').style(
            f'color: {color}; '
            f'overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
        )


def _kpi_card_expandable(c, label, value, icon, color, is_expanded,
                          portefeuille_id, on_toggle):
    """KPI card spéciale 'Perf. Annualisée' : cliquable, expandable.

    Layout cohérent avec les autres KPIs :
    - Label en haut (toujours)
    - Valeur en bas (état fermé) OU valeur + rendements annuels (état ouvert)
    """
    flex = '5' if is_expanded else '1'
    chevron = 'chevron_left' if is_expanded else 'unfold_more'

    bg_color = f'{color}08'
    border_color = f'{color}50'

    with ui.card().classes('p-4 rounded-xl gap-1 cursor-pointer kpi-expandable').style(
        f'background-color: {bg_color}; '
        f'border: 1.5px solid {border_color}; '
        f'flex: {flex}; '
        f'transition: flex 0.3s ease, background-color 0.2s ease; '
        f'min-width: 0; '
        f'min-height: 92px;'
    ).on('click', on_toggle):
        # 🆕 Header : label + chevron (toujours en haut, comme les autres cards)
        with ui.row().classes('items-center justify-between w-full flex-nowrap'):
            ui.label(label).classes('text-xs font-semibold tracking-wider').style(
                f'color: {c["text_secondary"]};'
            )
            ui.icon(chevron).classes('text-base').style(
                f'color: {color}; opacity: 0.8;'
            ).tooltip(
                'Cliquer pour replier' if is_expanded
                else 'Cliquer pour voir les rendements annuels'
            )

        # 🆕 Contenu principal : valeur + rendements sur la MÊME ligne quand ouvert
        if is_expanded and portefeuille_id is not None:
            from services.perf_annuelle import get_rendements_annuels

            try:
                rendements = get_rendements_annuels(portefeuille_id, max_years=10)
            except Exception as e:
                with ui.row().classes('w-full items-center gap-3'):
                    ui.label(value).classes('text-xl font-bold').style(f'color: {color}')
                    ui.label(f'⚠️ Erreur : {e}').classes('text-xs').style('color: #ef4444;')
                return

            if not rendements:
                with ui.row().classes('w-full items-center gap-3'):
                    ui.label(value).classes('text-xl font-bold').style(f'color: {color}')
                    ui.label('Pas assez d\'historique pour les rendements annuels.') \
                        .classes('text-xs italic').style(f'color: {c["text_secondary"]};')
                return

            # Layout horizontal : valeur globale à gauche + mini-cards alignées à DROITE
            with ui.row().classes('w-full items-center gap-3 flex-nowrap'):
                # Valeur globale (perf annualisée)
                ui.label(value).classes('text-xl font-bold').style(
                    f'color: {color}; min-width: 80px;'
                )

                # Séparateur vertical
                ui.element('div').style(
                    f'width: 1px; height: 36px; '
                    f'background-color: {c["card_border"]}; '
                    f'opacity: 0.5;'
                )

                # 🆕 Spacer flexible pour pousser les rendements à droite
                ui.element('div').style('flex: 1;')

                # Rendements annuels (du plus ancien au plus récent), alignés à droite
                with ui.row().classes('gap-1 flex-nowrap items-center'):
                    for r in reversed(rendements):
                        _render_year_minicard(r, c)
        else:
            # État fermé : valeur + icône
            with ui.row().classes('items-center justify-between w-full flex-nowrap'):
                ui.label(value).classes('text-xl font-bold').style(f'color: {color}')
                ui.icon(icon).classes('text-base').style(
                    f'color: {color}; opacity: 0.7;'
                )


def _render_year_minicard(rendement, c):
    """Mini-card pour un rendement annuel."""
    from datetime import date
    pct = rendement['rendement_pct']
    color = get_perf_color(pct)

    # 🆕 Détecter l'année en cours
    is_current_year = rendement['annee'] == date.today().year
    annee_label = f"{rendement['annee']}*" if is_current_year else str(rendement['annee'])

    tooltip_text = (
        f"Année {rendement['annee']}\n"
        f"Valo début : {format_money(rendement['valo_debut'])}\n"
        f"Valo fin : {format_money(rendement['valo_fin'])}\n"
        f"Flux nets : {format_money(rendement['flux_nets'])}"
    )
    if is_current_year:
        tooltip_text += "\n* Année en cours (partielle)"

    # 🆕 Format propre : signe + ou - explicite
    sign = '+' if pct >= 0 else '-'
    pct_str = f'{sign}{abs(pct):.1f} %'.replace('.', ',')

    with ui.column().classes('gap-0 items-center justify-center px-2 py-1 rounded').style(
        f'background-color: {c["card_border"]}30; '
        f'border-left: 3px solid {color}; '
        f'min-width: 60px; max-width: 90px;'
        + (' border: 1px dashed ' + color + '80;' if is_current_year else '')
    ).tooltip(tooltip_text):
        ui.label(annee_label).classes('text-xs').style(
            f'color: {c["text_secondary"]}; line-height: 1.2;'
            + (' font-style: italic;' if is_current_year else '')
        )
        ui.label(pct_str).classes('text-sm font-bold').style(
            f'color: {color}; white-space: nowrap; line-height: 1.2;'
        )

def _open_edit_portefeuille(portefeuille_id, c, refresh):
    from pages.portfolios import _open_dialog
    _open_dialog(c, refresh, portefeuille_id=portefeuille_id)


async def _refresh_quotes(c, refresh):
    from services.quotes_updater import update_all_quotes
    from nicegui import run

    ui.notify('🔄 Mise à jour des cours en cours...', type='info', timeout=2000)

    try:
        stats = await run.io_bound(update_all_quotes, force=True)

        if stats['updated'] == 0 and stats['errors'] == 0:
            ui.notify('Aucune position à mettre à jour', type='info')
        elif stats['errors'] > 0:
            ui.notify(
                f"✅ {stats['updated']} cours mis à jour, "
                f"⚠️ {stats['errors']} erreur(s)",
                type='warning', timeout=4000
            )
        else:
            ui.notify(
                f"✅ {stats['updated']} cours mis à jour",
                type='positive'
            )
        refresh()
    except Exception as e:
        ui.notify(f'❌ Erreur : {e}', type='negative', timeout=5000)