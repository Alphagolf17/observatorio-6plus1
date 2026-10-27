# Observatorio 6+1 — versión 1

Recopila cinco ETF/acciones con Alpha Vantage y ocho series macroeconómicas FRED. No realiza operaciones ni accede a cuentas de inversión.

## Configuración
1. Crear un repositorio **privado** en GitHub.
2. Subir `collector.py` y `.github/workflows/observatorio.yml` conservando las rutas.
3. En Settings → Secrets and variables → Actions → New repository secret, crear:
   - `ALPHAVANTAGE_API_KEY`
   - `FRED_API_KEY`
4. Actions → Observatorio 6+1 → Run workflow.
5. Al terminar, abrir la ejecución y descargar el artefacto `observatorio-6plus1`.

Se programa de lunes a viernes a las 23:37 UTC. GitHub puede retrasar o cancelar alguna ejecución. Los CSV se descargan como artefactos con retención de 30 días: **no son almacenamiento histórico permanente**. El histórico de mercado gratuito contiene como máximo unas 100 sesiones y la recolección diaria no amplía el rango si no se guarda fuera de los artefactos. Para mantener años de historia, incorporar almacenamiento persistente posteriormente.

Las cotizaciones son de cierre, no intradía ni necesariamente en EUR. Los datos FRED pueden estar revisados y publicarse con retraso; los CSV no sirven por sí solos para backtests sin sesgo de anticipación.

Si una API devuelve límites o errores, el programa deja una advertencia en `report.json`. No escribas claves en archivos, mensajes ni URLs compartidas.
