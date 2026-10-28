
"""Actualiza el histórico ajustado de Yahoo Finance.
Valida todas las series antes de sustituir los archivos existentes.
No modifica historico/ ni output/.
"""
import csv
import math
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import yfinance as yf

START = '2016-01-01'
SYMBOLS = ('SPY', 'QQQ', 'SMH', 'ASML', 'AVGO')
DEST = Path('historico_inicial')
FIELDS = (
    'date', 'open', 'high', 'low', 'close', 'volume',
    'symbol', 'source', 'price_basis', 'retrieved_at_utc'
)


def download_one(symbol):
    frame = yf.download(
        symbol, start=START, interval='1d',
        auto_adjust=True, progress=False,
        threads=False, actions=False
    )
    if frame is None or frame.empty:
        raise ValueError('Yahoo Finance no ha devuelto cotizaciones')

    if getattr(frame.columns, 'nlevels', 1) > 1:
        frame.columns = frame.columns.get_level_values(0)

    needed = ('Open', 'High', 'Low', 'Close', 'Volume')
    if any(col not in frame.columns for col in needed):
        raise ValueError('Faltan columnas OHLCV')

    stamp = datetime.now(timezone.utc).isoformat()
    rows = []

    for day, record in frame.iterrows():
        values = [float(record[col]) for col in needed]
        op, hi, lo, cl, vol = values

        if not all(math.isfinite(v) for v in values):
            raise ValueError(f'Valor no finito: {symbol} {day}')

        if not (
            0 < lo <= min(op, cl)
            <= max(op, cl) <= hi
            and vol >= 0
        ):
            raise ValueError(f'OHLCV inválido: {symbol} {day}')

        rows.append(dict(zip(FIELDS, (
            day.strftime('%Y-%m-%d'),
            *values, symbol, 'Yahoo Finance via yfinance',
            'dividend_and_split_adjusted', stamp
        ))))

    if len(rows) < 500 or len({r['date'] for r in rows}) != len(rows):
        raise ValueError(f'Histórico insuficiente o duplicado: {symbol}')

    if rows != sorted(rows, key=lambda r: r['date']):
        raise ValueError(f'Fechas desordenadas: {symbol}')

    if (date.today() - date.fromisoformat(rows[-1]['date'])).days > 7:
        raise ValueError(f'Último cierre antiguo: {symbol}')

    target = DEST / f'market_{symbol}_adjusted.csv'

    if target.exists():
        with target.open(encoding='utf-8-sig', newline='') as f:
            previous = list(csv.DictReader(f))

        if previous and (
            len(rows) < len(previous) - 3
            or rows[-1]['date'] < previous[-1]['date']
        ):
            raise ValueError(f'Descarga truncada: {symbol}')

    print(f'VALIDADO {symbol}: {len(rows)} sesiones')
    return rows


def main():
    downloaded = {}
    failures = []

    for symbol in SYMBOLS:
        try:
            downloaded[symbol] = download_one(symbol)
        except Exception as exc:
            failures.append(symbol)
            print(f'ERROR {symbol}: {exc}', file=sys.stderr)

    if failures:
        print('No se ha sustituido ningún archivo.', file=sys.stderr)
        return 1

    ends = [date.fromisoformat(downloaded[s][-1]['date']) for s in SYMBOLS]

    if (max(ends) - min(ends)).days > 4:
        print('ERROR: fechas finales incompatibles', file=sys.stderr)
        return 1

    DEST.mkdir(parents=True, exist_ok=True)
    staged = []

    try:
        for symbol in SYMBOLS:
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', newline='',
                dir=DEST, prefix=f'.{symbol}_',
                suffix='.tmp', delete=False
            ) as f:
                path = Path(f.name)
                staged.append((
                    path,
                    DEST / f'market_{symbol}_adjusted.csv'
                ))
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(downloaded[symbol])

        for temp, target in staged:
            os.replace(temp, target)
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)

    print('Histórico ajustado actualizado.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
