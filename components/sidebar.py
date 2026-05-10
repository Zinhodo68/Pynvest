from nicegui import ui
from theme import get_is_dark, get_colors
from database.db import get_all_membres
from components.refresh import register_refresh_callback


def _build_menu_items():
    """Construit la liste des items de menu avec les membres dynamiques."""
    membres = get_all_membres()

    portefeuilles_children = []
    for m in membres:
        portefeuilles_children.append({
            'label': f'Portefeuille {m["prenom"]}',
            'route': f'/portefeuilles/{m["prenom"].lower()}',
        })

    if not portefeuilles_children:
        portefeuilles_children = [
            {'label': '+ Ajouter un membre', 'route': '/famille'}
        ]

    return [
        {'icon': 'dashboard', 'label': 'Tableau de bord', 'route': '/'},
        {'icon': 'account_balance_wallet', 'label': 'Portefeuilles',
         'route': '/portefeuilles', 'children': portefeuilles_children},
        {'icon': 'home', 'label': 'Immobilier', 'route': '/immobilier'},
        {'icon': 'account_balance', 'label': 'Comptes', 'route': '/comptes'},
        {'icon': 'trending_up', 'label': 'Investissements', 'route': '/investissements'},
        {'icon': 'group', 'label': 'Famille', 'route': '/famille'},
        {'icon': 'show_chart', 'label': 'Marchés', 'route': '/marches'},
    ]


def create_sidebar(active_route: str = '/'):
    is_dark = get_is_dark()
    c = get_colors(is_dark)

    drawer = ui.left_drawer(fixed=True, bordered=False, value=True).classes('p-0').style(
        f'width: 260px; background-color: {c["card_bg"]}; '
        f'border-right: 1px solid {c["card_border"]};'
    )

    with drawer:
        with ui.row().classes('items-center justify-between w-full px-4 py-4'):
            with ui.row().classes('items-center gap-3'):
                with ui.element('div').classes(
                    'w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center'
                ):
                    ui.icon('trending_up').classes('text-white text-xl')
                ui.label('Patrimoine').classes('text-lg font-bold').style(
                    f'color: {c["text_primary"]}'
                )
            ui.button(icon='chevron_left', on_click=drawer.toggle).props(
                'flat round dense'
            ).style(f'color: {c["text_secondary"]}')

        # ✨ Container réactif pour le menu
        menu_container = ui.column().classes('w-full gap-1 px-3 mt-2')

        def render_menu():
            menu_container.clear()
            with menu_container:
                for item in _build_menu_items():
                    _render_menu_item(item, active_route, is_dark, c)

        render_menu()
        register_refresh_callback(render_menu)

    return drawer


def _render_menu_item(item, active_route, is_dark, c):
    has_children = 'children' in item
    is_active_self = active_route == item['route']
    is_active_branch = has_children and any(
        ch['route'] == active_route for ch in item.get('children', [])
    )
    is_active = is_active_self or is_active_branch
    # ✅ Ouvert si actif OU si on est sur l'item parent lui-même
    expanded = {'value': has_children and (is_active_branch or is_active_self)}

    if is_active_self and not has_children:
        item_style = 'background-color: #2563eb; color: #ffffff;'
    elif is_active_self and has_children:
        # ✅ L'item parent peut aussi être actif (page /portefeuilles)
        item_style = 'background-color: #2563eb; color: #ffffff;'
    elif is_active_branch and has_children:
        item_style = (
            f'background-color: {"#1e293b" if is_dark else "#f1f5f9"}; '
            f'color: {c["text_primary"]};'
        )
    else:
        item_style = f'color: {"#94a3b8" if is_dark else "#475569"};'

    hover_class = 'hover-item-dark' if is_dark else 'hover-item-light'

    item_row = ui.row().classes(
        f'items-center gap-3 w-full px-4 py-2.5 rounded-lg cursor-pointer transition {hover_class}'
    ).style(item_style)

    chevron = None
    with item_row:
        ui.icon(item['icon']).classes('text-lg')
        ui.label(item['label']).classes('text-sm font-medium').style('flex: 1')
        if has_children:
            chevron = ui.icon(
                'expand_more' if expanded['value'] else 'chevron_right'
            ).classes('text-base')

    if has_children:
        children_container = ui.column().classes('w-full gap-1 pl-8 mt-1')
        children_container.set_visibility(expanded['value'])

        with children_container:
            for child in item['children']:
                child_active = active_route == child['route']
                if child_active:
                    cstyle = 'background-color: #2563eb; color: #ffffff; font-weight: 500;'
                else:
                    cstyle = f'color: {"#94a3b8" if is_dark else "#64748b"};'
                ui.label(child['label']).classes(
                    'w-full px-4 py-2 rounded-lg text-sm cursor-pointer transition'
                ).style(cstyle).on('click', lambda r=child['route']: ui.navigate.to(r))

        ui.element('div').classes('h-px my-2 mx-4').style(
            f'background-color: {c["card_border"]}'
        )

        # ✅ NOUVEAU comportement : navigue ET déroule
        def handle_parent_click():
            # Si on est déjà sur la page parent, juste toggle
            if active_route == item['route']:
                expanded['value'] = not expanded['value']
                children_container.set_visibility(expanded['value'])
                if chevron:
                    chevron.props(
                        f'name={"expand_more" if expanded["value"] else "chevron_right"}'
                    )
            else:
                # Sinon, navigue (le menu sera automatiquement ouvert au rechargement
                # car is_active_self sera True)
                ui.navigate.to(item['route'])

        item_row.on('click', handle_parent_click)
    else:
        item_row.on('click', lambda r=item['route']: ui.navigate.to(r))