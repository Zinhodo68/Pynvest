"""Graphique d'évolution multi-courbes."""
from datetime import date as _date, datetime
from nicegui import ui


def render_chart(valorisations, transactions, color, c, is_dark):
    """Graphique ECharts : valorisation + apports cumulés + +/- value."""
    text_color = c['text_primary']
    grid_color = c['card_border']

    if not valorisations and not transactions:
        ui.label('Aucune donnée de valorisation ou de transaction').style(
            f'color: {c["text_secondary"]}'
        )
        return

    # Préparation des dates en string ISO
    all_dates = set(str(v['date']) for v in valorisations)
    for t in transactions:
        all_dates.add(str(t['date']))
    sorted_dates = sorted(list(all_dates))

    valo_by_date = {str(v['date']): v['montant'] for v in valorisations}

    # Apports cumulés — UNIQUEMENT les flux externes (parent_transaction_id is None)
    apports_par_date = {}
    cumul = 0
    for d in sorted_dates:
        for t in transactions:
            if str(t['date']) == d:
                # 🚫 Exclure les arbitrages internes
                if t.get('parent_transaction_id') is not None:
                    continue
                if t['type'] == 'versement':
                    cumul += t['montant']
                elif t['type'] == 'retrait':
                    cumul -= t['montant']
        apports_par_date[d] = cumul

    # Interpolation des valeurs
    interpolated_valos = {}
    last_valo = 0
    valos_data = []  # Format [timestamp_ms, valeur] pour ECharts time axis
    apports_data = []
    plus_values_data = []

    for d in sorted_dates:
        if d in valo_by_date:
            last_valo = valo_by_date[d]

        interpolated_valos[d] = round(last_valo, 2)

        # Conversion ISO date → timestamp ms (ce qu'attend ECharts en mode 'time')
        try:
            ts_ms = int(datetime.fromisoformat(d).timestamp() * 1000)
        except Exception:
            continue

        ap = apports_par_date.get(d, 0)
        valos_data.append([ts_ms, round(last_valo, 2)])
        apports_data.append([ts_ms, round(ap, 2)])
        plus_values_data.append([ts_ms, round(last_valo - ap, 2)])

    # Marqueurs achats/ventes
    markers = []
    for t in transactions:
        if t['type'] in ('achat', 'vente'):
            symbol_emoji = '🛒' if t['type'] == 'achat' else '💹'
            color_marker = '#8b5cf6' if t['type'] == 'achat' else '#ec4899'
            date_str = str(t['date'])
            try:
                ts_ms = int(datetime.fromisoformat(date_str).timestamp() * 1000)
                markers.append({
                    'name': symbol_emoji,
                    'coord': [ts_ms, interpolated_valos.get(date_str, 0)],
                    'value': t['type'],
                    'itemStyle': {'color': color_marker},
                })
            except Exception:
                pass

    ui.echart({
        'tooltip': {
            'trigger': 'axis',
            'backgroundColor': '#0f172a',
            'borderColor': color,
            'textStyle': {'color': '#ffffff'},
            ':formatter': '''function(params) {
                if (!params || params.length === 0) return '';
                var d = new Date(params[0].value[0]);
                var dateStr = d.getDate().toString().padStart(2, '0') + '/' 
                            + (d.getMonth()+1).toString().padStart(2, '0') + '/'
                            + d.getFullYear();
                var html = '<b>' + dateStr + '</b><br/>';
                params.forEach(function(p) {
                    html += p.marker + ' ' + p.seriesName + ' : <b>' 
                          + p.value[1].toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) 
                          + ' €</b><br/>';
                });
                return html;
            }''',
        },
        'legend': {
            'data': ['Valorisation', 'Capital investi', '+/- value'],
            'textStyle': {'color': text_color},
            'top': 0,
        },
        'grid': {'left': 70, 'right': 30, 'top': 50, 'bottom': 60},
        'xAxis': {
            'type': 'time',
            'axisLine': {'lineStyle': {'color': grid_color}},
            'axisLabel': {
                'color': c['text_secondary'],
                'hideOverlap': True,
            },
            'splitLine': {'show': False},
        },
        'yAxis': [{
            'type': 'value',
            'name': 'EUR',
            'nameTextStyle': {'color': c['text_secondary']},
            'axisLine': {'lineStyle': {'color': grid_color}},
            'axisLabel': {
                'color': c['text_secondary'],
                'formatter': '{value} €',
            },
            'splitLine': {
                'lineStyle': {'color': grid_color, 'opacity': 0.3}
            },
        }],
        'dataZoom': [
            {'type': 'inside', 'start': 0, 'end': 100},
            {
                'type': 'slider', 'start': 0, 'end': 100,
                'height': 25, 'bottom': 5,
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
                'data': valos_data,
                'smooth': True,
                'symbol': 'none',
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
                'data': apports_data,
                'smooth': False,
                'step': 'end',
                'symbol': 'none',
                'lineStyle': {
                    'color': '#a855f7',
                    'width': 2,
                    'type': 'dashed'
                },
                'itemStyle': {'color': '#a855f7'},
            },
            {
                'name': '+/- value',
                'type': 'line',
                'data': plus_values_data,
                'smooth': True,
                'symbol': 'none',
                'lineStyle': {
                    'color': '#10b981',
                    'width': 1,
                    'opacity': 0.6
                },
                'itemStyle': {'color': '#10b981'},
            },
        ],
    }).classes('w-full').style('height: 400px;')