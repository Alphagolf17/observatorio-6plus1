"""Backtest exploratorio 6+1 sobre precios ajustados desde 2016.
Señales técnicas conocidas al cierre; retornos futuros medidos desde ese cierre.
La ejecución real al cierre no está garantizada. No incluye costes.
"""
import csv
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path('historico_inicial')
OUT = Path('output')
SYMBOLS = ('SPY', 'QQQ', 'SMH', 'ASML', 'AVGO')
HORIZONS = (5, 10, 20)


def read_market(symbol):
    path = ROOT / f'market_{symbol}_adjusted.csv'
    if not path.exists():
        raise SystemExit(f'Falta {path}. Ejecuta primero la descarga historica.')
    rows = {}
    with path.open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            try:
                price = float(r['close'])
                if price > 0 and r.get('price_basis') == 'dividend_and_split_adjusted':
                    rows[r['date']] = price
            except (ValueError, TypeError, KeyError):
                continue
    return dict(sorted(rows.items()))


def stats(values):
    if not values:
        return None
    return {'n': len(values), 'mean_pct': round(mean(values), 3),
            'median_pct': round(median(values), 3),
            'positive_pct': round(100 * sum(v > 0 for v in values) / len(values), 1)}


def evaluate(signals, prices, horizon, nonoverlap=False):
    all_r, low, high = [], [], []
    last_selected = -horizon
    for i, score in signals:
        if i + horizon >= len(prices):
            continue
        if nonoverlap and i - last_selected < horizon:
            continue
        ret = (prices[i + horizon] / prices[i] - 1) * 100
        all_r.append(ret)
        (high if score >= 2 else low).append(ret)
        last_selected = i
    return {'all_days': stats(all_r), '0_or_1_adverse_signal': stats(low),
            '2_or_3_adverse_signals': stats(high),
            'mean_difference_high_minus_low_pp': round(mean(high) - mean(low), 3) if high and low else None,
            'enough_samples_in_both_groups': len(low) >= 20 and len(high) >= 20}


def main():
    series = {s: read_market(s) for s in SYMBOLS}
    dates = list(series['SPY'])
    prices = list(series['SPY'].values())
    if len(dates) < 100:
        raise SystemExit('Historico SPY insuficiente.')
    aligned = {s: [series[s].get(d) for d in dates] for s in SYMBOLS}
    signals = []
    for i in range(20, len(dates)):
        if any(aligned[s][i] is None or aligned[s][i-20] is None
               for s in ('SPY', 'QQQ', 'SMH')):
            continue
        window = aligned['SPY'][i-19:i+1]
        if any(x is None for x in window):
            continue
        returns = {s: (aligned[s][i] / aligned[s][i-20] - 1) * 100
                   for s in ('SPY', 'QQQ', 'SMH')}
        adverse = int(returns['SMH'] - returns['SPY'] < -5)
        adverse += int(returns['QQQ'] - returns['SPY'] < -2)
        adverse += int(prices[i] < mean(window))
        signals.append((i, adverse))

    result = {
        'method': 'Estudio retrospectivo exploratorio de tres senales tecnicas, no del semaforo macro.',
        'source': 'Yahoo Finance via yfinance; precios ajustados por dividendos y splits',
        'start_date': dates[0], 'end_date': dates[-1],
        'spy_sessions': len(dates), 'evaluated_signal_days': len(signals),
        'rules': ['SMH - SPY a 20 sesiones < -5 pp', 'QQQ - SPY a 20 sesiones < -2 pp',
                  'SPY bajo su media de 20 sesiones'],
        'horizons': {},
        'limitations': [
            'Los resultados diarios se solapan; la muestra no solapada es mas conservadora, pero no garantiza independencia.',
            'Los umbrales se eligieron tras observar datos recientes: riesgo de sobreajuste.',
            'No hay validacion fuera de muestra ni prueba de significacion estadistica.',
            'Se supone entrada al cierre que genero la senal; no es necesariamente ejecutable a ese precio.',
            'No incluye comisiones, spreads, impuestos ni slippage.',
            'Precios ajustados historicos pueden incorporar revisiones y no representan una simulacion exacta de operativa.',
            'No incluye indicadores macro alineados por fecha de publicacion.',
            'No hay garantia de capacidad predictiva ni recomendacion automatica.'
        ]
    }
    for h in HORIZONS:
        result['horizons'][str(h)] = {
            'overlapping': evaluate(signals, prices, h),
            'non_overlapping': evaluate(signals, prices, h, nonoverlap=True)
        }
    OUT.mkdir(exist_ok=True)
    (OUT / 'backtest_6plus1.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Backtest historico 6+1 (exploratorio)', '',
             f"Periodo: {result['start_date']} a {result['end_date']}",
             f"Sesiones SPY: {result['spy_sessions']}; dias con senal: {result['evaluated_signal_days']}",
             'Precios ajustados; no es un backtest de estrategia ejecutable.', '',
             '| Horizonte | Muestra | 0-1 senales | 2-3 senales | Diferencia |',
             '|---|---|---|---|---|']
    for h, variants in result['horizons'].items():
        for label, key in [('Diaria solapada', 'overlapping'), ('Sin solapamiento', 'non_overlapping')]:
            d = variants[key]
            def fmt(x):
                return f"{x['mean_pct']:+.2f}% (n={x['n']})" if x else 'N/D'
            diff = d['mean_difference_high_minus_low_pp']
            lines.append(f"| {h} | {label} | {fmt(d['0_or_1_adverse_signal'])} | "
                         f"{fmt(d['2_or_3_adverse_signals'])} | "
                         f"{diff:+.2f} pp |" if diff is not None else
                         f"| {h} | {label} | {fmt(d['0_or_1_adverse_signal'])} | "
                         f"{fmt(d['2_or_3_adverse_signals'])} | N/D |")
    lines += ['', '## Limitaciones', ''] + ['- ' + x for x in result['limitations']]
    (OUT / 'backtest_6plus1.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Backtest historico generado en output/backtest_6plus1.json y .md')
    for h, variants in result['horizons'].items():
        print(h, 'sesiones, diferencia no solapada:',
              variants['non_overlapping']['mean_difference_high_minus_low_pp'], 'pp')


if __name__ == '__main__':
    main()
