
"""Radar multiactivo 6+1, independiente del radar principal.
Requiere: pip install yfinance pandas
Datos de Yahoo Finance: orientativos, sujetos a revisiones y retrasos.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ASSETS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Small caps EEUU",
    "SMH": "Semiconductores",
    "XLK": "Tecnologia",
    "XLF": "Bancos y finanzas",
    "XLE": "Energia",
    "XLI": "Industriales",
    "XLV": "Salud",
    "XLP": "Consumo defensivo",
    "XLU": "Utilities",
    "CIBR": "Ciberseguridad",
    "COPX": "Mineras de cobre",
    "GLD": "Oro (ETF)",
    "BTC-USD": "Bitcoin (USD)",
    "EWT": "Taiwan (ETF)",
    "EWY": "Corea del Sur (ETF)",
    "FXI": "China grandes empresas",
    "VGK": "Europa (ETF)",
    "ASML": "ASML (ADR EEUU)",
}

WINDOWS = (5, 20, 60)
OUT = Path("output")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    results = []
    warnings = []
    histories = {}

    for ticker, name in ASSETS.items():
        try:
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
                raise ValueError("Sin datos")

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

            if len(close) < 65:
                raise ValueError(
                    f"Solo {len(close)} sesiones"
                )

            latest = close.index[-1].date()

            if (now.date() - latest).days > 7:
                raise ValueError(
                    f"Datos antiguos: {latest}"
                )

            histories[ticker] = close

        except Exception as exc:
            warnings.append(
                f"{ticker}: {type(exc).__name__}: {exc}"
            )

    if "SPY" not in histories:
        raise SystemExit(
            "Falta SPY: no se puede calcular fortaleza relativa"
        )

    benchmark = histories["SPY"]

    for ticker, close in histories.items():
        # Alinear por fechas comunes, incluido Bitcoin.
        aligned = pd.concat(
            [
                close.rename("asset"),
                benchmark.rename("spy"),
            ],
            axis=1,
        ).dropna()

        if len(aligned) < 65:
            warnings.append(
                f"{ticker}: insuficientes fechas comunes"
            )
            continue

        # No utilizar cierres posteriores al último SPY.
        aligned = aligned.loc[
            aligned.index <= benchmark.index[-1]
        ]

        if len(aligned) < 65:
            warnings.append(
                f"{ticker}: histórico alineado insuficiente"
            )
            continue

        lag = (
            benchmark.index[-1].date()
            - aligned.index[-1].date()
        ).days

        if lag > 4:
            warnings.append(
                f"{ticker}: última sesión demasiado antigua"
            )
            continue

        returns = {}
        relative = {}

        for n in WINDOWS:
            a = (
                float(aligned["asset"].iloc[-1])
                / float(aligned["asset"].iloc[-1 - n])
                - 1
            ) * 100

            b = (
                float(aligned["spy"].iloc[-1])
                / float(aligned["spy"].iloc[-1 - n])
                - 1
            ) * 100

            returns[str(n)] = round(a, 3)
            relative[str(n)] = round(a - b, 3)

        results.append({
            "symbol": ticker,
            "name": ASSETS[ticker],
            "date": aligned.index[-1].date().isoformat(),
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

    report = {
        "generated_at_utc": now.isoformat(),
        "benchmark": "SPY",
        "price_basis": "Yahoo Finance auto_adjust=True",
        "coverage": {
            "expected": len(ASSETS),
            "valid": len(results),
        },
        "assets": results,
        "warnings": warnings,
        "limitations": [
            "Fortaleza relativa no equivale a flujos de capital demostrados.",
            "Bitcoin se alinea con sesiones bursátiles de SPY.",
            "GLD es un ETF de oro, no el precio spot.",
            "Los ETF internacionales cotizan en EEUU y están en USD.",
            "Datos de terceros sujetos a retrasos y revisiones.",
            "No genera órdenes de inversión.",
        ],
    }

    (OUT / "radar_multiactivo.json").write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Radar multiactivo 6+1",
        "",
        f"Cobertura: {len(results)}/{len(ASSETS)}",
        "",
        "| Activo | 20 sesiones | Relativo a SPY (pp) |",
        "|---|---:|---:|",
    ]

    for a in results:
        lines.append(
            f"| {a['symbol']} | "
            f"{a['return_pct']['20']:+.2f}% | "
            f"{a['relative_vs_spy_pp']['20']:+.2f} |"
        )

    if warnings:
        lines += ["", "## Advertencias"]
        lines += [f"- {w}" for w in warnings]

    (OUT / "radar_multiactivo.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        f"Radar multiactivo: "
        f"{len(results)}/{len(ASSETS)} activos válidos"
    )

    if len(results) < 15:
        raise SystemExit(
            "Cobertura insuficiente: menos de 15 activos"
        )


if __name__ == "__main__":
    main()
  
