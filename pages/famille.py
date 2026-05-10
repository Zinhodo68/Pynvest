from datetime import date, datetime
from nicegui import ui
from sqlalchemy import select

from components.layout import page_layout
from components.refresh import refresh_layout
from theme import get_colors
from database.db import get_session
from database.models import Membre


ROLES = ['Père', 'Mère', 'Enfant', 'Conjoint(e)', 'Autre']
COULEURS = [
    ('Bleu', '#3b82f6'),
    ('Violet', '#8b5cf6'),
    ('Rose', '#ec4899'),
    ('Orange', '#f97316'),
    ('Vert', '#10b981'),
    ('Rouge', '#ef4444'),
]


def render():
    is_dark = page_layout(active_route='/famille')
    c = get_colors(is_dark)

    container = ui.column().classes('w-full p-6 gap-4')

    def refresh():
        container.clear()
        with container:
            _render_content(c, is_dark, refresh)
        # Rafraîchit le header (badges) et le sidebar (sous-menu Portefeuilles)
        refresh_layout()

    refresh()


def _render_content(c, is_dark, refresh):
    # Header de la page
    with ui.row().classes('w-full items-center justify-between'):
        with ui.column().classes('gap-1'):
            ui.label('Famille').classes('text-2xl font-bold').style(
                f'color: {c["text_primary"]}'
            )
            ui.label('Gérez les membres de votre famille.').style(
                f'color: {c["text_secondary"]}'
            )
        ui.button('+ Ajouter un membre', on_click=lambda: _open_dialog(c, refresh)) \
            .props('unelevated').classes('bg-blue-600 text-white')

    # Récupération des membres
    with get_session() as session:
        membres = session.execute(select(Membre).order_by(Membre.id)).scalars().all()
        membres_data = [m.to_dict() for m in membres]

    # État vide
    if not membres_data:
        with ui.card().classes('w-full p-12 rounded-xl items-center').style(
            f'background-color: {c["card_bg"]}; '
            f'border: 1px solid {c["card_border"]};'
        ):
            ui.icon('group_off').classes('text-6xl').style(
                f'color: {c["text_secondary"]}'
            )
            ui.label('Aucun membre dans votre famille').classes('text-lg mt-4').style(
                f'color: {c["text_primary"]}'
            )
            ui.label('Cliquez sur "Ajouter un membre" pour commencer.').style(
                f'color: {c["text_secondary"]}'
            )
        return

    # Grille des membres
    with ui.row().classes('w-full gap-4 flex-wrap'):
        for m in membres_data:
            _render_member_card(m, c, is_dark, refresh)


def _render_member_card(m, c, is_dark, refresh):
    with ui.card().classes('p-5 rounded-xl gap-3').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'width: 280px;'
    ):
        # Header carte : avatar + actions
        with ui.row().classes('w-full items-start justify-between'):
            with ui.row().classes('items-center gap-3'):
                # Avatar avec initiales
                with ui.element('div').classes(
                    'w-12 h-12 rounded-full flex items-center justify-center'
                ).style(f'background-color: {m["couleur"]}'):
                    ui.label(m['initiales']).classes('text-white font-bold text-sm')
                with ui.column().classes('gap-0'):
                    ui.label(f'{m["prenom"]} {m["nom"]}').classes('font-semibold').style(
                        f'color: {c["text_primary"]}'
                    )
                    ui.label(m['role']).classes('text-xs').style(
                        f'color: {c["text_secondary"]}'
                    )

            # Menu actions
            with ui.button(icon='more_vert').props('flat round dense size=sm').style(
                f'color: {c["text_secondary"]}'
            ):
                with ui.menu():
                    ui.menu_item(
                        'Modifier',
                        on_click=lambda mid=m['id']: _open_dialog(c, refresh, mid)
                    )
                    ui.menu_item(
                        'Supprimer',
                        on_click=lambda mid=m['id'], name=f'{m["prenom"]} {m["nom"]}':
                            _confirm_delete(mid, name, refresh)
                    )

        # Séparateur
        ui.element('div').classes('h-px w-full').style(
            f'background-color: {c["card_border"]}'
        )

        # Infos
        with ui.column().classes('gap-2'):
            if m['email']:
                with ui.row().classes('items-center gap-2'):
                    ui.icon('mail').classes('text-sm').style(
                        f'color: {c["text_secondary"]}'
                    )
                    ui.label(m['email']).classes('text-xs').style(
                        f'color: {c["text_secondary"]}'
                    )

            # Date de naissance au format français (JJ/MM/AAAA)
            if m['date_naissance']:
                dt = date.fromisoformat(m['date_naissance'])
                date_fr = dt.strftime('%d/%m/%Y')

                with ui.row().classes('items-center gap-2'):
                    ui.icon('cake').classes('text-sm').style(
                        f'color: {c["text_secondary"]}'
                    )
                    ui.label(date_fr).classes('text-xs').style(
                        f'color: {c["text_secondary"]}'
                    )


def _open_dialog(c, refresh, member_id: int = None):
    """Dialogue d'ajout/édition d'un membre."""
    is_edit = member_id is not None
    data = {
        'prenom': '', 'nom': '', 'initiales': '', 'role': 'Enfant',
        'date_naissance': None, 'email': '', 'couleur': '#3b82f6'
    }

    if is_edit:
        with get_session() as session:
            m = session.get(Membre, member_id)
            if m:
                data = m.to_dict()

    # Préparation de la date pour le formulaire (format JJ/MM/AAAA)
    date_initiale_fr = ''
    if data['date_naissance']:
        date_initiale_fr = date.fromisoformat(
            data['date_naissance']
        ).strftime('%d/%m/%Y')

    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4').style(
        f'background-color: {c["card_bg"]}; '
        f'border: 1px solid {c["card_border"]}; '
        f'min-width: 450px;'
    ):
        ui.label('Modifier un membre' if is_edit else 'Ajouter un membre') \
            .classes('text-xl font-bold').style(f'color: {c["text_primary"]}')

        prenom_input = ui.input('Prénom', value=data['prenom']).classes('w-full')
        nom_input = ui.input('Nom', value=data['nom']).classes('w-full')
        initiales_input = ui.input(
            'Initiales (2-3 lettres)', value=data['initiales']
        ).classes('w-full').props('maxlength=3')

        role_input = ui.select(ROLES, value=data['role'], label='Rôle').classes('w-full')

        # Date de naissance avec masque français
        with ui.input('Date de naissance', value=date_initiale_fr) \
                .classes('w-full') \
                .props('mask="##/##/####" placeholder="JJ/MM/AAAA"') as date_input:
            with ui.menu().props('no-parent-event') as menu:
                with ui.date().bind_value(date_input).props('mask="DD/MM/YYYY"'):
                    with ui.row().classes('justify-end'):
                        ui.button('Fermer', on_click=menu.close).props('flat')
            with date_input.add_slot('append'):
                ui.icon('edit_calendar').on('click', menu.open).classes('cursor-pointer')

        email_input = ui.input('Email', value=data['email'] or '').classes('w-full')

        # Sélection de couleur
        ui.label('Couleur du badge').style(f'color: {c["text_secondary"]}')
        couleur_state = {'value': data['couleur']}
        with ui.row().classes('gap-2'):
            color_buttons = []
            for label, color in COULEURS:
                btn = ui.button().style(
                    f'background-color: {color}; width: 32px; height: 32px; '
                    f'border-radius: 50%; min-width: 0; padding: 0; '
                    f'border: {"3px solid white" if color == couleur_state["value"] else "none"};'
                ).props('flat dense')

                def make_handler(c_val):
                    def handler():
                        couleur_state['value'] = c_val
                        for other_btn, (_, other_color) in zip(color_buttons, COULEURS):
                            other_btn.style(
                                f'background-color: {other_color}; '
                                f'width: 32px; height: 32px; '
                                f'border-radius: 50%; min-width: 0; padding: 0; '
                                f'border: {"3px solid white" if other_color == c_val else "none"};'
                            )
                    return handler
                btn.on('click', make_handler(color))
                color_buttons.append(btn)

        # Auto-génération des initiales depuis prénom + nom
        def auto_initials():
            if not initiales_input.value or len(initiales_input.value) < 2:
                p = (prenom_input.value or '').strip()
                n = (nom_input.value or '').strip()
                if p and n:
                    initiales_input.value = (p[0] + n[0]).upper()
                elif p:
                    initiales_input.value = p[:2].upper()

        prenom_input.on('blur', auto_initials)
        nom_input.on('blur', auto_initials)

        # Boutons d'action
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Annuler', on_click=dialog.close).props('flat').style(
                f'color: {c["text_secondary"]}'
            )

            def save():
                # Validations
                if not prenom_input.value or not nom_input.value:
                    ui.notify('Prénom et nom sont obligatoires', type='negative')
                    return
                if not initiales_input.value:
                    ui.notify('Les initiales sont obligatoires', type='negative')
                    return

                # Parsing de la date saisie (FR vers objet date Python)
                date_val = None
                if date_input.value:
                    try:
                        date_val = datetime.strptime(
                            date_input.value, '%d/%m/%Y'
                        ).date()
                    except ValueError:
                        ui.notify(
                            'Format de date invalide (attendu : JJ/MM/AAAA)',
                            type='negative'
                        )
                        return

                # Sauvegarde en base
                with get_session() as session:
                    if is_edit:
                        m = session.get(Membre, member_id)
                        m.prenom = prenom_input.value
                        m.nom = nom_input.value
                        m.initiales = initiales_input.value.upper()
                        m.role = role_input.value
                        m.date_naissance = date_val
                        m.email = email_input.value or None
                        m.couleur = couleur_state['value']
                    else:
                        m = Membre(
                            prenom=prenom_input.value,
                            nom=nom_input.value,
                            initiales=initiales_input.value.upper(),
                            role=role_input.value,
                            date_naissance=date_val,
                            email=email_input.value or None,
                            couleur=couleur_state['value'],
                        )
                        session.add(m)
                    session.commit()

                ui.notify(
                    'Membre modifié' if is_edit else 'Membre ajouté',
                    type='positive'
                )
                dialog.close()
                refresh()  # rafraîchit la grille + le header + le sidebar

            ui.button('Enregistrer', on_click=save).props('unelevated') \
                .classes('bg-blue-600 text-white')

    dialog.open()


def _confirm_delete(member_id: int, name: str, refresh):
    """Dialogue de confirmation avant suppression."""
    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4'):
        ui.label('Confirmer la suppression').classes('text-xl font-bold')
        ui.label(f'Voulez-vous vraiment supprimer {name} ?')

        def do_delete():
            with get_session() as session:
                m = session.get(Membre, member_id)
                if m:
                    session.delete(m)
                    session.commit()
            ui.notify(f'{name} a été supprimé', type='warning')
            dialog.close()
            refresh()  # rafraîchit la grille + le header + le sidebar

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Annuler', on_click=dialog.close).props('flat')
            ui.button('Supprimer', on_click=do_delete).props('unelevated') \
                .classes('bg-red-600 text-white')

    dialog.open()