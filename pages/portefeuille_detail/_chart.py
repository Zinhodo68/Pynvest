"""Graphique d'évolution de la valorisation."""
from datetime import date as _date, datetime
from nicegui import ui


def render_chart(valorisations, transactions, color, c, is_dark):
    """Graphique ECharts de valorisation.

    Détails (capital investi, +/- value) affichés dans le tooltip au survol.
    """
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

    # Apports cumulés — UNIQUEMENT les flux externes
    apports_par_date = {}
    cumul = 0
    for d in sorted_dates:
        for t in transactions:
            if str(t['date']) == d:
                if t.get('parent_transaction_id') is not None:
                    continue
                if t['type'] == 'versement':
                    cumul += t['montant']
                elif t['type'] == 'retrait':
                    cumul -= t['montant']
        apports_par_date[d] = cumul

    # Construction des séries de données
    last_valo = 0
    interpolated_valos = {}
    valos_data = []  # [ts_ms, valeur €]
    apports_data = []  # [ts_ms, capital investi]
    plus_values_data = []  # [ts_ms, +/- value €]
    rendement_data = []  # [ts_ms, rendement %]

    for d in sorted_dates:
        if d in valo_by_date:
            last_valo = valo_by_date[d]
        interpolated_valos[d] = round(last_valo, 2)

        try:
            ts_ms = int(datetime.fromisoformat(d).timestamp() * 1000)
        except Exception:
            continue

        ap = apports_par_date.get(d, 0)
        pv = last_valo - ap
        rdt_pct = (pv / ap * 100) if ap > 0 else 0

        valos_data.append([ts_ms, round(last_valo, 2)])
        apports_data.append([ts_ms, round(ap, 2)])
        plus_values_data.append([ts_ms, round(pv, 2)])
        rendement_data.append([ts_ms, round(rdt_pct, 2)])

    # 🎯 Calcul des bornes Y pour CHAQUE mode
    def compute_bounds(values):
        """Calcule [min, max] avec marges 0.8/1.2."""
        if not values:
            return 0, 100
        v_min = min(values)
        v_max = max(values)
        if v_min >= 0:
            y_min = v_min * 0.9
        else:
            y_min = v_min * 1.1
        if v_max >= 0:
            y_max = v_max * 1.1
        else:
            y_max = v_max * 0.9
        if abs(y_max - y_min) < 0.5:
            y_min -= 1
            y_max += 1
        return round(y_min, 2), round(y_max, 2)

    valo_y_min, valo_y_max = compute_bounds([v[1] for v in valos_data])

    # ─── ECharts ───
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

                // Récupérer les valeurs des 4 séries (visibles + invisibles)
                var valo = null, capital = null, pv = null, rdt = null;
                params.forEach(function(p) {
                    if (p.seriesName === 'Valorisation') valo = p.value[1];
                    else if (p.seriesName === 'Capital investi') capital = p.value[1];
                    else if (p.seriesName === '+/- value') pv = p.value[1];
                    else if (p.seriesName === 'Rendement') rdt = p.value[1];
                });

                var fmt = function(n) {
                    return n.toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                };

                var html = '<b>📅 ' + dateStr + '</b><br/>';
                if (valo !== null) {
                    html += '💎 Valorisation : <b>' + fmt(valo) + ' €</b><br/>';
                }
                if (capital !== null) {
                    html += '💰 Capital investi : <b>' + fmt(capital) + ' €</b><br/>';
                }
                if (pv !== null) {
                    var emoji = pv >= 0 ? '✅' : '❌';
                    var sign = pv >= 0 ? '+' : '';
                    html += emoji + ' +/- value : <b>' + sign + fmt(pv) + ' €</b>';
                    if (rdt !== null) {
                        html += ' (<b>' + sign + fmt(rdt) + ' %</b>)';
                    }
                    html += '<br/>';
                }
                return html;
            }''',
        },
        'legend': {'show': False},  # Pas de légende, on a le switch
        'grid': {'left': 70, 'right': 30, 'top': 30, 'bottom': 60},
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
            'min': valo_y_min,
            'max': valo_y_max,
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
            # ─ Série visible : Valorisation ─
            {
                'name': 'Valorisation',
                'type': 'line',
                'data': valos_data,
                'smooth': True,
                'smoothMonotone': 'x',
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
                # 🆕 markPoint supprimé : plus de pins d'achat/vente
            },
            # ─ Séries invisibles (pour tooltip uniquement) ─
            {
                'name': 'Capital investi',
                'type': 'line',
                'data': apports_data,
                'symbol': 'none',
                'lineStyle': {'opacity': 0},  # Invisible
                'itemStyle': {'opacity': 0},
                'silent': True,
            },
            {
                'name': '+/- value',
                'type': 'line',
                'data': plus_values_data,
                'symbol': 'none',
                'lineStyle': {'opacity': 0},
                'itemStyle': {'opacity': 0},
                'silent': True,
            },
            {
                'name': 'Rendement',
                'type': 'line',
                'data': rendement_data,
                'symbol': 'none',
                'lineStyle': {'opacity': 0},
                'itemStyle': {'opacity': 0},
                'silent': True,
            },
        ],
    }).classes('w-full').style('height: 400px;')

