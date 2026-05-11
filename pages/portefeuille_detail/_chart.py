"""Graphique d'évolution multi-courbes."""
from datetime import date, timedelta
from nicegui import ui


def render_chart(valorisations, transactions, color, c, is_dark):
    """Graphique ECharts : valorisation + apports cumulés + +/- value.

    - Courbe pleine : valorisation du portefeuille
    - Courbe pointillée : capital investi (apports cumulés)
    - Aire entre les deux : +/- value latente (verte/rouge)
    """
    text_color = c['text_primary']
    grid_color = c['card_border']

    if not valorisations:
        ui.label('Aucune donnée de valorisation').style(
            f'color: {c["text_secondary"]}'
        )
        return

    # ── Préparation des données ──
    # Liste de toutes les dates concernées (valorisations + transactions)
    all_dates = set(v['date'] for v in valorisations)
    for t in transactions:
        all_dates.add(t['date'])
    sorted_dates = sorted(all_dates)

    # Index des valorisations par date
    valo_by_date = {v['date']: v['montant'] for v in valorisations}

    # Calcul des apports cumulés à chaque date
    apports_par_date = {}
    cumul = 0
    for d in sorted_dates:
        # On somme tous les apports/retraits qui ont eu lieu ce jour
        for t in transactions:
            if t['date'] == d:
                if t['type'] == 'versement':
                    cumul += t['montant']
                elif t['type'] == 'retrait':
                    cumul -= t['montant']
        apports_par_date[d] = cumul

    # Valorisations interpolées (on prolonge la dernière valeur connue)
    valos = []
    apports = []
    plus_values = []
    last_valo = 0
    for d in sorted_dates:
        if d in valo_by_date:
            last_valo = valo_by_date[d]
        valos.append(round(last_valo, 2))
        ap = apports_par_date.get(d, 0)
        apports.append(round(ap, 2))
        plus_values.append(round(last_valo - ap, 2))

    # Marqueurs pour les achats/ventes
    markers = []
    for t in transactions:
        if t['type'] in ('achat', 'vente'):
            symbol_emoji = '🛒' if t['type'] == 'achat' else '💹'
            color_marker = '#8b5cf6' if t['type'] == 'achat' else '#ec4899'
            markers.append({
                'name': symbol_emoji,
                'coord': [t['date'], valo_by_date.get(t['date'], 0)],
                'value': t['type'],
                'itemStyle': {'color': color_marker},
            })

    ui.echart({
        'tooltip': {
            'trigger': 'axis',
            'backgroundColor': '#0f172a',
            'borderColor': color,
            'textStyle': {'color': '#ffffff'},
            'formatter': None,  # Format par défaut
        },
        'legend': {
            'data': ['Valorisation', 'Capital investi', '+/- value'],
            'textStyle': {'color': text_color},
            'top': 0,
        },
        'grid': {'left': 70, 'right': 30, 'top': 50, 'bottom': 60},
        'xAxis': {
            'type': 'category',
            'data': sorted_dates,
            'axisLine': {'lineStyle': {'color': grid_color}},
            'axisLabel': {'color': c['text_secondary'], 'rotate': 45},
        },
        'yAxis': [
            {
                'type': 'value',
                'name': 'EUR',
                'nameTextStyle': {'color': c['text_secondary']},
                'axisLine': {'lineStyle': {'color': grid_color}},
                'axisLabel': {
                    'color': c['text_secondary'],
                    'formatter': '{value} €',
                },
                'splitLine': {'lineStyle': {'color': grid_color, 'opacity': 0.3}},
            },
        ],
        'dataZoom': [
            {
                'type': 'inside',
                'start': 0,
                'end': 100,
            },
            {
                'type': 'slider',
                'start': 0,
                'end': 100,
                'height': 25,
                'bottom': 5,
                'borderColor': grid_color,
                'fillerColor': color + '30',
                'handleStyle': {'color': color},
                'textStyle': {'color': c['text_secondary']},
            },
        ],
        'series': [
            {
                'name': 'Valorisation',
                'type': 'line',
                'data': valos,
                'smooth': True,
                'symbol': 'circle',
                'symbolSize': 6,
                'lineStyle': {'color': color, 'width': 3},
                'itemStyle': {'color': color},
                'areaStyle': {
                    'color': {
                        'type': 'linear',
                        'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                        'colorStops': [
                            {'offset': 0, 'color': color + '40'},
                            {'offset': 1, 'color': color + '00'},
                        ]
                    }
                },
                'markPoint': {
                    'data': markers,
                    'symbol': 'pin',
                    'symbolSize': 30,
                    'label': {'show': False},
                } if markers else {},
            },
            {
                'name': 'Capital investi',
                'type': 'line',
                'data': apports,
                'smooth': False,
                'step': 'end',  # Marche d'escalier (plus juste pour des apports)
                'symbol': 'none',
                'lineStyle': {'color': '#a855f7', 'width': 2, 'type': 'dashed'},
                'itemStyle': {'color': '#a855f7'},
            },
            {
                'name': '+/- value',
                'type': 'line',
                'data': plus_values,
                'smooth': True,
                'symbol': 'none',
                'lineStyle': {'color': '#10b981', 'width': 1, 'opacity': 0.6},
                'itemStyle': {'color': '#10b981'},
            },
        ],
    }).classes('w-full').style('height: 400px;')