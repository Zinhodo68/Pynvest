from nicegui import ui
from theme import get_is_dark, get_colors
from database.db import get_all_membres
from components.refresh import register_refresh_callback


def create_header(toggle_fn, drawer):
    is_dark = get_is_dark()
    c = get_colors(is_dark)

    with ui.header(elevated=False).classes(
        'items-center justify-between px-6 py-3 border-b'
    ).style(
        f'background-color: {c["card_bg"]}; '
        f'border-color: {c["card_border"]};'
    ):
        # Partie gauche : hamburger + titre
        with ui.row().classes('items-center gap-4'):
            ui.button(icon='menu', on_click=drawer.toggle).props(
                'flat round dense'
            ).style(f'color: {c["text_primary"]}')

            with ui.column().classes('gap-0'):
                ui.label('Situation Patrimoniale').classes('text-2xl font-bold').style(
                    f'color: {c["text_primary"]}'
                )
                ui.label('Bienvenue sur votre tableau de bord familial consolidé.').style(
                    f'color: {c["text_secondary"]}; font-size: 0.875rem'
                )

        # Partie droite
        with ui.row().classes('items-center gap-4'):
            # ✨ Container réactif pour les badges
            badges_container = ui.row().classes('gap-2')

            def render_badges():
                badges_container.clear()
                membres = get_all_membres()
                with badges_container:
                    if membres:
                        for m in membres:
                            badge = ui.label(m['initiales']).classes(
                                'text-white text-xs font-bold '
                                'px-3 py-2 rounded-md cursor-pointer transition'
                            ).style(f'background-color: {m["couleur"]};')
                            with badge:
                                ui.tooltip(f'{m["prenom"]} {m["nom"]} — {m["role"]}')
                            badge.on(
                                'click',
                                lambda p=m['prenom'].lower(): ui.navigate.to(f'/portefeuilles/{p}')
                            )
                    else:
                        ui.button('+ Ajouter famille',
                                  on_click=lambda: ui.navigate.to('/famille')) \
                            .props('flat dense').style(f'color: {c["text_secondary"]}')

            render_badges()
            register_refresh_callback(render_badges)

            with ui.row().classes('items-center gap-1 cursor-pointer').style(
                f'color: {c["text_secondary"]}'
            ):
                ui.icon('visibility').classes('text-base')
                ui.label('Documents').classes('text-sm')

            with ui.row().classes('items-center gap-1 cursor-pointer relative').style(
                f'color: {c["text_secondary"]}'
            ):
                ui.icon('notifications').classes('text-base')
                ui.label('Tâches').classes('text-sm')
                ui.element('div').classes(
                    'absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full'
                )

            ui.button(
                icon='light_mode' if is_dark else 'dark_mode',
                on_click=toggle_fn
            ).props('flat round dense').style('color: #f59e0b')