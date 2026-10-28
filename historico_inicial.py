
"""Actualiza el historico ajustado de Yahoo Finance.

Valida todas las series antes de sustituir archivos.
No modifica historico/ ni output/.
"""
import csv
import math
import os
import sys
import tempfile
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import yfinance as yf

warnings.filterwarnings(
    "ignore",
    message=".*inplace keyword.*deprecated.*",
    category=FutureWarning,
)

START = "2016-01-01"
SYMBOLS = ("SPY", "QQQ", "SMH", "ASML", "AVGO")
DEST = Path("historico_inicial")

FIELDS = (
    "date", "open", "high", "low", "close", "volume",
    "symbol", "source", "price_basis", "retrieved_at_utc"
)


def log(message):
    print(message, flush=True)


def download_one(symbol):
    log(f"INICIO {symbol}")

    frame = yf.download(
        symbol,
        start=START,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
        actions=False,
    )

    if frame is None or frame.empty:
        raise ValueError("Yahoo Finance no devuelve cotizaciones")

    if getattr(frame.columns, "nlevels", 1) > 1:
        frame.columns = frame.columns.get_level_values(0)

    needed = ("Open", "High", "Low", "Close", "Volume")

    if any(col not in frame.columns for col in needed):
        raise ValueError("Faltan columnas OHLCV")

    stamp = datetime.now(timezone.utc).isoformat()
    rows = []

    for day, record in frame.iterrows():
        values = [float(record[col]) for col in needed]
        op, hi, lo, cl, vol = values

        if not all(math.isfinite(v) for v in values):
            raise ValueError(
                f"Valor no finito en {day.date()}: {values}"
            )

        if not (
            0 < lo <= min(op, cl)
            <= max(op, cl) <= hi
            and vol >= 0
        ):
            raise ValueError(
                f"OHLCV invalido en {day.date()}: "
                f"open={op}, high={hi}, low={lo}, "
                f"close={cl}, volume={vol}"
            )

        rows.append(dict(zip(FIELDS, (
            day.strftime("%Y-%m-%d"),
            *values,
            symbol,
            "Yahoo Finance via yfinance",
            "dividend_and_split_adjusted",
            stamp,
        ))))

    if len(rows) < 500:
        raise ValueError(
            f"Historico insuficiente: {len(rows)} sesiones"
        )

    if len({r["date"] for r in rows}) != len(rows):
        raise ValueError("Fechas duplicadas")

    if rows != sorted(rows, key=lambda r: r["date"]):
        raise ValueError("Fechas desordenadas")

    last = date.fromisoformat(rows[-1]["date"])
    age = (datetime.now(timezone.utc).date() - last).days

    log(
        f"DESCARGADO {symbol}: "
        f"{len(rows)} sesiones, ultimo cierre {last}"
    )

    if age > 7 or age < 0:
        raise ValueError(
            f"Fecha final invalida: {last}, antiguedad {age}"
        )

    target = DEST / f"market_{symbol}_adjusted.csv"

    if target.exists():
        with target.open(
            encoding="utf-8-sig", newline=""
        ) as f:
            previous = list(csv.DictReader(f))

        if previous:
            previous_last = previous[-1]["date"]

            log(
                f"COMPARACION {symbol}: "
                f"nuevo={len(rows)}, anterior={len(previous)}, "
                f"ultimo_nuevo={last}, "
                f"ultimo_anterior={previous_last}"
            )

            if len(rows) < len(previous) - 3:
                raise ValueError(
                    "Descarga truncada: "
                    f"{len(rows)} frente a {len(previous)}"
                )

            if rows[-1]["date"] < previous_last:
                raise ValueError(
                    f"Retroceso de fecha: "
                    f"{last} frente a {previous_last}"
                )

    log(f"VALIDADO {symbol}: {len(rows)} sesiones")
    return rows


def main():
    downloaded = {}
    failures = []

    for symbol in SYMBOLS:
        try:
            downloaded[symbol] = download_one(symbol)
        except Exception as exc:
            failures.append(symbol)
            log(
                f"ERROR_REAL {symbol}: "
                f"{type(exc).__name__}: {exc}"
            )

    if failures:
        log(
            "ACTUALIZACION CANCELADA. "
            "Activos fallidos: " + ", ".join(failures)
        )
        log("No se ha sustituido ningun archivo.")
        return 1

    ends = [
        date.fromisoformat(downloaded[s][-1]["date"])
        for s in SYMBOLS
    ]

    if (max(ends) - min(ends)).days > 4:
        log(
            "ERROR_REAL: fechas finales incompatibles: "
            + str(dict(zip(SYMBOLS, map(str, ends))))
        )
        return 1

    DEST.mkdir(parents=True, exist_ok=True)
    staged = []

    try:
        for symbol in SYMBOLS:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=DEST,
                prefix=f".{symbol}_",
                suffix=".tmp",
                delete=False,
            ) as f:
                path = Path(f.name)
                staged.append((
                    path,
                    DEST / f"market_{symbol}_adjusted.csv",
                ))
                writer = csv.DictWriter(
                    f, fieldnames=FIELDS
                )
                writer.writeheader()
                writer.writerows(downloaded[symbol])

        for temp, target in staged:
            os.replace(temp, target)

    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)

    log("HISTORICO AJUSTADO ACTUALIZADO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
