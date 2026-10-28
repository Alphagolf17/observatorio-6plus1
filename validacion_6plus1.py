
"""Observatorio 6+1 - Auditoria estadistica v2.

Reglas fijas, entrada a la apertura siguiente.
Seleccion cronologica global sin solapamiento por horizonte.
No representa una estrategia de trading validada.
Solo biblioteca estandar.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path("historico_inicial")
OUT = Path("output")

SYMBOLS = ("SPY", "QQQ", "SMH")
HORIZONS = (5, 10, 20)
CUTOFF = "2023-01-01"
COST_ROUND_TRIP_PCT = 0.10


def load(symbol):
    path = ROOT / f"market_{symbol}_adjusted.csv"

    if not path.exists():
        raise SystemExit(f"Falta {path}")

    data = {}

    with path.open(
        encoding="utf-8-sig", newline=""
    ) as file:
        for row in csv.DictReader(file):
            if row.get("price_basis") != (
                "dividend_and_split_adjusted"
            ):
                raise SystemExit(
                    f"Base de precios incorrecta: {path}"
                )

            try:
                date = row["date"]
                op = float(row["open"])
                cl = float(row["close"])
            except (KeyError, ValueError, TypeError):
                raise SystemExit(
                    f"Fila invalida en {path}"
                )

            if op <= 0 or cl <= 0:
                raise SystemExit(
                    f"Precio no positivo en {path}"
                )

            if date in data:
                raise SystemExit(
                    f"Fecha duplicada en {path}: {date}"
                )

            data[date] = (op, cl)

    return data


def summary(values):
    if not values:
        return {
            "n": 0,
            "mean_pct": None,
            "median_pct": None,
            "positive_pct": None,
        }

    return {
        "n": len(values),
        "mean_pct": round(mean(values), 4),
        "median_pct": round(median(values), 4),
        "positive_pct": round(
            100 * sum(x > 0 for x in values)
            / len(values), 2
        ),
    }


def summarize_trades(trades):
    groups = {
        "0_or_1_adverse": [],
        "2_or_3_adverse": [],
    }

    for trade in trades:
        groups[trade["group"]].append(
            trade["gross_return_pct"]
        )

    low = summary(groups["0_or_1_adverse"])
    high = summary(groups["2_or_3_adverse"])

    difference = None

    if low["n"] and high["n"]:
        difference = round(
            high["mean_pct"] - low["mean_pct"], 4
        )

    return {
        "total_trades": len(trades),
        "0_or_1_adverse": low,
        "2_or_3_adverse": high,
        "difference_pp": difference,
        "both_groups_n_at_least_20": (
            low["n"] >= 20 and high["n"] >= 20
        ),
        "benchmark_all_trades": summary([
            t["gross_return_pct"] for t in trades
        ]),
        "hypothetical_cost_adjusted": {
            "cost_round_trip_pct":
                COST_ROUND_TRIP_PCT,
            "all_trades": summary([
                t["gross_return_pct"]
                - COST_ROUND_TRIP_PCT
                for t in trades
            ]),
        },
    }


def calculate_signals(prices, dates):
    closes = {
        s: [x[1] for x in prices[s]]
        for s in SYMBOLS
    }

    signals = []

    for i in range(20, len(dates)):
        spy20 = (
            closes["SPY"][i]
            / closes["SPY"][i - 20] - 1
        ) * 100

        qqq20 = (
            closes["QQQ"][i]
            / closes["QQQ"][i - 20] - 1
        ) * 100

        smh20 = (
            closes["SMH"][i]
            / closes["SMH"][i - 20] - 1
        ) * 100

        ma20 = mean(
            closes["SPY"][i - 19:i + 1]
        )

        adverse = sum((
            smh20 - spy20 < -5,
            qqq20 - spy20 < -2,
            closes["SPY"][i] < ma20,
        ))

        signals.append((i, dates[i], adverse))

    return signals


def select_trades(
    signals, prices, dates, horizon,
    start, end
):
    """Una sola secuencia, sin solapamiento global."""

    selected = []
    last_exit_index = -1

    for i, date, adverse in signals:
        exit_index = i + horizon + 1

        if date < start or date >= end:
            continue

        if exit_index >= len(dates):
            continue

        if dates[exit_index] >= end:
            continue

        entry_index = i + 1

        if entry_index <= last_exit_index:
            continue

        entry = prices["SPY"][entry_index][0]
        exit_price = prices["SPY"][exit_index][0]

        gross = (
            exit_price / entry - 1
        ) * 100

        selected.append({
            "signal_date": date,
            "entry_date": dates[entry_index],
            "exit_date": dates[exit_index],
            "entry_index": entry_index,
            "exit_index": exit_index,
            "adverse_signals": adverse,
            "group": (
                "2_or_3_adverse"
                if adverse >= 2
                else "0_or_1_adverse"
            ),
            "gross_return_pct": round(
                gross, 6
            ),
        })

        last_exit_index = exit_index

    for first, second in zip(
        selected, selected[1:]
    ):
        if (
            second["entry_index"]
            <= first["exit_index"]
        ):
            raise AssertionError(
                "Solapamiento temporal detectado"
            )

    return selected


def main():
    raw = {
        s: load(s) for s in SYMBOLS
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
        s: [raw[s][d] for d in dates]
        for s in SYMBOLS
    }

    signals = calculate_signals(
        prices, dates
    )

    # Los CSV ajustados ya excluyen sesiones
    # abiertas en su proceso de descarga.
    # No se descarta artificialmente otro cierre.
    periods = {
        "referencia_2016_2022": (
            dates[0], CUTOFF
        ),
        "comprobacion_2023_2026": (
            CUTOFF, "9999-12-31"
        ),
    }

    result = {
        "schema_version": 2,
        "method": (
            "Auditoria retrospectiva con "
            "seleccion cronologica global"
        ),
        "start_date": dates[0],
        "end_date": dates[-1],
        "aligned_sessions": len(dates),
        "cutoff": CUTOFF,
        "horizons": {},
        "rules": [
            "SMH-SPY 20 sesiones < -5 pp",
            "QQQ-SPY 20 sesiones < -2 pp",
            "SPY por debajo de MA20",
        ],
        "execution": (
            "Senal al cierre t; "
            "entrada apertura t+1; "
            "salida apertura t+h+1"
        ),
        "selection": (
            "Una secuencia global por horizonte "
            "y periodo; seleccion cronologica "
            "independiente de la categoria"
        ),
        "limitations": [
            "Es una comparacion descriptiva, "
            "no una estrategia operativa.",
            "La seleccion cronologica depende "
            "del primer punto de entrada.",
            "Las muestras de distintos horizontes "
            "no son independientes.",
            "Las ventanas de indicadores se solapan.",
            "Los precios ajustados no equivalen "
            "a precios ejecutables reales.",
            "El coste hipotetico es uniforme "
            "y no incluye impuestos.",
            "El grupo 2023+ no es una prueba "
            "genuinamente fuera de muestra.",
            "No se han modelado decisiones "
            "de entrada y salida basadas "
            "en las senales.",
            "No se han incorporado datos macro "
            "con sus fechas de publicacion.",
            "No hay pruebas de significacion "
            "ni correccion por multiples ensayos.",
        ],
    }

    markdown = [
        "# Auditoria estadistica 6+1 - v2",
        "",
        f"Periodo: {dates[0]} a {dates[-1]}",
        "",
        "Seleccion global sin solapamiento "
        "entre categorias, por horizonte.",
        "",
        "| Horizonte | Periodo | "
        "0-1 adversas | 2-3 adversas | "
        "Diferencia |",
        "|---|---|---:|---:|---:|",
    ]

    for horizon in HORIZONS:
        horizon_result = {}

        for name, (start, end) in periods.items():
            trades = select_trades(
                signals, prices, dates,
                horizon, start, end
            )

            stats = summarize_trades(trades)

            yearly = defaultdict(list)

            for trade in trades:
                year = trade[
                    "signal_date"
                ][:4]
                yearly[year].append(trade)

            stats["by_year"] = {
                year: summarize_trades(rows)
                for year, rows in sorted(
                    yearly.items()
                )
            }

            horizon_result[name] = stats

            def fmt(group):
                if not group["n"]:
                    return "N/D"

                return (
                    f"{group['mean_pct']:+.3f}% "
                    f"(n={group['n']})"
                )

            difference = (
                f"{stats['difference_pp']:+.3f} pp"
                if stats["difference_pp"]
                is not None else "N/D"
            )

            markdown.append(
                f"| {horizon} | {name} | "
                f"{fmt(stats['0_or_1_adverse'])} | "
                f"{fmt(stats['2_or_3_adverse'])} | "
                f"{difference} |"
            )

        result["horizons"][
            str(horizon)
        ] = horizon_result

    markdown.extend([
        "",
        "## Interpretacion",
        "",
        "La diferencia compara rentabilidades "
        "condicionales de SPY. No mide "
        "rentabilidad incremental frente "
        "a comprar y mantener.",
        "",
        "El benchmark_all_trades muestra "
        "el retorno de SPY en las mismas "
        "ventanas seleccionadas, no un "
        "backtest independiente de buy-and-hold.",
        "",
        "El coste hipotetico de 0,10% "
        "por operacion es ilustrativo.",
        "",
        "## Limitaciones",
        "",
    ])

    markdown.extend(
        "- " + item
        for item in result["limitations"]
    )

    OUT.mkdir(
        parents=True, exist_ok=True
    )

    (OUT / "validacion_6plus1.json").write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ) + "\n",
        encoding="utf-8",
    )

    (OUT / "validacion_6plus1.md").write_text(
        "\n".join(markdown) + "\n",
        encoding="utf-8",
    )

    print("\n".join(markdown[:15]))
    print("Auditoria estadistica v2 completada")


if __name__ == "__main__":
    main()
