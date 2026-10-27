"""Validacion retrospectiva 6+1: reglas fijas y ejecucion a la apertura siguiente.
No modifica el radar ni el backtest existente. Solo biblioteca estandar.
"""
import csv
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path('historico_inicial')
OUT = Path('output')
SYMBOLS = ('SPY', 'QQQ', 'SMH')
HORIZONS = (5, 10, 20)
CUTOFF = '2023-01-01'


def load(symbol):
    path = ROOT / f'market_{symbol}_adjusted.csv'
    if not path.exists():
        raise SystemExit(f'Falta {path}')
    data = {}
    with path.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            try:
                if row.get('price_basis') != 'dividend_and_split_adjusted':
                    raise SystemExit(f'Base de precios inesperada: {path}')
                op, cl = float(row['open']), float(row['close'])
                if op > 0 and cl > 0:
                    data[row['date']] = (op, cl)
            except (ValueError, TypeError, KeyError):
                continue
    return data


def summary(values):
    if not values:
        return {'n': 0, 'mean_pct': None, 'median_pct': None, 'positive_pct': None}
    return {'n': len(values), 'mean_pct': round(mean(values), 3),
            'median_pct': round(median(values), 3),
            'positive_pct': round(100 * sum(x > 0 for x in values) / len(values), 1)}


def main():
    raw = {s: load(s) for s in SYMBOLS}
    dates = sorted(set.intersection(*(set(x) for x in raw.values())))
    if len(dates) < 500:
        raise SystemExit('Historico insuficiente o fechas no alineadas')
    prices = {s: [raw[s][d] for d in dates] for s in SYMBOLS}
    result = {'method': 'Validacion retrospectiva con reglas fijas, entrada siguiente apertura',
              'start_date': dates[0], 'end_date': dates[-1], 'aligned_sessions': len(dates),
              'cutoff': CUTOFF, 'horizons': {},
              'rules': ['SMH-SPY 20 sesiones < -5 pp', 'QQQ-SPY 20 sesiones < -2 pp', 'SPY bajo MA20'],
              'execution': 'Senal al cierre t; compra apertura t+1; salida apertura t+h+1',
              'limitations': [
                  'Precios OHLC ajustados historicamente: aproximacion de rentabilidad total, no precios ejecutables reales.',
                  'No se incluyen comisiones, deslizamiento, impuestos ni costes de financiacion.',
                  'Los umbrales se definieron tras observar parte de los datos: 2023+ NO es una prueba genuinamente virgen.',
                  'Los intervalos sin solapamiento se seleccionan cronologicamente por grupo; las muestras no son ensayos independientes aleatorios.',
                  'El resultado compara retornos condicionales de SPY, NO una estrategia operativa ni rentabilidad incremental garantizada.',
                  'No incluye indicadores macro ni fechas de publicacion de los mismos.',
                  'El ultimo dia podria ser una sesion abierta: se excluye como fecha de senal y de salida.'
              ]}
    # Excluir ultima observacion por posible cierre provisional; entrada/salida nunca la usan.
    last_final = len(dates) - 2
    signals = []
    for i in range(20, last_final):
        closes = {s: [x[1] for x in prices[s]] for s in SYMBOLS}
        spy20 = (closes['SPY'][i] / closes['SPY'][i-20] - 1) * 100
        qqq20 = (closes['QQQ'][i] / closes['QQQ'][i-20] - 1) * 100
        smh20 = (closes['SMH'][i] / closes['SMH'][i-20] - 1) * 100
        adverse = int(smh20-spy20 < -5) + int(qqq20-spy20 < -2) + int(closes['SPY'][i] < mean(closes['SPY'][i-19:i+1]))
        signals.append((i, dates[i], adverse))
    for h in HORIZONS:
        periods = {}
        for period, is_in in [('referencia_2016_2022', lambda d: d < CUTOFF),
                              ('comprobacion_2023_2026', lambda d: d >= CUTOFF)]:
            candidates = {'0_1': [], '2_3': []}
            for i, date, score in signals:
                if not is_in(date) or i + h + 1 > last_final:
                    continue
                # Impedir operaciones que crucen el corte entre referencia y comprobacion.
                if not is_in(dates[i+h+1]):
                    continue
                entry = prices['SPY'][i+1][0]
                exit_ = prices['SPY'][i+h+1][0]
                ret = (exit_ / entry - 1) * 100
                candidates['2_3' if score >= 2 else '0_1'].append((i, ret))
            stats = {}
            for key, vals in candidates.items():
                selected, last_exit = [], -1
                for i, ret in vals:
                    if i+1 > last_exit:
                        selected.append(ret)
                        last_exit = i+h+1
                stats[key] = summary(selected)
            a, b = stats['0_1'], stats['2_3']
            periods[period] = {'0_or_1_adverse': a, '2_or_3_adverse': b,
                               'difference_pp': round(b['mean_pct']-a['mean_pct'], 3) if a['n'] and b['n'] else None,
                               'both_groups_n_at_least_20': a['n'] >= 20 and b['n'] >= 20}
        result['horizons'][str(h)] = periods
    OUT.mkdir(exist_ok=True)
    (OUT/'validacion_6plus1.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Validacion retrospectiva 6+1', '', f"Periodo: {dates[0]} a {dates[-1]}",
             'Senal al cierre, entrada apertura siguiente, salida apertura posterior.',
             'Ultima sesion excluida por precaucion.', '',
             '| Horizonte | Periodo | 0-1 adversas | 2-3 adversas | Diferencia | n>=20 ambos |',
             '|---|---|---:|---:|---:|---|']
    for h, periods in result['horizons'].items():
        for period, d in periods.items():
            def fmt(x):
                return f"{x['mean_pct']:+.2f}% (n={x['n']})" if x['n'] else 'N/D'
            diff = f"{d['difference_pp']:+.2f} pp" if d['difference_pp'] is not None else 'N/D'
            lines.append(f"| {h} | {period} | {fmt(d['0_or_1_adverse'])} | {fmt(d['2_or_3_adverse'])} | {diff} | {'Si' if d['both_groups_n_at_least_20'] else 'No'} |")
    lines += ['', '## Limitaciones', ''] + ['- '+x for x in result['limitations']]
    (OUT/'validacion_6plus1.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('\n'.join(lines[:15]))
    print('Generados output/validacion_6plus1.json y output/validacion_6plus1.md')

if __name__ == '__main__':
    main()
