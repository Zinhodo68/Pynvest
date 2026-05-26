"""Orchestrateur principal de la page détail d'un portefeuille."""

from nicegui import ui

from components.layout import page_layout
from theme import get_colors
from database.db import get_session
from database.models import Portefeuille
from pages.portefeuilles_data import get_type_info, is_mono_support

from pages.portefeuille_detail._header import render_header, render_kpis
from pages.portefeuille_detail._chart import render_chart
from pages.portefeuille_detail._positions import render_positions_section
from pages.portefeuille_detail._transactions import render_transactions_card
from pages.portefeuille_detail._mono_support import render_mono_support_section


def render(portefeuille_id: int):
    is_dark = page_layout(active_route='/portefeuilles')
    c = get_colors(is_dark)

    container = ui.column().classes('w-full p-6 gap-4')

    def refresh():
        container.clear()
        with container:
            _render_content(portefeuille_id, c, is_dark, refresh)

    refresh()


def _render_content(portefeuille_id, c, is_dark, refresh):
    with get_session() as session:
        from services.portfolio_stats import preload_stats

        p = session.get(Portefeuille, portefeuille_id)
        if not p:
            ui.label('Portefeuille introuvable').classes('text-2xl').style(
                f'color: {c["text_primary"]}'
            )
            ui.button(
                '← Retour',
                on_click=lambda: ui.navigate.to('/portefeuilles'),
            ).props('flat')
            return

        preload_stats(session, [p])

        data = p.to_dict()
        valorisations = [
            {'date': v.date_valeur.isoformat(), 'montant': v.montant}
            for v in p.valorisations
        ]
        transactions = [
            {
                'id': t.id,
                'date': t.date_operation.isoformat(),
                'type': t.type_operation,
                'montant': t.montant,
                'libelle': t.libelle,
                'parent_transaction_id': t.parent_transaction_id,
            }
            for t in p.transactions
        ]
        positions = [pos.to_dict() for pos in p.positions]

        data['taux_interet'] = p.taux_interet
        data['plafond'] = p.plafond

        type_info = get_type_info(data['type'])
        accent_color = type_info['couleur']
        mono = is_mono_support(data['type'])

        # ── Graphique dans un bandeau dépliable (fermé par défaut) ──
        @ui.refreshable
        def render_chart_card():
            with get_session() as chart_session:
                p_chart = chart_session.get(Portefeuille, portefeuille_id)
                if not p_chart:
                    return

                valorisations_chart = [
                    {'date': v.date_valeur.isoformat(), 'montant': v.montant}
                    for v in p_chart.valorisations
                ]
                transactions_chart = [
                    {
                        'id': t.id,
                        'date': t.date_operation.isoformat(),
                        'type': t.type_operation,
                        'montant': t.montant,
                        'libelle': t.libelle,
                        'parent_transaction_id': t.parent_transaction_id,
                    }
                    for t in p_chart.transactions
                ]

            # ── Bandeau dépliable ──
            with ui.card().classes('w-full p-0 rounded-xl overflow-hidden').style(
                f'background-color: {c["card_bg"]}; '
                f'border: 1px solid {c["card_border"]};'
            ):
                with ui.expansion(
                    text='Évolution de la valeur',
                    icon='show_chart',
                    value=False,  # ← fermé par défaut
                ).classes('w-full').style(
                    f'color: {c["text_primary"]};'
                ) as expansion:
                    # Style du header de l'expansion
                    expansion.props('dense header-class="text-lg font-bold"')

                    if not valorisations_chart:
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
                                valorisations_chart,
                                transactions_chart,
                                accent_color,
                                c,
                                is_dark,
                            )

        # En-tête + KPIs
        render_header(data, type_info, accent_color, c, portefeuille_id, refresh, mono,
                      refresh_chart=render_chart_card.refresh)
        render_kpis(data, accent_color, c, mono, portefeuille_id=portefeuille_id)

        render_chart_card()

        # Section principale selon le type
        if mono:
            render_mono_support_section(data, type_info, c, portefeuille_id, refresh)
            render_transactions_card(
                transactions,
                c,
                is_dark,
                refresh,
                portefeuille_id,
                full_width=True,
                refresh_chart=render_chart_card.refresh,
            )
        else:
            with ui.row().classes('w-full gap-4 flex-nowrap items-start'):
                with ui.column().classes('gap-0').style('flex: 2; min-width: 0;'):
                    render_positions_section(positions, data, c, portefeuille_id, refresh,
                                             refresh_chart=render_chart_card.refresh)
                with ui.column().classes('gap-0').style('flex: 1; min-width: 0;'):
                    render_transactions_card(
                        transactions,
                        c,
                        is_dark,
                        refresh,
                        portefeuille_id,
                        full_width=True,
                        refresh_chart=render_chart_card.refresh,
                    )
