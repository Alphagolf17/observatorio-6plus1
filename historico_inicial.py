"""Descarga puntual de precios diarios ajustados para análisis histórico.
No modifica output/ ni historico/; guarda CSV independientes en historico_inicial/.
Ejecutar una sola vez desde un workflow específico, no en la tarea diaria.
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

START = '2016-01-01'
SYMBOLS = ('SPY', 'QQQ', 'SMH', 'ASML', 'AVGO')
DEST = Path('historico_inicial')
FIELDS = ('date', 'open', 'high', 'low', 'close', 'volume', 'symbol', 'source', 'price_basis', 'retrieved_at_utc')


def download_one(symbol):
    frame = yf.download(symbol, start=START, interval='1d', auto_adjust=True,
                        progress=False, threads=False, actions=False)
    if frame is None or frame.empty:
        raise ValueError('La fuente no ha devuelto cotizaciones')
    # Algunas versiones de yfinance entregan columnas MultiIndex.
    if getattr(frame.columns, 'nlevels', 1) > 1:
        frame.columns = frame.columns.get_level_values(0)
    needed = ('Open', 'High', 'Low', 'Close', 'Volume')
    if any(col not in frame.columns for col in needed):
        raise ValueError('Faltan columnas OHLCV')
    stamp = datetime.now(timezone.utc).isoformat()
    rows = []
    for day, record in frame.iterrows():
        try:
            values = [float(record[col]) for col in needed]
        except (TypeError, ValueError):
            continue
        if any(not (float('-inf') < value < float('inf')) for value in values):
            continue
        if values[3] <= 0:
            continue
        rows.append(dict(zip(FIELDS, (
            day.strftime('%Y-%m-%d'), *values, symbol, 'Yahoo Finance via yfinance',
            'dividend_and_split_adjusted', stamp))))
    if len(rows) < 500:
        raise ValueError(f'Histórico demasiado corto: {len(rows)} sesiones')
    DEST.mkdir(parents=True, exist_ok=True)
    target = DEST / f'market_{symbol}_adjusted.csv'
    with target.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f'OK {symbol}: {len(rows)} sesiones ({rows[0]["date"]} a {rows[-1]["date"]})')


def main():
    failures = []
    for symbol in SYMBOLS:
        try:
            download_one(symbol)
        except Exception as exc:
            failures.append(symbol)
            print(f'ERROR {symbol}: {type(exc).__name__}: {exc}', file=sys.stderr)
    if failures:
        print('Símbolos pendientes: ' + ', '.join(failures), file=sys.stderr)
        return 1
    print('Descarga histórica completada. No se han modificado los CSV diarios.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
