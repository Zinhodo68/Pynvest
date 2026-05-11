"""Gestion d'un état persistant (date dernière MAJ des cours, etc.)."""
import json
from datetime import date, datetime
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / 'app_state.json'


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