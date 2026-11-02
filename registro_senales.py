
"""Observatorio 6+1: registro y evaluación prospectiva.

No genera órdenes de inversión.
No modifica las fotografías históricas ya registradas.
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


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


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


def main():
    now = utc_now()
    radar = json.loads(
        (OUT / "radar_6plus1.json").read_text(
            encoding="utf-8"
        )
    )

    assessment = radar["risk_assessment"]
    markets = radar["market_data"]
    signals = radar["signals"]

    

    if (
        assessment["available_signals"] != EXPECTED
        or len(signals) != EXPECTED
        or assessment.get("traffic_light") == "sin_datos"
    ):
        raise SystemExit("Radar incompleto: señales insuficientes")

):
    raise SystemExit("Radar incompleto: señales insuficientes")

    ):
        raise SystemExit("Radar incompleto o con advertencias")

    if any(s not in markets for s in SYMBOLS):
        raise SystemExit("Faltan activos de referencia")

    signal_date = markets["SPY"]["date"]

    if any(
        markets[s]["date"] != signal_date
        for s in SYMBOLS
    ):
        raise SystemExit("Fechas no alineadas")

    age = (
        now.date() - date.fromisoformat(signal_date)
    ).days

    if not 0 <= age <= 5:
        raise SystemExit("Cierre demasiado antiguo o futuro")

    generated = parse_time(radar["generated_at_utc"])
    if generated > now:
        raise SystemExit("Fecha de generación futura")

    if (now - generated).total_seconds() > 3600:
        raise SystemExit("Radar generado hace más de una hora")

    prices = {s: read_prices(s) for s in SYMBOLS}
    common_dates = sorted(
        set.intersection(
            *(set(p) for p in prices.values())
        )
    )

    if signal_date not in common_dates:
        raise SystemExit("Fecha ausente del histórico")

    # No registrar un cierre si ya hay precios posteriores.
    if common_dates[-1] != signal_date:
        raise SystemExit(
            "El histórico contiene sesiones posteriores al radar"
        )

    DEST.mkdir(parents=True, exist_ok=True)
    snapshot = DEST / f"senal_{signal_date}.json"
    created = False

    if not snapshot.exists():
        frozen = {
            "schema_version": 2,
            "signal_date": signal_date,
            "recorded_at_utc": now.isoformat(),
            "radar_generated_at_utc":
                radar["generated_at_utc"],
            "type": "observacion_no_operativa",
            "evaluation_method":
                "primer_cierre_posterior_al_registro",
            "risk_assessment": assessment,
            "signals": signals,
            "market_data": {
                s: markets[s] for s in SYMBOLS
            },
            "relative_return_20_sessions_vs_spy_percentage_points":
                radar.get(
                    "relative_return_20_sessions_vs_spy_percentage_points"
                ),
            "liquidity_proxy":
                radar.get("liquidity_proxy"),
            "macro_latest":
                radar.get("macro_latest"),
            "price_basis":
                "cierres no ajustados de Alpha Vantage",
            "limitations":
                "Sin costes, dividendos ni ejecución real. "
                "Datos macro no reconstruidos por publicación.",
        }
        atomic_json(snapshot, frozen)
        created = True

    outcomes_path = DEST / "resultados.json"
    outcomes = (
        json.loads(outcomes_path.read_text(encoding="utf-8"))
        if outcomes_path.exists()
        else {}
    )

    positions = {
        d: i for i, d in enumerate(common_dates)
    }

    for path in sorted(
        DEST.glob("senal_????-??-??.json")
    ):
        recorded = json.loads(
            path.read_text(encoding="utf-8")
        )
        d = recorded["signal_date"]

        if d not in positions:
            continue

        recorded_at = parse_time(
            recorded["recorded_at_utc"]
        )

        # Primera sesión con fecha posterior al registro.
        entry_idx = next(
            (
                i for i, day in enumerate(common_dates)
                if date.fromisoformat(day) >
                   recorded_at.date()
            ),
            None,
        )

        if entry_idx is None:
            continue

        entry_date = common_dates[entry_idx]

        for h in HORIZONS:
            key = f"{d}_{h}"

            # Conservar resultados existentes.
            if key in outcomes:
                continue

            # Horizonte contado desde el cierre de entrada.
            exit_idx = entry_idx + h
            if exit_idx >= len(common_dates):
                continue

            exit_date = common_dates[exit_idx]

            returns = {
                s: round(
                    (
                        prices[s][exit_date]
                        / prices[s][entry_date] - 1
                    ) * 100,
                    4,
                )
                for s in SYMBOLS
            }

            outcomes[key] = {
                "signal_date": d,
                "recorded_at_utc":
                    recorded["recorded_at_utc"],
                "entry_date": entry_date,
                "evaluation_date": exit_date,
                "horizon_sessions": h,
                "returns_pct_unadjusted": returns,
                "qqq_minus_spy_pp": round(
                    returns["QQQ"] - returns["SPY"], 4
                ),
                "smh_minus_spy_pp": round(
                    returns["SMH"] - returns["SPY"], 4
                ),
                "method":
                    "cierre posterior al registro "
                    "hasta cierre tras h sesiones",
                "limitations":
                    "No equivale a operación ejecutable. "
                    "Sin dividendos ni costes.",
            }

    atomic_json(outcomes_path, outcomes)

    snapshots = list(
        DEST.glob("senal_????-??-??.json")
    )

    report = {
        "latest_signal_date": signal_date,
        "new_snapshot_created": created,
        "total_snapshots": len(snapshots),
        "matured_outcomes": len(outcomes),
        "risk_score":
            assessment["risk_score_0_100"],
        "traffic_light":
            assessment["traffic_light"],
        "evaluation_method":
            "primer cierre posterior al registro",
        "limitations":
            "Evaluación descriptiva. "
            "No demuestra ventaja predictiva.",
    }

    atomic_json(
        OUT / "registro_senales_resumen.json",
        report,
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
