from nicegui import ui
from components.layout import page_layout


def render():
    page_layout(active_route='/immobilier')
    with ui.column().classes('w-full p-6 gap-4'):
        ui.label('Immobilier').classes('text-2xl font-bold text-slate-900 dark:text-white')
        with ui.card().classes(
            'w-full p-6 bg-white dark:bg-slate-900 '
            'border border-slate-200 dark:border-slate-800 rounded-xl'
        ):
            ui.label('Liste de vos biens immobiliers.').classes(
                'text-slate-600 dark:text-slate-400'
            )