
"""Observatorio 6+1 - Diagnostico integrado de mercado.

Integra riesgo, macroeconomia y fortaleza relativa.
No predice precios ni genera recomendaciones operativas.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("output")

DEFENSIVE = ("XLP", "XLU", "XLV")
CYCLICAL = ("XLI", "XLF", "XLE", "IWM")
TECH = ("QQQ", "SMH", "XLK", "ASML")
CREDIT = "BAMLH0A0HYM2"
VOLATILITY = "VIXCLS"


def load(filename):
    return json.loads(
        (OUT / filename).read_text(encoding="utf-8")
    )


def save(filename, data):
    path = OUT / filename
    path.write_text(
        json.dumps(
            data, ensure_ascii=False, indent=2
        ) + "\n",
        encoding="utf-8",
    )


def group_summary(assets, symbols):
    values = [
        float(assets[s]["relative_20_pp"])
        for s in symbols if s in assets
    ]

    return {
        "expected": len(symbols),
        "available": len(values),
        "average_relative_20_pp": (
            round(sum(values) / len(values), 3)
            if len(values) == len(symbols)
            else None
        ),
        "above_spy": sum(v > 0 for v in values),
        "below_spy": sum(v < 0 for v in values),
    }


def main():
    radar = load("radar_6plus1.json")
    rotation = load("analisis_rotacion.json")
    multi = load("radar_multiactivo.json")

    date = radar["market_data"]["SPY"]["date"]

    if (
        date != rotation["reference_close_date"]
        or date != multi["reference_close_date"]
    ):
        raise SystemExit(
            "Fechas de cierre incompatibles"
        )

    if radar.get("warnings") or multi.get("warnings"):
        raise SystemExit(
            "Advertencias en los datos de entrada"
        )

    if radar["risk_assessment"]["available_signals"] != 6:
        raise SystemExit("Radar principal incompleto")

    if multi["coverage"]["valid"] != 20:
        raise SystemExit("Radar multiactivo incompleto")

    assets = {
        a["symbol"]: a
        for a in rotation["assets"]
    }

    groups = {
        "defensivos": group_summary(
            assets, DEFENSIVE
        ),
        "ciclicos": group_summary(
            assets, CYCLICAL
        ),
        "tecnologia": group_summary(
            assets, TECH
        ),
    }

    if any(
        g["average_relative_20_pp"] is None
        for g in groups.values()
    ):
        raise SystemExit("Faltan activos sectoriales")

    macro = radar["macro_latest"]
    risk = radar["risk_assessment"]
    signals = {
        s["signal"]: s["risk"]
        for s in radar["signals"]
    }

    adverse = []
    supportive = []
    uncertainty = []

    if signals.get("spy_below_ma20"):
        adverse.append(
            "SPY por debajo de su media de 20 sesiones"
        )
    else:
        supportive.append(
            "SPY sin señal adversa de media de 20 sesiones"
        )

    if signals.get("nasdaq_relative_weakness"):
        adverse.append(
            "Nasdaq presenta debilidad relativa"
        )

    if signals.get("semiconductor_relative_weakness"):
        adverse.append(
            "Semiconductores presentan debilidad relativa"
        )

    if signals.get("vix_elevated"):
        adverse.append(
            "Volatilidad elevada segun umbral del radar"
        )
    else:
        supportive.append(
            "VIX por debajo del umbral de estres"
        )

    if signals.get("high_yield_stress"):
        adverse.append(
            "Spread high yield por encima del umbral"
        )
    else:
        supportive.append(
            "Credito sin señal de estres extremo"
        )

    if signals.get("liquidity_contraction"):
        adverse.append(
            "Contraccion de la liquidez proxy"
        )
    else:
        supportive.append(
            "Sin contraccion de liquidez segun umbral"
        )

    defensives = groups["defensivos"]
    cyclicals = groups["ciclicos"]
    technology = groups["tecnologia"]

    if (
        defensives["average_relative_20_pp"]
        > cyclicals["average_relative_20_pp"]
        and technology["average_relative_20_pp"] < 0
    ):
        adverse.append(
            "Defensivos lideran a ciclicos "
            "mientras tecnologia queda rezagada"
        )

    if cyclicals["average_relative_20_pp"] > 0:
        supportive.append(
            "Grupo ciclico supera a SPY en promedio"
        )

    if rotation["persistence_status"] != "available":
        uncertainty.append(
            "No hay suficiente historial de fotografias "
            "para confirmar persistencia"
        )

    if rotation["comparison_status"] != "available":
        uncertainty.append(
            "No hay suficientes fotografias "
            "para medir cambios de liderazgo"
        )

    uncertainty.append(
        "Las fechas de observacion macro no equivalen "
        "necesariamente a fechas de publicacion"
    )
    uncertainty.append(
        "Los grupos sectoriales son cestas equiponderadas "
        "de ETF seleccionados, no indices oficiales"
    )
    uncertainty.append(
        "Los indicadores comparten informacion y "
        "no deben contarse como pruebas independientes"
    )

    report = {
        "schema_version": 1,
        "generated_at_utc":
            datetime.now(timezone.utc).isoformat(),
        "reference_close_date": date,
        "risk_score_existing":
            risk["risk_score_0_100"],
        "traffic_light_existing":
            risk["traffic_light"],
        "groups": groups,
        "macro_observations": {
            CREDIT: macro.get(CREDIT),
            VOLATILITY: macro.get(VOLATILITY),
            "liquidity_proxy":
                radar.get("liquidity_proxy"),
        },
        "evidence": {
            "adverse": adverse,
            "supportive": supportive,
            "uncertainties": uncertainty,
        },
        "diagnosis":
            "evidencia_mixta_requiere_confirmacion",
        "operational_status":
            "sin_senal_operativa_validada",
        "limitations": [
            "No es una probabilidad de caida.",
            "No modifica el semaforo 6+1.",
            "No suma indicadores correlacionados.",
            "No demuestra flujos institucionales.",
            "No genera operaciones ni objetivos de precio.",
        ],
    }

    save("diagnostico_mercado.json", report)

    lines = [
        "# Diagnostico integrado 6+1",
        "",
        f"Cierre de referencia: {date}",
        f"Semaforo original: {risk['traffic_light']}",
        f"Riesgo original: {risk['risk_score_0_100']}/100",
        "",
        "## Grupos sectoriales",
    ]

    for name, group in groups.items():
        lines.append(
            f"- {name}: "
            f"{group['average_relative_20_pp']:+.2f} pp "
            "frente a SPY (media equiponderada)"
        )

    for heading, items in (
        ("Evidencias adversas", adverse),
        ("Evidencias favorables", supportive),
        ("Limitaciones e incertidumbre", uncertainty),
    ):
        lines.extend(["", f"## {heading}"])
        lines.extend(f"- {item}" for item in items)

    lines.extend([
        "",
        "## Conclusion",
        "Evidencia mixta. No hay una señal "
        "operativa validada.",
    ])

    (OUT / "diagnostico_mercado.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        f"Diagnostico integrado generado: {date}"
    )


if __name__ == "__main__":
    main()
  
