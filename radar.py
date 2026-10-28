"""Radar 6+1: fechas sincronizadas, cobertura explícita y señales descriptivas."""
import csv
import json
from bisect import bisect_right
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path('output')
SYMBOLS = ('SPY', 'QQQ', 'SMH', 'ASML', 'AVGO')
SERIES = ('WALCL', 'WTREGEN', 'RRPONTSYD', 'VIXCLS', 'BAMLH0A0HYM2', 'DGS10', 'DFII10', 'DTWEXBGS')
EXPECTED_SIGNALS = 6


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return sorted(csv.DictReader(f), key=lambda x: x['date'])


def pct(a, b):
    return round((a / b - 1) * 100, 2) if b else None


def age_days(iso):
    return (datetime.now(timezone.utc).date() - date.fromisoformat(iso)).days


def main():
    ROOT.mkdir(exist_ok=True)
    markets, macro, warnings, histories = {}, {}, [], {}
    for symbol in SYMBOLS:
        path = ROOT / f'market_{symbol}.csv'
        if not path.exists():
            warnings.append(f'Falta {path}')
            continue
        try:
            rows = read_rows(path)
            valid = {}
            for r in rows:
                try:
                    close = float(r['close'])
                    volume = float(r['volume'])
                    date.fromisoformat(r['date'])
                    if close > 0 and volume >= 0:
                        valid[r['date']] = (close, volume)
                except (ValueError, TypeError, KeyError):
                    continue
            dates = sorted(valid)
            if len(dates) < 21:
                warnings.append(f'Histórico insuficiente: {symbol}')
                continue
            closes = [valid[d][0] for d in dates]
            volumes = [valid[d][1] for d in dates]
            ma20 = sum(closes[-20:]) / 20
            avg_volume = sum(volumes[-20:]) / 20
            histories[symbol] = valid
            markets[symbol] = {
                'date': dates[-1], 'close': closes[-1],
                'return_5_sessions_pct': pct(closes[-1], closes[-6]),
                'return_20_sessions_pct': pct(closes[-1], closes[-21]),
                'above_ma20': closes[-1] > ma20,
                'last_volume_vs_20_session_average': round(volumes[-1] / avg_volume, 2) if avg_volume else None,
                'age_days': age_days(dates[-1])}
            if markets[symbol]['age_days'] > 5:
                warnings.append(f'{symbol}: cierre desactualizado ({dates[-1]})')
        except (OSError, ValueError, KeyError) as exc:
            warnings.append(f'{symbol}: CSV inválido: {exc}')

    macro_history = {}
    for series in SERIES:
        path = ROOT / f'fred_{series}.csv'
        if not path.exists():
            warnings.append(f'Falta {path}')
            continue
        try:
            valid = {}
            for r in read_rows(path):
                try:
                    date.fromisoformat(r['date'])
                    valid[r['date']] = float(r['value'])
                except (ValueError, TypeError, KeyError):
                    continue
            rows = sorted(valid.items())
            if rows:
                macro_history[series] = rows
                macro[series] = {'date': rows[-1][0], 'value': rows[-1][1],
                                 'previous_value': rows[-2][1] if len(rows) > 1 else None,
                                 'age_days': age_days(rows[-1][0])}
                if macro[series]['age_days'] > (14 if series in ('WALCL', 'WTREGEN') else 7):
                    warnings.append(f'{series}: dato potencialmente antiguo ({rows[-1][0]})')
        except (OSError, ValueError, KeyError) as exc:
            warnings.append(f'{series}: CSV inválido: {exc}')

    relative = {}
    common_dates = []
    if all(s in histories for s in ('SPY', 'QQQ', 'SMH')):
        common_dates = sorted(set(histories['SPY']) & set(histories['QQQ']) & set(histories['SMH']))
        if len(common_dates) >= 21 and age_days(common_dates[-1]) <= 5:
            for symbol in ('QQQ', 'SMH'):
                ref = histories['SPY']
                other = histories[symbol]
                relative[symbol] = round(pct(other[common_dates[-1]][0], other[common_dates[-21]][0])
                                         - pct(ref[common_dates[-1]][0], ref[common_dates[-21]][0]), 2)
        else:
            warnings.append('Fechas comunes SPY/QQQ/SMH insuficientes o antiguas')
    else:
        warnings.append('Faltan mercados para señales relativas sincronizadas')
    # ASML/AVGO se muestran solo cuando comparten fechas de inicio y fin con SPY.
    for symbol in ('ASML', 'AVGO'):
        if symbol in histories and 'SPY' in histories:
            common = sorted(set(histories[symbol]) & set(histories['SPY']))
            if len(common) >= 21 and age_days(common[-1]) <= 5:
                relative[symbol] = round(pct(histories[symbol][common[-1]][0], histories[symbol][common[-21]][0])
                                         - pct(histories['SPY'][common[-1]][0], histories['SPY'][common[-21]][0]), 2)

    signals, risk_flags = [], []
    def add(label, condition, detail):
        signals.append({'signal': label, 'risk': bool(condition), 'detail': detail})
        if condition:
            risk_flags.append(detail)

    if 'SMH' in relative:
        add('semiconductor_relative_weakness', relative['SMH'] < -5,
            'Semiconductores: fuerte debilidad relativa a 20 sesiones')
    if 'QQQ' in relative:
        add('nasdaq_relative_weakness', relative['QQQ'] < -2,
            'Nasdaq: debilidad relativa frente al S&P 500')
    if common_dates and len(common_dates) >= 20 and age_days(common_dates[-1]) <= 5:
        spy_close = [histories['SPY'][d][0] for d in common_dates[-20:]]
        add('spy_below_ma20', spy_close[-1] < sum(spy_close) / 20,
            'SPY por debajo de su media de 20 sesiones')

    def macro_point(name, max_age=7):
        x = macro.get(name)
        return x['value'] if x and 0 <= x['age_days'] <= max_age else None

    vix = macro_point('VIXCLS')
    if vix is not None:
        add('vix_elevated', vix > 25, 'VIX superior a 25: volatilidad elevada')
    spread = macro_point('BAMLH0A0HYM2')
    if spread is not None:
        add('high_yield_stress', spread > 5, 'Spread high yield superior a 5 puntos: estrés crediticio')

    liquidity = {'available': False,
                 'limitations': 'Proxy orientativo por fecha de observación, NO por fecha real de publicación. No apto para backtest sin calendario de disponibilidad.'}
    if all(s in macro_history for s in ('WALCL', 'WTREGEN', 'RRPONTSYD')):
        walcl = dict(macro_history['WALCL'])
        tga = dict(macro_history['WTREGEN'])
        rrp = dict(macro_history['RRPONTSYD'])
        rrp_dates = sorted(rrp)
        points = []
        for d in sorted(set(walcl) & set(tga)):
            pos = bisect_right(rrp_dates, d) - 1
            if pos < 0:
                continue
            rd = rrp_dates[pos]
            if (date.fromisoformat(d) - date.fromisoformat(rd)).days > 7:
                continue
            points.append((d, round((walcl[d] - tga[d]) / 1000 - rrp[rd], 3)))
        if len(points) >= 5 and 0 <= age_days(points[-1][0]) <= 14:
            change = round(points[-1][1] - points[-5][1], 3)
            liquidity = {'available': True, 'date': points[-1][0],
                         'proxy_usd_billions': points[-1][1],
                         'change_4_weekly_observations_usd_billions': change,
                         'direction': 'contraccion' if change < -50 else ('expansion' if change > 50 else 'estable'),
                         'limitations': 'WALCL - TGA - ON RRP. Alineación por observación, no publicación; solo uso descriptivo actual.'}
            add('liquidity_contraction', change < -50,
                'Proxy de liquidez Fed: contracción superior a 50.000 millones USD en cuatro observaciones semanales')
        else:
            warnings.append('Proxy de liquidez no disponible o demasiado antiguo')
    else:
        warnings.append('Faltan series para calcular el proxy de liquidez')

    count = len(signals)
    active = sum(s['risk'] for s in signals)
    score = round(100 * active / count) if count else None
    coverage = round(100 * count / EXPECTED_SIGNALS) if EXPECTED_SIGNALS else 0
    color = ('sin_datos' if count < EXPECTED_SIGNALS else
             'rojo' if score >= 60 else 'amarillo' if score >= 30 else 'verde')
    if count < EXPECTED_SIGNALS:
        warnings.append(f'Cobertura incompleta: {count}/{EXPECTED_SIGNALS} señales; semáforo bloqueado')
    report = {'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'market_data': markets, 'macro_latest': macro,
              'relative_return_20_sessions_vs_spy_percentage_points': relative,
              'technical_common_last_date': common_dates[-1] if common_dates else None,
              'liquidity_proxy': liquidity,
              'risk_assessment': {'traffic_light': color, 'risk_score_0_100': score,
                                  'active_signals': active, 'available_signals': count,
                                  'expected_signals': EXPECTED_SIGNALS, 'coverage_pct': coverage,
                                  'interpretation': 'Índice heurístico, NO probabilidad de caída. Sin datos si cobertura incompleta.'},
              'signals': signals, 'risk_flags': risk_flags, 'warnings': warnings,
              'limitations': 'Cierres y macro con retrasos; proxy de liquidez sin calendario de publicación. No son recomendaciones automáticas.'}
    (ROOT / 'radar_6plus1.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Radar financiero 6+1', '', f'## Semáforo: {color.upper()}',
             f'Señales adversas: {active}/{count}; cobertura: {count}/{EXPECTED_SIGNALS} ({coverage}%). '
             f'Índice heurístico: {score}/100. No es una probabilidad.',
             '', '## Fortaleza relativa (20 sesiones frente a SPY)', '']
    lines += [f'- {s}: {v:+.2f} puntos porcentuales' for s, v in relative.items()]
    lines += ['', '## Alertas', ''] + [f'- {x}' for x in risk_flags or ['Sin alertas por los umbrales configurados']]
    lines += ['', '## Liquidez aproximada', '']
    lines += ([f"- {liquidity['date']}: {liquidity['proxy_usd_billions']} miles de millones USD",
               f"- Variación de 4 observaciones: {liquidity['change_4_weekly_observations_usd_billions']:+.3f} miles de millones USD",
               f"- Tendencia: {liquidity['direction']}"] if liquidity['available'] else ['- No disponible'])
    lines += ['', '## Indicadores macro (último dato disponible)', '']
    lines += [f"- {s}: {x['value']} ({x['date']})" for s, x in macro.items()]
    lines += ['', '## Limitaciones', '', report['limitations'], liquidity['limitations']]
    if warnings:
        lines += ['', '## Advertencias', ''] + [f'- {x}' for x in warnings]
    (ROOT / 'radar_6plus1.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Radar generado. Semáforo: {color}; señales adversas: {active}/{count}; cobertura {coverage}%')
    for flag in risk_flags:
        print('ALERTA:', flag)


if __name__ == '__main__':
    main()
