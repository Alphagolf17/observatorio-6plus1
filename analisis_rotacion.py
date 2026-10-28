
"""Observatorio 6+1 - Analisis de rotacion multiactivo.

Compara fotografias historicas reales.
No inventa observaciones ni genera ordenes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY = Path("historico_multiactivo")
OUT = Path("output")

MIN_COVERAGE = 15
PERSISTENCE_DAYS = 3
LEADERS = 5
LAGGARDS = 5


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_snapshots():
    snapshots = {}

    for path in sorted(
        HISTORY.glob("clasificacion_????-??-??.json")
    ):
        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        day = data["reference_close_date"]

        if path.stem != f"clasificacion_{day}":
            raise ValueError(
                f"Fecha inconsistente: {path}"
            )

        if data.get("benchmark") != "SPY":
            raise ValueError(
                f"Referencia incorrecta: {path}"
            )

        assets = data.get("assets", [])

        if len(assets) < MIN_COVERAGE:
            raise ValueError(
                f"Cobertura insuficiente: {day}"
            )

        symbols = [a["symbol"] for a in assets]

        if len(symbols) != len(set(symbols)):
            raise ValueError(
                f"Activos duplicados: {day}"
            )

        if any(a["date"] != day for a in assets):
            raise ValueError(
                f"Fechas desalineadas: {day}"
            )

        snapshots[day] = {
            a["symbol"]: a for a in assets
        }

    return snapshots


def ranking(snapshot):
    ordered = sorted(
        snapshot.values(),
        key=lambda a: (
            -float(
                a["relative_vs_spy_pp"]["20"]
            ),
            a["symbol"],
        ),
    )

    return {
        a["symbol"]: i + 1
        for i, a in enumerate(ordered)
    }


def classify(asset):
    rel = asset["relative_vs_spy_pp"]

    r5 = float(rel["5"])
    r20 = float(rel["20"])
    r60 = float(rel["60"])

    if r5 > 0 and r20 > 0 and r60 > 0:
        return "fortaleza_multihorizonte"

    if r5 < 0 and r20 < 0 and r60 < 0:
        return "debilidad_multihorizonte"

    if r5 > 0 and r20 < 0:
        return "recuperacion_incipiente"

    if r5 < 0 and r20 > 0:
        return "perdida_impulso"

    return "mixto"


def main():
    snapshots = load_snapshots()

    if not snapshots:
        raise SystemExit(
            "No hay fotografias multiactivo"
        )

    dates = sorted(snapshots)
    latest_date = dates[-1]
    latest = snapshots[latest_date]
    current_ranks = ranking(latest)

    previous_date = (
        dates[-2] if len(dates) >= 2 else None
    )

    previous = (
        snapshots[previous_date]
        if previous_date else None
    )

    previous_ranks = (
        ranking(previous) if previous else {}
    )

    results = []

    for symbol, asset in latest.items():
        current_rank = current_ranks[symbol]
        previous_rank = previous_ranks.get(symbol)

        rank_change = (
            previous_rank - current_rank
            if previous_rank is not None
            else None
        )

        # Persistencia basada exclusivamente en
        # fotografias realmente almacenadas.
        streak = 0

        for day in reversed(dates):
            observation = snapshots[day].get(symbol)

            if observation is None:
                break

            relative20 = float(
                observation[
                    "relative_vs_spy_pp"
                ]["20"]
            )

            if relative20 > 0:
                if streak < 0:
                    break
                streak += 1
            elif relative20 < 0:
                if streak > 0:
                    break
                streak -= 1
            else:
                break

        persistent = (
            len(dates) >= PERSISTENCE_DAYS
            and abs(streak) >= PERSISTENCE_DAYS
        )

        results.append({
            "symbol": symbol,
            "name": asset["name"],
            "rank_20": current_rank,
            "previous_rank_20": previous_rank,
            "rank_change": rank_change,
            "relative_5_pp":
                asset["relative_vs_spy_pp"]["5"],
            "relative_20_pp":
                asset["relative_vs_spy_pp"]["20"],
            "relative_60_pp":
                asset["relative_vs_spy_pp"]["60"],
            "classification": classify(asset),
            "consecutive_observations":
                abs(streak),
            "persistent_direction": (
                "liderazgo_relativo"
                if persistent and streak > 0
                else "debilidad_relativa"
                if persistent and streak < 0
                else None
            ),
        })

    results.sort(key=lambda a: a["rank_20"])

    enough_for_changes = len(dates) >= 2
    enough_for_persistence = (
        len(dates) >= PERSISTENCE_DAYS
    )

    report = {
        "schema_version": 1,
        "generated_at_utc":
            datetime.now(timezone.utc).isoformat(),
        "reference_close_date": latest_date,
        "previous_close_date": previous_date,
        "snapshots_available": len(dates),
        "comparison_status": (
            "available"
            if enough_for_changes
            else "insufficient_history"
        ),
        "persistence_status": (
            "available"
            if enough_for_persistence
            else "insufficient_history"
        ),
        "leaders": results[:LEADERS],
        "laggards": results[-LAGGARDS:],
        "assets": results,
        "limitations": [
            "Los cambios de ranking requieren dos fotografias.",
            "La persistencia requiere al menos tres fotografias.",
            "Las observaciones no necesariamente son consecutivas en calendario bursatil.",
            "Persistencia significa signo relativo repetido, no rentabilidad futura.",
            "Los periodos de 20 sesiones se solapan.",
            "No se infieren flujos institucionales.",
            "No genera senales de compra ni venta.",
        ],
    }

    save_json(
        OUT / "analisis_rotacion.json",
        report,
    )

    lines = [
        "# Analisis de rotacion 6+1",
        "",
        f"Ultimo cierre: {latest_date}",
        f"Fotografias disponibles: {len(dates)}",
        "",
        "| Activo | Puesto | Cambio | Relativo 20d | Estado |",
        "|---|---:|---:|---:|---|",
    ]

    for a in results:
        change = (
            f"{a['rank_change']:+d}"
            if a["rank_change"] is not None
            else "N/D"
        )

        lines.append(
            f"| {a['symbol']} | "
            f"{a['rank_20']} | "
            f"{change} | "
            f"{a['relative_20_pp']:+.2f} pp | "
            f"{a['classification']} |"
        )

    if not enough_for_changes:
        lines.extend([
            "",
            "Cambios de ranking: datos insuficientes.",
        ])

    if not enough_for_persistence:
        lines.extend([
            "",
            "Persistencia: datos insuficientes.",
        ])

    (OUT / "analisis_rotacion.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        f"Analisis de rotacion generado: "
        f"{len(results)} activos; "
        f"{len(dates)} fotografias"
    )


if __name__ == "__main__":
    main()
      
