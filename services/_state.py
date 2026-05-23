"""Gestion d'un état persistant (date dernière MAJ des cours, etc.) et de l'état UI (filtres)."""
import json
from datetime import date, datetime
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / 'app_state.json'


# ─────────────────────────────────────────────
# 1. ÉTAT PERSISTANT (JSON - MAJ des cours)
# ─────────────────────────────────────────────

def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f'Erreur sauvegarde état: {e}')


def get_last_update_date() -> date | None:
    """Retourne la date de dernière mise à jour des cours."""
    state = _load_state()
    iso = state.get('last_quotes_update')
    if iso:
        try:
            return date.fromisoformat(iso)
        except ValueError:
            return None
    return None


def set_last_update_date(d: date):
    """Enregistre la date de dernière mise à jour."""
    state = _load_state()
    state['last_quotes_update'] = d.isoformat()
    state['last_quotes_update_timestamp'] = datetime.now().isoformat()
    _save_state(state)


def is_update_needed() -> bool:
    """True si on n'a pas mis à jour aujourd'hui."""
    last = get_last_update_date()
    if last is None:
        return True
    return last < date.today()


# ─────────────────────────────────────────────
# 2. ÉTAT UI VOLATILE (Filtres des Portefeuilles)
# ─────────────────────────────────────────────

class PortfolioFilterState:
    def __init__(self):
        self.selected = set()
        self.membres_avec_pf = set()

        # Stockage des fonctions de rafraîchissement des différentes pages/composants
        self.dashboard_refresh = None
        self.header_refresh = None

    def toggle(self, m_id):
        # On ne fait rien si le membre cliqué n'a aucun portefeuille
        if m_id not in self.membres_avec_pf:
            return

        # Logique de sélection/désélection (Switch)
        if m_id in self.selected:
            # On empêche de tout décocher (garde au moins 1)
            if len(self.selected) > 1:
                self.selected.remove(m_id)
        else:
            self.selected.add(m_id)

        # On déclenche la mise à jour visuelle du Header ET de la page Portefeuilles
        if self.header_refresh:
            try:
                self.header_refresh()
            except Exception:
                pass

        if self.dashboard_refresh:
            try:
                self.dashboard_refresh()
            except Exception:
                pass


# Instance unique (Singleton) importable partout dans l'application
portfolio_state = PortfolioFilterState()