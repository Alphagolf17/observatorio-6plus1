
"""Registro prospectivo 6+1.
Conserva señales y evalúa resultados futuros sin generar órdenes.
"""
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

OUT = Path("output")
DEST = Path("registro_senales")
HORIZONS = (5, 10, 20)
SYMBOLS = ("SPY", "QQQ", "SMH")
EXPECTED = 6


def read_prices(symbol):
    path = Path("historico") / f"market_{symbol}.csv"
    if not path.exists():
        raise ValueError(f"Falta {path}")
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            day = date.fromisoformat(row["date"]).isoformat()
            close = float(row["close"])
            if close <= 0:
                raise ValueError(f"Precio inválido: {symbol} {day}")
            result[day] = close
    return result


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def main():
    radar_path = OUT / "radar_6plus1.json"
    radar = json.loads(radar_path.read_text(encoding="utf-8"))
    assessment = radar["risk_assessment"]
    markets = radar["market_data"]

    if (
        assessment["available_signals"] != EXPECTED
        or len(radar["signals"]) != EXPECTED
    ):
        raise SystemExit("Radar incompleto: no se registra señal")

    if radar.get("warnings"):
        raise SystemExit("Radar con advertencias")

    if any(s not in markets for s in SYMBOLS):
        raise SystemExit("Faltan SPY/QQQ/SMH")

    signal_date = markets["SPY"]["date"]
    if any(markets[s]["date"] != signal_date for s in SYMBOLS):
        raise SystemExit("Fechas de mercado no alineadas")

    age = (
        datetime.now(timezone.utc).date()
        - date.fromisoformat(signal_date)
    ).days
    if not 0 <= age <= 5:
        raise SystemExit("Cierre desactualizado o futuro")

    prices = {s: read_prices(s) for s in SYMBOLS}
    common_dates = sorted(
        set.intersection(*(set(p) for p in prices.values()))
    )

    if signal_date not in common_dates:
        raise SystemExit("Fecha del radar ausente del histórico")

    DEST.mkdir(exist_ok=True)
    snapshot = DEST / f"senal_{signal_date}.json"
    created = False

    if not snapshot.exists():
        frozen = {
            "schema_version": 1,
            "signal_date": signal_date,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "radar_generated_at_utc": radar["generated_at_utc"],
            "type": "observacion_prospectiva_no_operativa",
            "risk_assessment": assessment,
            "signals": radar["signals"],
            "market_data": {s: markets[s] for s in SYMBOLS},
            "relative_return_20_sessions_vs_spy_percentage_points":
                radar.get(
                    "relative_return_20_sessions_vs_spy_percentage_points"
                ),
            "liquidity_proxy": radar.get("liquidity_proxy"),
            "macro_latest": radar.get("macro_latest"),
            "price_basis":
                "Alpha Vantage sin ajuste de dividendos",
            "limitations":
                "Resultados cierre-cierre, sin costes ni dividendos.",
        }
        atomic_json(snapshot, frozen)
        created = True

    outcomes_path = DEST / "resultados.json"
    outcomes = (
        json.loads(outcomes_path.read_text(encoding="utf-8"))
        if outcomes_path.exists() else {}
    )

    positions = {
        d: i for i, d in enumerate(common_dates)
    }

    for path in sorted(DEST.glob("senal_????-??-??.json")):
        recorded = json.loads(path.read_text(encoding="utf-8"))
        d = recorded["signal_date"]

        if d not in positions:
            continue

        idx = positions[d]

        for h in HORIZONS:
            key = f"{d}_{h}"

            if key in outcomes or idx + h >= len(common_dates):
                continue

            future = common_dates[idx + h]

            ret = {
                s: round(
                    (prices[s][future] / prices[s][d] - 1) * 100,
                    4,
                )
                for s in SYMBOLS
            }

            outcomes[key] = {
                "signal_date": d,
                "horizon_sessions": h,
                "evaluation_date": future,
                "returns_pct_unadjusted": ret,
                "qqq_minus_spy_pp":
                    round(ret["QQQ"] - ret["SPY"], 4),
                "smh_minus_spy_pp":
                    round(ret["SMH"] - ret["SPY"], 4),
                "note":
                    "Retornos cierre-cierre; no son operaciones ejecutables.",
            }

    atomic_json(outcomes_path, outcomes)

    report = {
        "latest_signal_date": signal_date,
        "new_snapshot_created": created,
        "total_snapshots": len(
            list(DEST.glob("senal_????-??-??.json"))
        ),
        "matured_outcomes": len(outcomes),
        "risk_score": assessment["risk_score_0_100"],
        "traffic_light": assessment["traffic_light"],
        "limitations":
            "Registro descriptivo, no prueba de ventaja predictiva.",
    }

    atomic_json(OUT / "registro_senales_resumen.json", report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
