import os
from pathlib import Path
from nicegui import ui, app

# Initialisation de la BDD
from database.db import init_db
init_db()

# Dossier uploads exposé en statique
UPLOADS_DIR = Path(__file__).parent / 'uploads' / 'logos'
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.add_static_files('/uploads', str(UPLOADS_DIR.parent))

# Imports des pages
from pages import dashboard, portfolios, famille, portefeuille_detail
from components.layout import page_layout
from theme import get_colors


# ✅ Tâche de démarrage propre via app.on_startup
# Complètement découplée de tout contexte de page NiceGUI
# Pas de ui.notify() ici → uniquement des logs console
async def _startup_update_quotes():
    """
    Met à jour les cours au démarrage si pas fait aujourd'hui.
    Tourne dans la boucle asyncio de NiceGUI, sans contexte de page.
    """
    try:
        from nicegui import run
        from services.quotes_updater import update_all_quotes
        stats = await run.io_bound(update_all_quotes, False)
        print(f'✅ MAJ cours au démarrage terminée : {stats}')
    except Exception as e:
        print(f'❌ Erreur MAJ cours au démarrage : {e}')


app.on_startup(_startup_update_quotes)


@ui.page('/')
def index():
    dashboard.render()


@ui.page('/portefeuilles')
def portefeuilles_page():
    portfolios.render()


@ui.page('/portefeuilles/{member}')
def portefeuille_member(member: str):
    portfolios.render(member)


@ui.page('/portefeuille/{pid}')
def portefeuille_detail_page(pid: int):
    portefeuille_detail.render(pid)


@ui.page('/famille')
def famille_page():
    famille.render()


def make_simple_page(title, route):
    @ui.page(route)
    def _page():
        is_dark = page_layout(active_route=route)
        c = get_colors(is_dark)

        with ui.column().classes('w-full p-6 gap-4'):
            ui.label(title).classes('text-2xl font-bold').style(
                f'color: {c["text_primary"]}'
            )
            with ui.card().classes('w-full p-6 rounded-xl').style(
                f'background-color: {c["card_bg"]}; '
                f'border: 1px solid {c["card_border"]};'
            ):
                ui.label(f'Page {title} en construction...').style(
                    f'color: {c["text_secondary"]}'
                )
    return _page


make_simple_page('Immobilier', '/immobilier')
make_simple_page('Comptes', '/comptes')
make_simple_page('Investissements', '/investissements')
make_simple_page('Marchés', '/marches')
make_simple_page('Paramètres', '/parametres')


ui.run(
    title='Patrimoine',
    port=8080,
    storage_secret='patrimoine-secret-key-2024',
    reload=True,
)