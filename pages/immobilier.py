from nicegui import ui
from components.layout import page_layout


def render():
    is_dark = page_layout(active_route='/immobilier')

    text_primary = '#ffffff' if is_dark else '#0f172a'
    text_secondary = '#94a3b8' if is_dark else '#64748b'
    card_bg = '#0f172a' if is_dark else '#ffffff'
    card_border = '#1e293b' if is_dark else '#e2e8f0'

    with ui.column().classes('w-full p-6 gap-4'):
        ui.label('Immobilier').classes('text-2xl font-bold').style(
            f'color: {text_primary}'
        )
        with ui.card().classes('w-full p-6 rounded-xl').style(
                f'background-color: {card_bg}; border: 1px solid {card_border};'
        ):
            ui.label('Liste de vos biens immobiliers.').style(
                f'color: {text_secondary}'
            )