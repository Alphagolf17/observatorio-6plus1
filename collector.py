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
ERRORS = []
SUMMARY = {'collected_at_utc': STAMP, 'markets': {}, 'macro': {}, 'warnings': ERRORS,
           'disclaimer': 'Datos con retrasos y frecuencias distintas. No representan flujos netos de capital.'}

def fetch(url, params):
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + '?' + query, headers={'User-Agent': 'observatorio-6plus1/1.0'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def save_csv(filename, rows, fields):
    with (OUT / filename).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def market(symbol, key):
    data = fetch('https://www.alphavantage.co/query', {
        'function': 'TIME_SERIES_DAILY', 'symbol': symbol, 'outputsize': 'compact', 'apikey': key})
    series = data.get('Time Series (Daily)')
    if not series:
        raise ValueError('No se recibio serie diaria; posible limite, simbolo no disponible o plan insuficiente')
    rows = [{'date': day, 'open': val['1. open'], 'high': val['2. high'],
             'low': val['3. low'], 'close': val['4. close'], 'volume': val['5. volume'],
             'symbol': symbol, 'source': 'Alpha Vantage', 'retrieved_at_utc': STAMP}
            for day, val in sorted(series.items())]
    save_csv('market_' + symbol + '.csv', rows, list(rows[0]))
    last = rows[-1]
    SUMMARY['markets'][symbol] = {'last_date': last['date'], 'last_close': float(last['close']),
                                  'last_volume': int(last['volume']), 'observations': len(rows)}

def fred(series_id, key):
    data = fetch('https://api.stlouisfed.org/fred/series/observations', {
        'series_id': series_id, 'api_key': key, 'file_type': 'json', 'observation_start': '2016-01-01'})
    obs = data.get('observations', [])
    rows = [{'date': v['date'], 'value': v['value'], 'series': series_id,
             'source': 'FRED', 'retrieved_at_utc': STAMP} for v in obs if v['value'] != '.']
    if not rows:
        raise ValueError('Serie FRED sin observaciones')
    save_csv('fred_' + series_id + '.csv', rows, list(rows[0]))
    SUMMARY['macro'][series_id] = {'last_date': rows[-1]['date'],
                                   'last_value': float(rows[-1]['value']), 'observations': len(rows)}

def main():
    av = os.environ.get('ALPHAVANTAGE_API_KEY', '')
    fk = os.environ.get('FRED_API_KEY', '')
    if not av or not fk:
        print('Faltan secretos ALPHAVANTAGE_API_KEY o FRED_API_KEY', file=sys.stderr)
        return 1
    for symbol in ['SPY', 'QQQ', 'SMH', 'ASML', 'AVGO']:
        try:
            market(symbol, av)
            print('OK mercado:', symbol)
        except Exception as exc:
            ERRORS.append({'source': 'Alpha Vantage', 'symbol': symbol, 'error': str(exc)})
            print('ERROR mercado:', symbol, type(exc).__name__)
        time.sleep(1)
    for series in ['WALCL', 'WTREGEN', 'RRPONTSYD', 'DGS10', 'DFII10', 'BAMLH0A0HYM2', 'VIXCLS', 'DTWEXBGS']:
        try:
            fred(series, fk)
            print('OK macro:', series)
        except Exception as exc:
            ERRORS.append({'source': 'FRED', 'series': series, 'error': str(exc)})
            print('ERROR macro:', series, type(exc).__name__)
    (OUT / 'report.json').write_text(json.dumps(SUMMARY, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if SUMMARY['markets'] and SUMMARY['macro'] else 1

if __name__ == '__main__':
    sys.exit(main())
