
"""Observatorio 6+1 - Sensibilidad a la fase de entrada.

Prueba todos los desplazamientos posibles de una
rejilla temporal de operaciones no solapadas.

Reutiliza las reglas de validacion_6plus1.py (v2).
No modifica los umbrales ni genera ordenes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import validacion_6plus1 as base

OUT = Path("output")
PERIODS = {
    "referencia_2016_2022": (
        "2016-01-01", "2023-01-01"
    ),
    "comprobacion_2023_2026": (
        "2023-01-01", "9999-12-31"
    ),
}


def stats(values):
    if not values:
        return {
            "n": 0,
            "mean_pct": None,
            "median_pct": None,
        }

    return {
        "n": len(values),
        "mean_pct": round(mean(values), 5),
        "median_pct": round(median(values), 5),
    }


def select_phase(
    signals, prices, dates,
    horizon, phase, start, end
):
    """Entradas espaciadas por horizon+1 sesiones.

    La fase fija la posicion dentro de esa rejilla.
    No se permite solapamiento dentro de cada fase.
    """

    stride = horizon + 1
    selected = []

    for i, date, adverse in signals:
        entry_index = i + 1
        exit_index = entry_index + horizon

        if date < start or date >= end:
            continue

        if exit_index >= len(dates):
            continue

        if dates[exit_index] >= end:
            continue

        if i % stride != phase:
            continue

        entry_price = prices["SPY"][entry_index][0]
        exit_price = prices["SPY"][exit_index][0]

        selected.append({
            "signal_date": date,
            "entry_index": entry_index,
            "exit_index": exit_index,
            "adverse": adverse,
            "return_pct": (
                exit_price / entry_price - 1
            ) * 100,
        })

    for a, b in zip(selected, selected[1:]):
        if b["entry_index"] <= a["exit_index"]:
            raise AssertionError(
                "Solapamiento dentro de la fase"
            )

    return selected


def analyze_phase(trades, phase):
    low = [
        t["return_pct"]
        for t in trades if t["adverse"] <= 1
    ]
    high = [
        t["return_pct"]
        for t in trades if t["adverse"] >= 2
    ]

    difference = (
        round(mean(high) - mean(low), 5)
        if low and high else None
    )

    return {
        "phase": phase,
        "total": len(trades),
        "low_adverse": stats(low),
        "high_adverse": stats(high),
        "difference_high_minus_low_pp":
            difference,
        "adequate_sample": (
            len(low) >= 20 and len(high) >= 20
        ),
    }


def analyze_period(
    signals, prices, dates,
    horizon, start, end
):
    phases = []

    for phase in range(horizon + 1):
        trades = select_phase(
            signals, prices, dates,
            horizon, phase, start, end
        )
        phases.append(
            analyze_phase(trades, phase)
        )

    valid = [
        p for p in phases
        if p["difference_high_minus_low_pp"]
        is not None
    ]

    adequate = [
        p for p in valid
        if p["adequate_sample"]
    ]

    differences = [
        p["difference_high_minus_low_pp"]
        for p in valid
    ]

    signs = {
        "positive": sum(x > 0 for x in differences),
        "negative": sum(x < 0 for x in differences),
        "zero": sum(x == 0 for x in differences),
    }

    return {
        "horizon": horizon,
        "phases_tested": len(phases),
        "phases_with_both_groups": len(valid),
        "phases_with_adequate_samples":
            len(adequate),
        "difference_range_pp": {
            "min": (
                round(min(differences), 5)
                if differences else None
            ),
            "max": (
                round(max(differences), 5)
                if differences else None
            ),
            "median": (
                round(median(differences), 5)
                if differences else None
            ),
        },
        "difference_signs": signs,
        "phases": phases,
    }


def main():
    raw = {
        symbol: base.load(symbol)
        for symbol in base.SYMBOLS
    }

    dates = sorted(
        set.intersection(
            *(set(v) for v in raw.values())
        )
    )

    if len(dates) < 500:
        raise SystemExit(
            "Historico insuficiente"
        )

    prices = {
        symbol: [
            raw[symbol][date] for date in dates
        ]
        for symbol in base.SYMBOLS
    }

    signals = base.calculate_signals(
        prices, dates
    )

    report = {
        "schema_version": 1,
        "generated_at_utc":
            datetime.now(timezone.utc).isoformat(),
        "reference_validation": "v2",
        "last_session": dates[-1],
        "method": (
            "Rejillas temporales de operaciones "
            "sin solapamiento por fase"
        ),
        "periods": {},
        "limitations": [
            "Las fases son alternativas, no muestras independientes.",
            "Las fases comparten datos de mercado y pueden tener ventanas solapadas entre si.",
            "El desplazamiento se define sobre sesiones, no sobre dias naturales.",
            "No es una prueba fuera de muestra.",
            "Los umbrales ya fueron seleccionados con conocimiento historico.",
            "No hay intervalos de confianza ni correccion por pruebas multiples.",
            "Las muestras adversas pueden ser demasiado pequenas.",
            "No se ha implementado una estrategia ejecutable frente a buy-and-hold.",
            "Las diferencias no incluyen costes ni impuestos.",
        ],
    }

    md = [
        "# Sensibilidad temporal 6+1",
        "",
        f"Ultima sesion: {dates[-1]}",
        "",
        "Diferencia = retorno medio con 2-3 "
        "senales adversas menos retorno medio "
        "con 0-1 senales.",
        "",
        "| Periodo | Horizonte | Fases | "
        "Fases con ambas muestras | "
        "Fases con n>=20 en ambos grupos | "
        "Rango diferencia |",
        "|---|---:|---:|---:|---:|---|",
    ]

    for period, (start, end) in PERIODS.items():
        results = {}

        for horizon in base.HORIZONS:
            result = analyze_period(
                signals, prices, dates,
                horizon, start, end
            )

            results[str(horizon)] = result
            rng = result["difference_range_pp"]

            interval = (
                f"{rng['min']:+.3f} a "
                f"{rng['max']:+.3f} pp"
                if rng["min"] is not None
                else "N/D"
            )

            md.append(
                f"| {period} | {horizon} | "
                f"{result['phases_tested']} | "
                f"{result['phases_with_both_groups']} | "
                f"{result['phases_with_adequate_samples']} | "
                f"{interval} |"
            )

        report["periods"][period] = results

    md.extend([
        "",
        "## Interpretacion",
        "",
        "Un cambio de signo entre fases indica "
        "sensibilidad al punto de entrada. "
        "Un signo estable tampoco demuestra "
        "capacidad predictiva.",
        "",
        "Los resultados de distintas fases "
        "estan correlacionados. No deben "
        "tratarse como replicaciones independientes.",
        "",
        "## Limitaciones",
        "",
    ])

    md.extend(
        "- " + item
        for item in report["limitations"]
    )

    OUT.mkdir(
        parents=True, exist_ok=True
    )

    (OUT / "sensibilidad_6plus1.json").write_text(
        json.dumps(
            report, indent=2,
            ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    (OUT / "sensibilidad_6plus1.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("\n".join(md[:15]))
    print("Sensibilidad temporal completada")


if __name__ == "__main__":
    main()
  
