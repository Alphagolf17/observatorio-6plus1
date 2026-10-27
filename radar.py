"""Observatorio 6+1: radar de riesgo, solo biblioteca estándar.
Señales descriptivas, no órdenes de inversión ni probabilidades.
"""
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path('output')
SYMBOLS = ('SPY', 'QQQ', 'SMH', 'ASML', 'AVGO')
SERIES = ('WALCL', 'WTREGEN', 'RRPONTSYD', 'VIXCLS', 'BAMLH0A0HYM2', 'DGS10', 'DFII10', 'DTWEXBGS')


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return sorted(csv.DictReader(f), key=lambda x: x['date'])


def pct(a, b):
    return round((a / b - 1) * 100, 2) if b else None


def delta(a, b):
    return round(a - b, 3)


def age_days(iso):
    return (datetime.now(timezone.utc).date() - date.fromisoformat(iso)).days


def macro_point(macro, name, max_age=10):
    x = macro.get(name)
    return x['value'] if x and x['age_days'] <= max_age else None


def main():
    if not ROOT.exists():
        raise SystemExit('Falta output/. Ejecuta primero collector.py.')
    markets, macro, warnings = {}, {}, []
    for symbol in SYMBOLS:
        path = ROOT / f'market_{symbol}.csv'
        if not path.exists():
            warnings.append(f'Falta {path}')
            continue
        try:
            rows = [r for r in read_rows(path) if r.get('close') not in ('', None)]
            if len(rows) < 21:
                warnings.append(f'Histórico insuficiente: {symbol}')
                continue
            close = [float(r['close']) for r in rows]
            volume = [float(r['volume']) if r.get('volume') else 0 for r in rows]
            ma20 = sum(close[-20:]) / 20
            avg_volume = sum(volume[-20:]) / 20
            markets[symbol] = {
                'date': rows[-1]['date'], 'close': close[-1],
                'return_5_sessions_pct': pct(close[-1], close[-6]),
                'return_20_sessions_pct': pct(close[-1], close[-21]),
                'above_ma20': close[-1] > ma20,
                'last_volume_vs_20_session_average': round(volume[-1] / avg_volume, 2) if avg_volume else None,
                'age_days': age_days(rows[-1]['date']),
            }
            if markets[symbol]['age_days'] > 5:
                warnings.append(f'{symbol}: cierre desactualizado ({rows[-1]["date"]})')
        except (ValueError, KeyError, IndexError) as exc:
            warnings.append(f'{symbol}: CSV inválido: {exc}')

    history = {}
    for series in SERIES:
        path = ROOT / f'fred_{series}.csv'
        if not path.exists():
            warnings.append(f'Falta {path}')
            continue
        rows = []
        for row in read_rows(path):
            try:
                rows.append((row['date'], float(row['value'])))
            except (ValueError, TypeError, KeyError):
                continue
        if rows:
            history[series] = rows
            macro[series] = {
                'date': rows[-1][0], 'value': rows[-1][1],
                'previous_value': rows[-2][1] if len(rows) > 1 else None,
                'age_days': age_days(rows[-1][0]),
            }
            if macro[series]['age_days'] > (14 if series in ('WALCL', 'WTREGEN') else 7):
                warnings.append(f'{series}: dato potencialmente antiguo ({rows[-1][0]})')

    relative = {}
    if 'SPY' in markets:
        for symbol in ('QQQ', 'SMH', 'ASML', 'AVGO'):
            if symbol in markets:
                relative[symbol] = round(markets[symbol]['return_20_sessions_pct'] - markets['SPY']['return_20_sessions_pct'], 2)

    risk_flags = []
    signals = []
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
    if 'SPY' in markets and markets['SPY']['age_days'] <= 5:
        add('spy_below_ma20', not markets['SPY']['above_ma20'], 'SPY por debajo de su media de 20 sesiones')

    vix = macro_point(macro, 'VIXCLS', 7)
    if vix is not None:
        add('vix_elevated', vix > 25, 'VIX superior a 25: volatilidad elevada')
    spread = macro_point(macro, 'BAMLH0A0HYM2', 7)
    if spread is not None:
        add('high_yield_stress', spread > 5, 'Spread high yield superior a 5 puntos: estrés crediticio')

    # WALCL y WTREGEN se publican en millones USD; RRPONTSYD en miles de millones USD.
    # Alinear cada observación al último dato publicado en esa fecha, sin usar datos futuros.
    liquidity = {'available': False, 'limitations': 'Proxy orientativo; no mide toda la liquidez financiera.'}
    if all(s in history for s in ('WALCL', 'WTREGEN', 'RRPONTSYD')):
        walcl, tga, rrp = (history[s] for s in ('WALCL', 'WTREGEN', 'RRPONTSYD'))
        dates = sorted(set(d for d, _ in walcl) & set(d for d, _ in tga))
        rrp_by_date = dict(rrp)
        rrp_dates = sorted(rrp_by_date)
        points = []
        for d in dates:
            eligible = [r for r in rrp_dates if r <= d]
            if not eligible:
                continue
            rd = eligible[-1]
            if (date.fromisoformat(d) - date.fromisoformat(rd)).days > 7:
                continue
            w = dict(walcl)[d]
            t = dict(tga)[d]
            # Resultado en miles de millones USD.
            points.append((d, round((w - t) / 1000 - rrp_by_date[rd], 3)))
        if len(points) >= 5 and age_days(points[-1][0]) <= 14:
            change = round(points[-1][1] - points[-5][1], 3)
            liquidity = {
                'available': True, 'date': points[-1][0],
                'proxy_usd_billions': points[-1][1],
                'change_4_weekly_observations_usd_billions': change,
                'direction': 'contraccion' if change < -50 else ('expansion' if change > 50 else 'estable'),
                'limitations': 'Proxy WALCL - TGA - ON RRP. Alineado por fecha, no representa flujos bursátiles ni liquidez total.'
            }
            add('liquidity_contraction', change < -50,
                'Proxy de liquidez Fed: contracción superior a 50.000 millones USD en cuatro observaciones semanales')
        else:
            warnings.append('Proxy de liquidez no disponible o demasiado antiguo')
    else:
        warnings.append('Faltan series para calcular el proxy de liquidez')

    # Cada señal disponible pesa igual; no es una probabilidad.
    count = len(signals)
    active = sum(s['risk'] for s in signals)
    score = round(100 * active / count) if count else None
    color = ('sin_datos' if count < 3 else
             'rojo' if score >= 60 else 'amarillo' if score >= 30 else 'verde')
    report = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'market_data': markets, 'macro_latest': macro,
        'relative_return_20_sessions_vs_spy_percentage_points': relative,
        'liquidity_proxy': liquidity,
        'risk_assessment': {'traffic_light': color, 'risk_score_0_100': score,
                            'active_signals': active, 'available_signals': count,
                            'interpretation': 'Índice heurístico de señales adversas; NO es probabilidad de caída.'},
        'signals': signals, 'risk_flags': risk_flags, 'warnings': warnings,
        'limitations': 'Datos de cierre y macro con retrasos. No miden flujos netos ni son recomendaciones automáticas.'
    }
    (ROOT / 'radar_6plus1.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Radar financiero 6+1', '', f'## Semáforo: {color.upper()}',
             f'Señales adversas: {active}/{count}. Índice heurístico: {score}/100. No es una probabilidad.',
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
    print(f'Radar generado. Semáforo: {color}; señales adversas: {active}/{count}')
    for flag in risk_flags:
        print('ALERTA:', flag)


if __name__ == '__main__':
    main()
