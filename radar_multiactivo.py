
"""Observatorio 6+1: radar multiactivo sincronizado.

Usa exclusivamente cierres hasta la fecha del radar principal.
Conserva una fotografia diaria de la clasificacion.
No genera operaciones de inversion.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ASSETS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Small caps EEUU",
    "SMH": "Semiconductores",
    "XLK": "Tecnologia",
    "XLF": "Finanzas",
    "XLE": "Energia",
    "XLI": "Industriales",
    "XLV": "Salud",
    "XLP": "Consumo defensivo",
    "XLU": "Utilities",
    "CIBR": "Ciberseguridad",
    "COPX": "Mineras de cobre",
    "GLD": "Oro ETF",
    "BTC-USD": "Bitcoin USD",
    "EWT": "Taiwan ETF",
    "EWY": "Corea del Sur ETF",
    "FXI": "China ETF",
    "VGK": "Europa ETF",
    "ASML": "ASML ADR",
}

WINDOWS = (5, 20, 60)
OUT = Path("output")
HISTORY = Path("historico_multiactivo")


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def get_reference_date():
    path = OUT / "radar_6plus1.json"
    radar = json.loads(path.read_text(encoding="utf-8"))

    market = radar["market_data"]
    required = ("SPY", "QQQ", "SMH")
    dates = [market[s]["date"] for s in required]

    if len(set(dates)) != 1:
        raise ValueError("Radar principal sin fechas alineadas")

    reference = date.fromisoformat(dates[0])
    today = datetime.now(timezone.utc).date()
    age = (today - reference).days

    if not 0 <= age <= 5:
        raise ValueError("Fecha del radar principal no vigente")

    return reference


def download_close(ticker, reference):
    data = yf.download(
        ticker,
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
        timeout=20,
    )

    if data.empty:
        raise ValueError("Descarga vacia")

    close = data["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = pd.to_numeric(
        close, errors="coerce"
    ).dropna()

    close = close[close > 0].sort_index()
    close = close[
        ~close.index.duplicated(keep="last")
    ]

    # Normalizar las fechas, sin interpretar horas intradia.
    close.index = pd.to_datetime(close.index).normalize()

    # Eliminar todos los precios posteriores al cierre
    # utilizado por el radar principal.
    cutoff = pd.Timestamp(reference)
    close = close.loc[close.index <= cutoff]

    if close.empty:
        raise ValueError("No hay precios anteriores al corte")

    if close.index[-1].date() != reference:
        raise ValueError(
            "No existe cierre en fecha de referencia: "
            + str(close.index[-1].date())
        )

    if len(close) < 65:
        raise ValueError(
            f"Historico insuficiente: {len(close)} sesiones"
        )

    return close


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    reference = get_reference_date()

    histories = {}
    warnings = []

    for ticker in ASSETS:
        try:
            histories[ticker] = download_close(
                ticker, reference
            )
        except Exception as exc:
            warnings.append(
                f"{ticker}: {type(exc).__name__}: {exc}"
            )

    if "SPY" not in histories:
        raise SystemExit(
            "SPY no disponible para la fecha de referencia"
        )

    benchmark = histories["SPY"]
    results = []

    for ticker, close in histories.items():
        aligned = pd.concat(
            [
                close.rename("asset"),
                benchmark.rename("spy"),
            ],
            axis=1,
        ).dropna().sort_index()

        if len(aligned) < 65:
            warnings.append(
                f"{ticker}: menos de 65 sesiones comunes"
            )
            continue

        if aligned.index[-1].date() != reference:
            warnings.append(
                f"{ticker}: fecha final no sincronizada"
            )
            continue

        returns = {}
        relative = {}

        for n in WINDOWS:
            asset_return = (
                aligned["asset"].iloc[-1]
                / aligned["asset"].iloc[-1 - n]
                - 1
            ) * 100

            spy_return = (
                aligned["spy"].iloc[-1]
                / aligned["spy"].iloc[-1 - n]
                - 1
            ) * 100

            returns[str(n)] = round(
                float(asset_return), 3
            )
            relative[str(n)] = round(
                float(asset_return - spy_return), 3
            )

        results.append({
            "symbol": ticker,
            "name": ASSETS[ticker],
            "date": reference.isoformat(),
            "close_usd_or_native": round(
                float(aligned["asset"].iloc[-1]), 4
            ),
            "sessions": len(aligned),
            "return_pct": returns,
            "relative_vs_spy_pp": relative,
        })

    results.sort(
        key=lambda x: x["relative_vs_spy_pp"]["20"],
        reverse=True,
    )

    coverage = {
        "expected": len(ASSETS),
        "valid": len(results),
    }

    report = {
        "schema_version": 2,
        "generated_at_utc": now.isoformat(),
        "reference_close_date": reference.isoformat(),
        "benchmark": "SPY",
        "price_basis": "Yahoo Finance auto_adjust=True",
        "coverage": coverage,
        "assets": results,
        "warnings": warnings,
        "limitations": [
            "Solo se utilizan precios hasta la fecha de referencia.",
            "La fecha de referencia procede del radar principal.",
            "No se mezclan sesiones bursatiles abiertas.",
            "Bitcoin se alinea con las sesiones de SPY.",
            "Los retornos usan precios ajustados de Yahoo Finance.",
            "Los ajustes historicos pueden revisarse posteriormente.",
            "Fortaleza relativa no demuestra flujos institucionales.",
            "Los resultados no son senales de compra o venta.",
        ],
    }

    save_json(OUT / "radar_multiactivo.json", report)

    lines = [
        "# Radar multiactivo 6+1",
        "",
        f"Fecha de cierre: {reference.isoformat()}",
        f"Cobertura: {len(results)}/{len(ASSETS)}",
        "",
        "| Activo | 20 sesiones | Relativo SPY (pp) |",
        "|---|---:|---:|",
    ]

    for asset in results:
        lines.append(
            f"| {asset['symbol']} | "
            f"{asset['return_pct']['20']:+.2f}% | "
            f"{asset['relative_vs_spy_pp']['20']:+.2f} |"
        )

    if warnings:
        lines.extend(["", "## Advertencias"])
        lines.extend(f"- {w}" for w in warnings)

    (OUT / "radar_multiactivo.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    if len(results) < 15:
        raise SystemExit(
            f"Cobertura insuficiente: {len(results)}/20"
        )

    # Primera fotografia valida de cada fecha.
    # Las ejecuciones posteriores no la sobrescriben.
    snapshot = (
        HISTORY
        / f"clasificacion_{reference.isoformat()}.json"
    )

    if not snapshot.exists():
        save_json(snapshot, report)
        print("Nueva fotografia historica creada")
    else:
        print("Fotografia existente conservada")

    print(
        f"Radar multiactivo sincronizado: "
        f"{len(results)}/{len(ASSETS)} activos, "
        f"cierre {reference.isoformat()}"
    )


if __name__ == "__main__":
    main()
