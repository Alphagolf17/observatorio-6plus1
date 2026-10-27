"""Observatorio 6+1: radar gratuito basado en los CSV del coleccionista.
Solo usa la biblioteca estándar de Python; no necesita claves adicionales.
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('output')
SYMBOLS = ('SPY', 'QQQ', 'SMH', 'ASML', 'AVGO')
SERIES = ('WALCL', 'WTREGEN', 'RRPONTSYD', 'VIXCLS', 'BAMLH0A0HYM2', 'DGS10', 'DFII10', 'DTWEXBGS')


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return sorted(list(csv.DictReader(f)), key=lambda x: x['date'])


def pct(a, b):
    return round((a / b - 1) * 100, 2) if b else None


def main():
    if not ROOT.exists():
        raise SystemExit('Falta output/. Ejecuta primero collector.py.')
    markets, macro, warnings = {}, {}, []
    for symbol in SYMBOLS:
        path = ROOT / f'market_{symbol}.csv'
        if not path.exists():
            warnings.append(f'Falta {path}')
            continue
        rows = read_rows(path)
        if len(rows) < 21:
            warnings.append(f'Histórico insuficiente: {symbol}')
            continue
        close = [float(r['close']) for r in rows]
        volume = [float(r['volume']) for r in rows]
        ma20 = sum(close[-20:]) / 20
        avg_volume = sum(volume[-20:]) / 20
        markets[symbol] = {
            'date': rows[-1]['date'],
            'close': close[-1],
            'return_5_sessions_pct': pct(close[-1], close[-6]),
            'return_20_sessions_pct': pct(close[-1], close[-21]),
            'above_ma20': close[-1] > ma20,
            'last_volume_vs_20_session_average': round(volume[-1] / avg_volume, 2) if avg_volume else None,
        }
    for series in SERIES:
        path = ROOT / f'fred_{series}.csv'
        if not path.exists():
            warnings.append(f'Falta {path}')
            continue
        rows = []
        for row in read_rows(path):
            try:
                rows.append((row['date'], float(row['value'])))
            except (ValueError, TypeError):
                continue
        if rows:
            macro[series] = {'date': rows[-1][0], 'value': rows[-1][1],
                             'previous_value': rows[-2][1] if len(rows) > 1 else None}
    relative = {}
    if 'SPY' in markets:
        for symbol in ('QQQ', 'SMH', 'ASML', 'AVGO'):
            if symbol in markets:
                relative[symbol] = round(markets[symbol]['return_20_sessions_pct'] - markets['SPY']['return_20_sessions_pct'], 2)
    risk_flags = []
    if 'SMH' in relative and relative['SMH'] < -5:
        risk_flags.append('Semiconductores: fuerte debilidad relativa a 20 sesiones')
    if 'QQQ' in relative and relative['QQQ'] < -2:
        risk_flags.append('Nasdaq: debilidad relativa frente al S&P 500')
    if 'VIXCLS' in macro and macro['VIXCLS']['value'] > 25:
        risk_flags.append('VIX superior a 25: volatilidad elevada')
    if 'BAMLH0A0HYM2' in macro and macro['BAMLH0A0HYM2']['value'] > 5:
        risk_flags.append('Spread high yield superior a 5 puntos: estrés crediticio')
    report = {'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'market_data': markets, 'macro_latest': macro,
              'relative_return_20_sessions_vs_spy_percentage_points': relative,
              'risk_flags': risk_flags, 'warnings': warnings,
              'limitations': 'Datos de cierre y macro con retrasos. No miden flujos netos ni son recomendaciones automáticas.'}
    (ROOT / 'radar_6plus1.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Radar financiero 6+1', '', '## Fortaleza relativa (20 sesiones frente a SPY)', '']
    lines += [f'- {s}: {v:+.2f} puntos porcentuales' for s, v in relative.items()]
    lines += ['', '## Alertas', ''] + [f'- {x}' for x in risk_flags or ['Sin alertas por los umbrales configurados']]
    lines += ['', '## Indicadores macro (último dato disponible)', '']
    lines += [f"- {s}: {x['value']} ({x['date']})" for s, x in macro.items()]
    lines += ['', '## Limitaciones', '', report['limitations']]
    if warnings:
        lines += ['', '## Advertencias', ''] + [f'- {x}' for x in warnings]
    (ROOT / 'radar_6plus1.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Radar generado: output/radar_6plus1.json y output/radar_6plus1.md')
    for flag in risk_flags:
        print('ALERTA:', flag)


if __name__ == '__main__':
    main()
