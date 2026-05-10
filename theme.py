from nicegui import ui, app

# État global persistant (storage côté serveur)
def get_is_dark():
    return app.storage.general.get('dark_mode', True)

def set_is_dark(value: bool):
    app.storage.general['dark_mode'] = value


def apply_theme_script():
    """Injecte le JS qui applique la classe 'dark' sur <html> pour Tailwind."""
    ui.add_head_html('''
        <script>
        function applyDarkClass(isDark) {
            if (isDark) {
                document.documentElement.classList.add('dark');
                document.body.classList.add('dark');
            } else {
                document.documentElement.classList.remove('dark');
                document.body.classList.remove('dark');
            }
        }
        </script>
        <style>
            /* Tailwind dark mode basé sur la classe */
            html.dark { color-scheme: dark; }
        </style>
    ''')


def init_theme():
    """À appeler dans chaque page. Retourne (dark_mode_element, toggle_fn)."""
    apply_theme_script()

    is_dark = get_is_dark()
    dark = ui.dark_mode(value=is_dark)

    # Applique immédiatement la classe dark sur <html>
    ui.run_javascript(f'applyDarkClass({str(is_dark).lower()})')

    def toggle():
        new_value = not dark.value
        dark.value = new_value
        set_is_dark(new_value)
        ui.run_javascript(f'applyDarkClass({str(new_value).lower()})')
        # Recharge la page pour mettre à jour l'icône et les styles
        ui.navigate.reload()

    return dark, toggle

def get_colors(is_dark: bool):
    """Retourne les couleurs du thème actuel."""
    return {
        'text_primary': '#ffffff' if is_dark else '#0f172a',
        'text_secondary': '#94a3b8' if is_dark else '#64748b',
        'card_bg': '#0f172a' if is_dark else '#ffffff',
        'card_border': '#1e293b' if is_dark else '#e2e8f0',
        'page_bg': '#020617' if is_dark else '#f8fafc',
    }