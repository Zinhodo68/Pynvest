from nicegui import ui
from theme import get_is_dark, get_colors
from database.db import get_all_membres
# ÉTAPE 1: Importer l'état global partagé
from services._state import portfolio_state


@ui.refreshable
def render_header_badges():
    """
    Ce composant dynamique affiche les badges des membres dans le header.
    Il est "rafraîchissable" pour pouvoir changer son apparence (couleur/gris).
    """
    # On attache sa propre fonction de rafraîchissement à l'état global.
    # Ainsi, l'état pourra lui dire "redessine-toi !" après un clic.
    portfolio_state.header_refresh = render_header_badges.refresh

    is_dark = get_is_dark()
    c = get_colors(is_dark)
    membres = get_all_membres()

    with ui.row().classes('gap-2'):
        if not membres:
            ui.button('+ Ajouter famille', on_click=lambda: ui.navigate.to('/famille')) \
                .props('flat dense').style(f'color: {c["text_secondary"]}')
            return

        for m in membres:
            m_id = m['id']
            # On lit l'état global pour savoir si le membre est sélectionné ou a des portefeuilles
            has_pf = m_id in portfolio_state.membres_avec_pf
            is_selected = m_id in portfolio_state.selected

            initiales = m.get('initiales', f"{m['prenom'][0]}{m['nom'][0]}".upper())
            couleur = m.get('couleur', '#3b82f6')

            # ÉTAPE 2: Logique de style pour la sélection multiple
            if not has_pf:
                # Membre sans portefeuille : grisé foncé et inactif
                bg = 'transparent'
                text_color = '#9ca3af'
                cursor = 'cursor-not-allowed opacity-30'
                border = f'border border-[{c.get("card_border", "#e5e7eb")}]'
            elif is_selected:
                # Membre sélectionné : couleur vive, actif
                bg = couleur
                text_color = '#ffffff'
                cursor = 'cursor-pointer hover:opacity-90 shadow-sm'
                border = 'border-transparent'
            else:
                # Membre non sélectionné : badge grisé clair mais cliquable
                bg = '#e5e7eb' if not is_dark else '#374151'
                text_color = '#9ca3af'
                cursor = 'cursor-pointer hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors opacity-70 hover:opacity-100'
                border = 'border-transparent'

            # Le Badge rectangulaire
            badge = ui.label(initiales).classes(
                'text-xs font-bold px-3 py-2 rounded-md transition-all'
            ).style(f'background-color: {bg}; color: {text_color};')

            # ÉTAPE 3: Le clic ne navigue plus, il appelle la fonction toggle() de l'état global
            badge.on('click', lambda i=m_id: portfolio_state.toggle(i))

            with badge:
                ui.tooltip(f'{m["prenom"]} {m["nom"]}')


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
            ui.button(icon='menu', on_click=drawer.toggle).props('flat round dense').style(
                f'color: {c["text_primary"]}')
            with ui.column().classes('gap-0'):
                ui.label('Situation Patrimoniale').classes('text-2xl font-bold').style(f'color: {c["text_primary"]}')
                ui.label('Bienvenue sur votre tableau de bord familial consolidé.').style(
                    f'color: {c["text_secondary"]}; font-size: 0.875rem')

        # Partie droite
        with ui.row().classes('items-center gap-4'):
            # ÉTAPE 4: On appelle simplement notre nouveau composant dynamique
            render_header_badges()

            with ui.row().classes('items-center gap-1 cursor-pointer').style(f'color: {c["text_secondary"]}'):
                ui.icon('visibility').classes('text-base')
                ui.label('Documents').classes('text-sm')

            with ui.row().classes('items-center gap-1 cursor-pointer relative').style(f'color: {c["text_secondary"]}'):
                ui.icon('notifications').classes('text-base')
                ui.label('Tâches').classes('text-sm')
                ui.element('div').classes('absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full')

            ui.button(
                icon='light_mode' if is_dark else 'dark_mode',
                on_click=toggle_fn
            ).props('flat round dense').style('color: #f59e0b')