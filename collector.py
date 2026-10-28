"""Recopilación diaria 6+1. Fallo explícito ante series obligatorias incompletas."""
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('output')
OUT.mkdir(exist_ok=True)
STAMP = datetime.now(timezone.utc).isoformat()
SYMBOLS = ('SPY', 'QQQ', 'SMH', 'ASML', 'AVGO')
SERIES = ('WALCL', 'WTREGEN', 'RRPONTSYD', 'DGS10', 'DFII10', 'BAMLH0A0HYM2', 'VIXCLS', 'DTWEXBGS')
ERRORS = []
SUMMARY = {'collected_at_utc': STAMP, 'markets': {}, 'macro': {}, 'warnings': ERRORS,
           'complete': False, 'disclaimer': 'Datos con retrasos y frecuencias distintas. No representan flujos netos de capital.'}


def fetch(url, params):
    req = urllib.request.Request(url + '?' + urllib.parse.urlencode(params),
                                 headers={'User-Agent': 'observatorio-6plus1/1.1'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def save_csv(filename, rows, fields):
    target = OUT / filename
    temp = target.with_suffix(target.suffix + '.tmp')
    try:
        with temp.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def market(symbol, key):
    data = fetch('https://www.alphavantage.co/query', {
        'function': 'TIME_SERIES_DAILY', 'symbol': symbol, 'outputsize': 'compact', 'apikey': key})
    series = data.get('Time Series (Daily)')
    if not isinstance(series, dict) or not series:
        msg = data.get('Note') or data.get('Information') or data.get('Error Message')
        raise ValueError(f'Serie diaria no disponible: {str(msg or "respuesta sin serie")[:180]}')
    rows = []
    for day, val in sorted(series.items()):
        datetime.strptime(day, '%Y-%m-%d')
        op, hi, lo, cl = (float(val[k]) for k in ('1. open', '2. high', '3. low', '4. close'))
        vol = int(val['5. volume'])
        if not (0 < lo <= min(op, cl) <= max(op, cl) <= hi and vol >= 0):
            raise ValueError(f'OHLCV inválido para {symbol} en {day}')
        rows.append({'date': day, 'open': val['1. open'], 'high': val['2. high'],
                     'low': val['3. low'], 'close': val['4. close'], 'volume': val['5. volume'],
                     'symbol': symbol, 'source': 'Alpha Vantage', 'retrieved_at_utc': STAMP})
    if len(rows) < 21:
        raise ValueError(f'Solo {len(rows)} sesiones para {symbol}')
    save_csv(f'market_{symbol}.csv', rows, list(rows[0]))
    SUMMARY['markets'][symbol] = {'last_date': rows[-1]['date'], 'last_close': float(rows[-1]['close']),
                                  'last_volume': int(rows[-1]['volume']), 'observations': len(rows)}


def fred(series_id, key):
    data = fetch('https://api.stlouisfed.org/fred/series/observations', {
        'series_id': series_id, 'api_key': key, 'file_type': 'json', 'observation_start': '2016-01-01'})
    if 'observations' not in data:
        raise ValueError(f'FRED sin observaciones: {str(data.get("error_message", "respuesta inválida"))[:180]}')
    rows = []
    for v in data['observations']:
        if v.get('value') in ('.', None, ''):
            continue
        datetime.strptime(v['date'], '%Y-%m-%d')
        float(v['value'])
        rows.append({'date': v['date'], 'value': v['value'], 'series': series_id,
                     'source': 'FRED', 'retrieved_at_utc': STAMP})
    rows.sort(key=lambda r: r['date'])
    if not rows:
        raise ValueError('Serie FRED sin observaciones válidas')
    save_csv(f'fred_{series_id}.csv', rows, list(rows[0]))
    SUMMARY['macro'][series_id] = {'last_date': rows[-1]['date'],
                                   'last_value': float(rows[-1]['value']), 'observations': len(rows)}


def main():
    av, fk = os.environ.get('ALPHAVANTAGE_API_KEY'), os.environ.get('FRED_API_KEY')
    if not av or not fk:
        print('Faltan secretos ALPHAVANTAGE_API_KEY o FRED_API_KEY', file=sys.stderr)
        return 1
    # Evitar reutilizar como actuales los CSV de una ejecución anterior que falle.
    for symbol in SYMBOLS:
        (OUT / f'market_{symbol}.csv').unlink(missing_ok=True)
    for series in SERIES:
        (OUT / f'fred_{series}.csv').unlink(missing_ok=True)
    for symbol in SYMBOLS:
        try:
            market(symbol, av)
            print('OK mercado:', symbol)
        except Exception as exc:
            ERRORS.append({'source': 'Alpha Vantage', 'symbol': symbol, 'error': str(exc)})
            print('ERROR mercado:', symbol, type(exc).__name__)
        time.sleep(1)
    for series in SERIES:
        try:
            fred(series, fk)
            print('OK macro:', series)
        except Exception as exc:
            ERRORS.append({'source': 'FRED', 'series': series, 'error': str(exc)})
            print('ERROR macro:', series, type(exc).__name__)
    SUMMARY['complete'] = len(SUMMARY['markets']) == len(SYMBOLS) and len(SUMMARY['macro']) == len(SERIES)
    (OUT / 'report.json').write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=2), encoding='utf-8')
    if not SUMMARY['complete']:
        print(f'RECOPILACIÓN INCOMPLETA: {len(SUMMARY["markets"])}/{len(SYMBOLS)} mercados, '
              f'{len(SUMMARY["macro"])}/{len(SERIES)} series macro', file=sys.stderr)
    return 0 if SUMMARY['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
