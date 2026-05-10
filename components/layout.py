from nicegui import ui
from theme import init_theme, get_is_dark, get_colors
from components.header import create_header
from components.sidebar import create_sidebar
from components.refresh import clear_callbacks


def page_layout(active_route: str = '/'):
    # Important : nettoyer les callbacks de la page précédente
    clear_callbacks()

    _, toggle_fn = init_theme()
    is_dark = get_is_dark()
    c = get_colors(is_dark)

    bg_page = c["page_bg"]

    ui.query('body').style(f'background-color: {bg_page}')
    ui.query('.q-page').style(f'background-color: {bg_page}')
    ui.query('.nicegui-content').style('padding: 0')

    ui.add_head_html(f'''
        <style>
            .hover-item-dark:hover {{ background-color: #1e293b; color: #ffffff !important; }}
            .hover-item-light:hover {{ background-color: #f1f5f9; color: #0f172a !important; }}
            .q-page-container {{ background-color: {bg_page}; }}
        </style>
    ''')

    drawer = create_sidebar(active_route)
    create_header(toggle_fn, drawer)

    return is_dark