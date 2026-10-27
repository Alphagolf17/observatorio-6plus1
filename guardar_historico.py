"""Conserva CSV diarios de output/ en historico/ sin borrar fechas anteriores.
Solo almacena series públicas; no lee ni escribe claves API.
"""
from pathlib import Path
import csv
import io
import os

SOURCE = Path('output')
DEST = Path('historico')


def load_rows(path):
    if not path.exists():
        return [], []
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or 'date' not in reader.fieldnames:
            raise ValueError(f'CSV sin columna date: {path}')
        return reader.fieldnames, list(reader)


def merge_one(source):
    target = DEST / source.name
    old_cols, old_rows = load_rows(target)
    new_cols, new_rows = load_rows(source)
    if not new_rows:
        print(f'Sin datos nuevos: {source.name}')
        return
    cols = list(dict.fromkeys(old_cols + new_cols))
    # Las filas más recientes reemplazan revisiones de la misma fecha.
    # No se eliminan fechas históricas que falten en una respuesta de API.
    rows = {r['date']: r for r in old_rows if r.get('date')}
    for row in new_rows:
        if row.get('date'):
            rows[row['date']] = row
    DEST.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.csv.tmp')
    with temp.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        writer.writeheader()
        for date in sorted(rows):
            writer.writerow(rows[date])
    os.replace(temp, target)
    print(f'{source.name}: {len(old_rows)} previas + {len(new_rows)} recibidas => {len(rows)} fechas')


def main():
    sources = sorted(SOURCE.glob('market_*.csv')) + sorted(SOURCE.glob('fred_*.csv'))
    if not sources:
        raise SystemExit('ERROR: no hay CSV en output/. No se guardará un histórico vacío.')
    for source in sources:
        merge_one(source)
    print(f'Histórico actualizado: {len(sources)} series.')


if __name__ == '__main__':
    main()
