"""Graphique d'évolution de la valeur."""
from nicegui import ui


def render_chart(valorisations, transactions, color, c, is_dark):
    """Graphique ECharts : valorisation + capital investi."""
    text_color = c['text_primary']
    grid_color = c['card_border']

    dates = [v['date'] for v in valorisations]
    montants = [v['montant'] for v in valorisations]

    # Cumul des versements pour comparaison
    versements_par_date = {}
    for t in transactions:
        if t['type'] == 'versement':
            versements_par_date[t['date']] = versements_par_date.get(t['date'], 0) + t['montant']
        elif t['type'] == 'retrait':
            versements_par_date[t['date']] = versements_par_date.get(t['date'], 0) - t['montant']

    sorted_t_dates = sorted(versements_par_date.keys())
    cumul_par_date = {}
    cumul = 0
    for d in sorted_t_dates:
        cumul += versements_par_date[d]
        cumul_par_date[d] = cumul

    investis_a_date = []
    for d in dates:
        c_val = 0
        for td in sorted_t_dates:
            if td <= d:
                c_val = cumul_par_date[td]
        investis_a_date.append(c_val)

    ui.echart({
        'tooltip': {
            'trigger': 'axis',
            'backgroundColor': '#0f172a',
            'borderColor': color,
            'textStyle': {'color': '#ffffff'},
        },
        'legend': {
            'data': ['Valorisation', 'Capital investi'],
            'textStyle': {'color': text_color},
            'top': 0,
        },
        'grid': {'left': 60, 'right': 20, 'top': 40, 'bottom': 40},
        'xAxis': {
            'type': 'category',
            'data': dates,
            'axisLine': {'lineStyle': {'color': grid_color}},
            'axisLabel': {'color': c['text_secondary']},
        },
        'yAxis': {
            'type': 'value',
            'axisLine': {'lineStyle': {'color': grid_color}},
            'axisLabel': {'color': c['text_secondary'], 'formatter': '{value} €'},
            'splitLine': {'lineStyle': {'color': grid_color, 'opacity': 0.3}},
        },
        'series': [
            {
                'name': 'Valorisation',
                'type': 'line',
                'data': montants,
                'smooth': True,
                'lineStyle': {'color': color, 'width': 3},
                'itemStyle': {'color': color},
                'areaStyle': {
                    'color': {
                        'type': 'linear',
                        'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                        'colorStops': [
                            {'offset': 0, 'color': color + '60'},
                            {'offset': 1, 'color': color + '00'},
                        ]
                    }
                },
            },
            {
                'name': 'Capital investi',
                'type': 'line',
                'data': investis_a_date,
                'smooth': True,
                'lineStyle': {'color': '#a855f7', 'width': 2, 'type': 'dashed'},
                'itemStyle': {'color': '#a855f7'},
            },
        ],
    }).classes('w-full').style('height: 350px;')