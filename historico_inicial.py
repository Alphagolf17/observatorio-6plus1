
"""Observatorio 6+1 - Historico ajustado.

Descarga y valida precios ajustados de Yahoo Finance.
Excluye sesiones estadounidenses todavia abiertas.
Tolera errores insignificantes de precision decimal.
No modifica historico/ ni output/.
"""

import csv
import math
import os
import sys
import tempfile
import warnings

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

warnings.filterwarnings(
    "ignore",
    message=".*inplace keyword.*deprecated.*",
)

START = "2016-01-01"
SYMBOLS = ("SPY", "QQQ", "SMH", "ASML", "AVGO")
DEST = Path("historico_inicial")
NEW_YORK = ZoneInfo("America/New_York")

FIELDS = (
    "date", "open", "high", "low", "close", "volume",
    "symbol", "source", "price_basis", "retrieved_at_utc"
)


def log(message):
    print(message, flush=True)


def last_eligible_date():
    now = datetime.now(timezone.utc).astimezone(NEW_YORK)

    # Cierre ordinario: 16:00 hora de Nueva York.
    # Margen adicional de 90 minutos.
    threshold = datetime.combine(
        now.date(),
        time(17, 30),
        tzinfo=NEW_YORK,
    )

    if now < threshold:
        candidate = now.date() - timedelta(days=1)
    else:
        candidate = now.date()

    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)

    return candidate


def validate_ohlcv(symbol, day, values):
    op, hi, lo, cl, vol = values

    if not all(math.isfinite(v) for v in values):
        raise ValueError(
            f"Valores no finitos: {symbol} {day}"
        )

    # Tolerancia exclusivamente numerica.
    # No modifica los precios descargados.
    tolerance = max(
        1e-8,
        max(abs(op), abs(hi), abs(lo), abs(cl)) * 1e-10,
    )

    if not (
        lo > 0
        and op > 0
        and hi > 0
        and cl > 0
        and vol >= 0
        and lo <= hi + tolerance
        and lo <= op + tolerance
        and lo <= cl + tolerance
        and op <= hi + tolerance
        and cl <= hi + tolerance
    ):
        raise ValueError(
            f"OHLCV invalido: {symbol} {day}; "
            f"open={op}, high={hi}, low={lo}, "
            f"close={cl}, volume={vol}"
        )


def download_one(symbol, cutoff):
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
        raise ValueError(
            "Yahoo Finance no devuelve cotizaciones"
        )

    if getattr(frame.columns, "nlevels", 1) > 1:
        frame.columns = frame.columns.get_level_values(0)

    needed = ("Open", "High", "Low", "Close", "Volume")

    if any(col not in frame.columns for col in needed):
        raise ValueError("Faltan columnas OHLCV")

    stamp = datetime.now(timezone.utc).isoformat()
    rows = []
    excluded = 0

    for day, record in frame.iterrows():
        day_date = day.date()

        if day_date > cutoff:
            excluded += 1
            continue

        values = [
            float(record[col])
            for col in needed
        ]

        validate_ohlcv(symbol, day_date, values)

        rows.append(dict(zip(FIELDS, (
            day_date.isoformat(),
            *values,
            symbol,
            "Yahoo Finance via yfinance",
            "dividend_and_split_adjusted",
            stamp,
        ))))

    log(
        f"DESCARGADO {symbol}: "
        f"{len(rows)} sesiones; "
        f"filas excluidas={excluded}"
    )

    if len(rows) < 500:
        raise ValueError(
            f"Historico insuficiente: {len(rows)} sesiones"
        )

    if len({r["date"] for r in rows}) != len(rows):
        raise ValueError("Fechas duplicadas")

    if rows != sorted(rows, key=lambda r: r["date"]):
        raise ValueError("Fechas desordenadas")

    last = date.fromisoformat(rows[-1]["date"])
    age = (cutoff - last).days

    if not 0 <= age <= 7:
        raise ValueError(
            f"Ultimo cierre desactualizado: "
            f"{last}; corte={cutoff}"
        )

    target = DEST / f"market_{symbol}_adjusted.csv"

    if target.exists():
        with target.open(
            encoding="utf-8-sig",
            newline="",
        ) as f:
            previous = list(csv.DictReader(f))

        if previous:
            previous_eligible = [
                r for r in previous
                if r["date"] <= cutoff.isoformat()
            ]

            log(
                f"COMPARACION {symbol}: "
                f"nuevo={len(rows)}, "
                f"anterior={len(previous)}, "
                f"ultimo_nuevo={last}, "
                f"ultimo_anterior={previous[-1]['date']}"
            )

            if len(rows) < len(previous_eligible) - 3:
                raise ValueError(
                    f"Descarga truncada: "
                    f"{len(rows)} frente a "
                    f"{len(previous_eligible)}"
                )

            if (
                previous_eligible
                and rows[-1]["date"]
                < previous_eligible[-1]["date"]
            ):
                raise ValueError(
                    "Retroceso respecto al ultimo cierre elegible"
                )

    log(
        f"VALIDADO {symbol}: "
        f"{len(rows)} sesiones; "
        f"ultimo cierre={last}"
    )

    return rows


def main():
    cutoff = last_eligible_date()
    log(f"CORTE DE SEGURIDAD: {cutoff}")

    downloaded = {}
    failures = []

    for symbol in SYMBOLS:
        try:
            downloaded[symbol] = download_one(
                symbol, cutoff
            )
        except Exception as exc:
            failures.append(symbol)
            log(
                f"ERROR_REAL {symbol}: "
                f"{type(exc).__name__}: {exc}"
            )

    if failures:
        log(
            "ACTUALIZACION CANCELADA: "
            + ", ".join(failures)
        )
        log("No se ha sustituido ningun archivo.")
        return 1

    ends = [
        date.fromisoformat(
            downloaded[s][-1]["date"]
        )
        for s in SYMBOLS
    ]

    if (max(ends) - min(ends)).days > 4:
        log("ERROR_REAL: fechas finales incompatibles")
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
                    f,
                    fieldnames=FIELDS,
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
