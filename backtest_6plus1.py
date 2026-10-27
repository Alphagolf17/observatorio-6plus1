"""Backtest exploratorio 6+1: no usa datos futuros para construir señales.
Ejecutar después de collector.py: python backtest_6plus1.py
Solo biblioteca estándar. Horizonte de 5/10/20 sesiones; precios sin dividendos.
"""
import csv
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path('output')
SYMBOLS = ('SPY', 'QQQ', 'SMH', 'ASML', 'AVGO')
HORIZONS = (5, 10, 20)
MIN_SAMPLE = 20


def read_market(symbol):
    path = ROOT / f'market_{symbol}.csv'
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = []
        for r in csv.DictReader(f):
            try:
                price = float(r['close'])
                if price > 0:
                    rows.append((r['date'], price))
            except (ValueError, TypeError, KeyError):
                pass
    return sorted(dict(rows).items())


def stats(values):
    if not values:
        return None
    return {'n': len(values), 'mean_pct': round(mean(values), 3),
            'median_pct': round(median(values), 3),
            'positive_pct': round(100 * sum(v > 0 for v in values) / len(values), 1)}


def main():
    series = {s: read_market(s) for s in SYMBOLS}
    if not series['SPY']:
        raise SystemExit('No existe output/market_SPY.csv. Ejecuta collector.py.')
    spy = dict(series['SPY'])
    spy_dates = [d for d, _ in series['SPY']]
    spy_prices = [v for _, v in series['SPY']]
    # Señal construida SOLO con datos del día y los 20 cierres anteriores.
    # Comparación QQQ/SMH vs SPY requiere mismo día inicial y final.
    aligned = {}
    for s in SYMBOLS:
        by_date = dict(series[s])
        aligned[s] = [by_date.get(d) for d in spy_dates]
    signals = []
    for i in range(20, len(spy_dates)):
        day = spy_dates[i]
        if any(aligned[s][i] is None or aligned[s][i-20] is None for s in ('SPY','QQQ','SMH')):
            continue
        spy20 = (aligned['SPY'][i] / aligned['SPY'][i-20] - 1) * 100
        qqq20 = (aligned['QQQ'][i] / aligned['QQQ'][i-20] - 1) * 100
        smh20 = (aligned['SMH'][i] / aligned['SMH'][i-20] - 1) * 100
        window = aligned['SPY'][i-19:i+1]
        if any(x is None for x in window):
            continue
        adverse = (smh20 - spy20 < -5) + (qqq20 - spy20 < -2) + (aligned['SPY'][i] < mean(window))
        signals.append((i, day, int(adverse)))
    result = {'method': 'Estudio exploratorio de 3 señales técnicas, no del semáforo macro completo.',
              'start_date': spy_dates[0], 'end_date': spy_dates[-1],
              'spy_sessions': len(spy_dates), 'evaluated_signal_days': len(signals),
              'rules': ['SMH - SPY a 20 sesiones < -5 pp', 'QQQ - SPY a 20 sesiones < -2 pp', 'SPY bajo su media de 20 sesiones'],
              'horizons': {},
              'limitations': ['Observaciones diarias solapadas: NO independientes.',
                              'Datos compactos de ~100 sesiones: muestra insuficiente para validar ventaja.',
                              'Cierres de precio sin ajuste garantizado por dividendos/splits.',
                              'No incluye comisiones, spread ni impuestos.',
                              'Las reglas son exploratorias y fueron elegidas tras ver datos recientes; riesgo de sobreajuste.',
                              'No incluye las señales macro del semáforo, que requieren alineación por fecha de publicación.',
                              'Los resultados históricos no demuestran capacidad predictiva.']}
    for h in HORIZONS:
        all_r, low, high = [], [], []
        for i, _, score in signals:
            if i + h >= len(spy_prices):
                continue
            ret = (spy_prices[i+h] / spy_prices[i] - 1) * 100
            all_r.append(ret)
            (high if score >= 2 else low).append(ret)
        result['horizons'][str(h)] = {
            'all_days': stats(all_r), '0_or_1_adverse_signal': stats(low),
            '2_or_3_adverse_signals': stats(high),
            'mean_difference_high_minus_low_pp': round(mean(high)-mean(low), 3) if high and low else None,
            'enough_samples_in_both_groups': len(low) >= MIN_SAMPLE and len(high) >= MIN_SAMPLE}
    ROOT.mkdir(exist_ok=True)
    (ROOT / 'backtest_6plus1.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Validación exploratoria 6+1', '', f"Periodo: {result['start_date']} a {result['end_date']}",
             f"Sesiones SPY: {result['spy_sessions']}; días evaluados: {result['evaluated_signal_days']}", '',
             'Señales adversas: SMH débil vs SPY, QQQ débil vs SPY, SPY bajo MA20.', '',
             '| Horizonte | Días 0–1 señales | Días 2–3 señales | Diferencia media | Muestra suficiente |',
             '|---|---|---|---|---|']
    for h, d in result['horizons'].items():
        def fmt(x):
            return f"{x['mean_pct']:+.2f}% (n={x['n']})" if x else 'sin datos'
        diff = d['mean_difference_high_minus_low_pp']
        lines.append(f"| {h} sesiones | {fmt(d['0_or_1_adverse_signal'])} | {fmt(d['2_or_3_adverse_signals'])} | {diff:+.2f} pp" + ('' if diff is not None else '') + f" | {'Sí' if d['enough_samples_in_both_groups'] else 'No'} |" if diff is not None else f"| {h} sesiones | {fmt(d['0_or_1_adverse_signal'])} | {fmt(d['2_or_3_adverse_signals'])} | N/D | No |")
    lines += ['', '## Limitaciones', ''] + ['- '+x for x in result['limitations']]
    (ROOT / 'backtest_6plus1.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('Generados output/backtest_6plus1.json y output/backtest_6plus1.md')
    for h, d in result['horizons'].items():
        print(h, 'sesiones:', d['mean_difference_high_minus_low_pp'], 'pp; muestra suficiente:', d['enough_samples_in_both_groups'])

if __name__ == '__main__':
    main()
