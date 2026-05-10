from nicegui import ui
from components.layout import page_layout


def render():
    is_dark = page_layout(active_route='/')  # ✅

    # Couleurs basées sur le thème
    card_bg = '#0f172a' if is_dark else '#ffffff'
    card_border = '#1e293b' if is_dark else '#e2e8f0'
    text_primary = '#ffffff' if is_dark else '#0f172a'
    text_secondary = '#94a3b8' if is_dark else '#64748b'

    card_style = (
        f'background-color: {card_bg}; '
        f'border: 1px solid {card_border}; '
        f'border-radius: 0.75rem;'
    )

    with ui.column().classes('w-full p-6 gap-6'):
        # Bannière de santé
        banner_bg = (
            'linear-gradient(to right, rgba(6,78,59,0.3), #0f172a)' if is_dark
            else 'linear-gradient(to right, #d1fae5, #ffffff)'
        )
        with ui.card().classes('w-full p-6 rounded-xl').style(
            f'background: {banner_bg}; border: 1px solid rgba(16,185,129,0.3);'
        ):
            with ui.row().classes('items-center justify-between w-full'):
                with ui.row().classes('items-center gap-6'):
                    with ui.element('div').classes(
                        'w-20 h-20 rounded-full flex items-center justify-center'
                    ).style('border: 4px solid #10b981'):
                        ui.label('82').classes('text-2xl font-bold').style('color: #10b981')
                    with ui.column().classes('gap-1'):
                        ui.label('Votre santé patrimoniale est saine').classes(
                            'text-xl font-bold'
                        ).style(f'color: {text_primary}')
                        ui.label(
                            "Le levier est équilibré et la révalorisation est positive cette année (+12.4%)."
                        ).classes('text-sm').style(f'color: {text_secondary}')
                ui.button("Voir l'analyse détaillée").props('outline').style(
                    f'color: {text_primary}; border-color: #94a3b8'
                )

        # KPI Cards
        with ui.row().classes('w-full gap-4 flex-nowrap'):
            _kpi_card('VALEUR BRUTE', '1 136 200,00 €', '+14.8% revalorisation',
                      'work', '#3b82f6', card_style, text_primary, text_secondary)
            _kpi_card('ENDETTEMENT', '370 000,00 €', '2 dossiers actifs',
                      'credit_card', '#ef4444', card_style, text_primary, text_secondary)
            _kpi_card('PATRIMOINE NET', '766 200,00 €', 'Calculé en valeur de marché',
                      'account_balance_wallet', '#10b981', card_style, text_primary, text_secondary)
            _kpi_card('RÉVALORISATION', '146 200,00 €', 'Plus-value latente totale',
                      'trending_up', '#a855f7', card_style, text_primary, text_secondary)
            _kpi_card('REVENUS MENSUELS', '755,00 €', 'Flux net avant impôts',
                      'pie_chart', '#ec4899', card_style, text_primary, text_secondary)

        # Section principale
        with ui.row().classes('w-full gap-4 flex-nowrap items-start'):
            _rendement_table(card_style, text_primary, text_secondary, is_dark)
            _allocation_card(card_style, text_primary, text_secondary)


def _kpi_card(title, value, sub, icon, color, card_style, text_primary, text_secondary):
    with ui.card().classes('flex-1 p-5 gap-2').style(card_style):
        with ui.row().classes('items-start justify-between w-full'):
            with ui.column().classes('gap-1 flex-1'):
                with ui.row().classes('items-center gap-2'):
                    ui.label(title).classes('text-xs font-semibold tracking-wider').style(
                        f'color: {text_secondary}'
                    )
                    ui.element('div').classes('w-1.5 h-1.5 rounded-full').style(
                        f'background-color: {color}'
                    )
                ui.label(value).classes('text-xl font-bold').style(f'color: {text_primary}')
            ui.icon(icon).classes('text-2xl').style(f'color: {color}; opacity: 0.6')
        ui.label(sub).classes('text-xs').style(f'color: {color}')


def _rendement_table(card_style, text_primary, text_secondary, is_dark):
    border = '#1e293b' if is_dark else '#e2e8f0'
    hover = '#1e293b80' if is_dark else '#f8fafc'

    with ui.card().classes('flex-1 p-0').style(card_style):
        with ui.row().classes('items-center justify-between w-full p-5').style(
            f'border-bottom: 1px solid {border}'
        ):
            ui.label('Rendement des actifs').classes('text-lg font-bold').style(
                f'color: {text_primary}'
            )
            with ui.row().classes('gap-2'):
                ui.button(icon='download').props('flat round dense').style(
                    f'color: {text_secondary}'
                )
                ui.button('Filtrer').props('outline dense').style(f'color: {text_primary}')
                ui.button('+ Actif').props('dense').classes('bg-blue-600 text-white')

        with ui.row().classes('w-full px-5 py-3 text-xs font-semibold uppercase tracking-wider').style(
            f'color: {text_secondary}'
        ):
            ui.label('Actif').style('flex: 1')
            ui.label('Valeur actuelle').style('width: 8rem; text-align: right')
            ui.label('Cashflow').style('width: 6rem; text-align: right')
            ui.label('Rendement').style('width: 6rem; text-align: right')

        rows = [
            {'actif': 'Appartement Lyon', 'cat': 'Immobilier', 'tags': ['JP', 'SM'],
             'valeur': '520 k €', 'cashflow': '+1200€', 'rendement': '3.2%', 'color': '#3b82f6'},
            {'actif': 'Portfolio Actions', 'cat': 'Actifs Financiers', 'tags': ['JP'],
             'valeur': '145 k €', 'cashflow': '+0€', 'rendement': '0.0%', 'color': '#f97316'},
        ]

        for row in rows:
            with ui.row().classes('w-full items-center px-5 py-4').style(
                f'border-top: 1px solid {border}'
            ):
                with ui.row().classes('items-center gap-3').style('flex: 1'):
                    ui.element('div').classes('w-1 h-10 rounded').style(
                        f'background-color: {row["color"]}'
                    )
                    with ui.column().classes('gap-0.5'):
                        ui.label(row['actif']).classes('text-sm font-semibold').style(
                            f'color: {text_primary}'
                        )
                        with ui.row().classes('items-center gap-2'):
                            ui.label(row['cat']).classes('text-xs').style(
                                f'color: {text_secondary}'
                            )
                            for t in row['tags']:
                                ui.label(t).classes(
                                    'bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded'
                                )
                ui.label(row['valeur']).classes('text-sm').style(
                    f'color: {text_primary}; width: 8rem; text-align: right'
                )
                ui.label(row['cashflow']).classes('text-sm').style(
                    'color: #10b981; width: 6rem; text-align: right'
                )
                ui.label(row['rendement']).classes('text-sm font-medium').style(
                    'background-color: rgba(16,185,129,0.2); color: #10b981; '
                    'padding: 0.25rem 0.5rem; border-radius: 0.25rem; '
                    'width: fit-content; margin-left: auto;'
                )


def _allocation_card(card_style, text_primary, text_secondary):
    with ui.card().classes('p-5').style(card_style + ' width: 24rem'):
        ui.label("Allocation d'Actifs").classes('text-lg font-bold mb-4').style(
            f'color: {text_primary}'
        )
        with ui.row().classes('items-center gap-4'):
            ui.echart({
                'tooltip': {'trigger': 'item'},
                'series': [{
                    'type': 'pie',
                    'radius': ['60%', '85%'],
                    'avoidLabelOverlap': False,
                    'label': {'show': False},
                    'data': [
                        {'value': 73.1, 'name': 'Immobilier', 'itemStyle': {'color': '#3b82f6'}},
                        {'value': 23.8, 'name': 'Actifs Financiers', 'itemStyle': {'color': '#10b981'}},
                        {'value': 4.0, 'name': 'Trésorerie', 'itemStyle': {'color': '#a855f7'}},
                    ],
                }],
            }).classes('w-40 h-40')

            with ui.column().classes('gap-3').style('flex: 1'):
                _legend_row('Immobilier', '73.1%', '#3b82f6', text_primary, text_secondary)
                _legend_row('Actifs Financiers', '23.8%', '#10b981', text_primary, text_secondary)
                _legend_row('Trésorerie', '4.0%', '#a855f7', text_primary, text_secondary)


def _legend_row(label, value, color, text_primary, text_secondary):
    with ui.row().classes('items-center justify-between w-full'):
        with ui.row().classes('items-center gap-2'):
            ui.element('div').classes('w-2 h-2 rounded-full').style(
                f'background-color: {color}'
            )
            ui.label(label).classes('text-sm').style(f'color: {text_secondary}')
        ui.label(value).classes('text-sm font-bold').style(f'color: {text_primary}')