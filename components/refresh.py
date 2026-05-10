"""Système simple de rafraîchissement des composants partagés."""

_callbacks = []


def register_refresh_callback(cb):
    """Enregistre une fonction à appeler quand on veut rafraîchir le layout."""
    _callbacks.append(cb)


def refresh_layout():
    """Déclenche le rafraîchissement de tous les composants enregistrés."""
    for cb in _callbacks:
        try:
            cb()
        except Exception as e:
            print(f'Erreur refresh: {e}')


def clear_callbacks():
    """À appeler au début de chaque page pour éviter l'accumulation."""
    _callbacks.clear()