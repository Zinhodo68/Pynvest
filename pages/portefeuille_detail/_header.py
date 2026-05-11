"""En-tête et KPIs de la page détail."""
from nicegui import ui

from theme import get_colors
from utils.formatters import format_money, format_percent, format_date_fr, get_perf_color


def render_header(data, type_info, accent_color, c, portefeuille_id, refresh, mono):
    """Header avec retour, identité, infos clés, et boutons d'action."""
    # Imports locaux pour éviter les imports circulaires
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

                # ✨ Bouton rafraîchir les cours (uniquement pour multi-supports)
                if not mono:
                    ui.button(icon='refresh',
                              on_click=lambda: _refresh_quotes(c, refresh)) \
                        .props('flat round dense') \
                        .style(f'color: {c["text_secondary"]}') \
                        .tooltip('Actualiser les cours')

                # Édition du portefeuille
                ui.button(icon='edit',
                          on_click=lambda: _open_edit_portefeuille(
                              portefeuille_id, c, refresh)) \
                    .props('flat round dense').style(f'color: {c["text_secondary"]}') \
                    .tooltip('Modifier le portefeuille')

                # Valorisation manuelle
                ui.button('+ Valorisation',
                          on_click=lambda: open_valorisation_dialog(
                              portefeuille_id, c, refresh)) \
                    .props('outline').style(
                        f'color: {c["text_primary"]}; '
                        f'border-color: {c["text_secondary"]};'
                    )

        # Séparateur
        ui.element('div').classes('h-px w-full my-3').style(
            f'background-color: {c["card_border"]}'
        )

        # Infos clés en grille
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


def render_kpis(data, accent_color, c, mono):
    """Bandeau de 5 KPIs principaux."""
    perf_color = get_perf_color(data['plus_value'])
    is_positive = data['plus_value'] >= 0
    arrow = '▲' if is_positive else '▼'

    with ui.row().classes('w-full gap-4 flex-nowrap'):
        _kpi_card(c, 'VALORISATION', format_money(data['valorisation_actuelle']),
                  'account_balance_wallet', accent_color)
        _kpi_card(c, 'CAPITAL INVESTI', format_money(data['total_verse']),
                  'savings', '#a855f7')
        _kpi_card(c, 'INTÉRÊTS' if mono else '+/- VALUE',
                  f'{arrow} {format_money(abs(data["plus_value"]))}',
                  'trending_up' if is_positive else 'trending_down', perf_color)
        _kpi_card(c, 'PERF. TOTALE', format_percent(data['rendement_total_pct']),
                  'percent', get_perf_color(data['rendement_total_pct']))
        _kpi_card(c, 'PERF. ANNUALISÉE', format_percent(data['rendement_annualise_pct']),
                  'speed', get_perf_color(data['rendement_annualise_pct']))


def _kpi_card(c, label, value, icon, color):
    with ui.card().classes('p-4 rounded-xl gap-1').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'flex: 1;'
    ):
        with ui.row().classes('items-center justify-between w-full'):
            ui.label(label).classes('text-xs font-semibold tracking-wider').style(
                f'color: {c["text_secondary"]}'
            )
            ui.icon(icon).classes('text-base').style(f'color: {color}; opacity: 0.7;')
        ui.label(value).classes('text-xl font-bold').style(f'color: {color}')


def _open_edit_portefeuille(portefeuille_id, c, refresh):
    """Réutilise le dialogue d'édition de portfolios.py."""
    from pages.portfolios import _open_dialog
    _open_dialog(c, refresh, portefeuille_id=portefeuille_id)


def _refresh_quotes(c, refresh):
    """Force la mise à jour des cours en arrière-plan."""
    from services.quotes_updater import update_all_quotes
    import threading

    ui.notify('🔄 Mise à jour des cours en cours...', type='info', timeout=2000)

    def do_update():
        try:
            stats = update_all_quotes(force=True)
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

    threading.Thread(target=do_update, daemon=True).start()