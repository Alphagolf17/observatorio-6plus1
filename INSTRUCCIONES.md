# Observatorio 6+1 — fase 1

Actualización parcial: sustituir `collector.py` y `radar.py` en la raíz del repositorio. Sustituir el archivo YAML **existente** de `.github/workflows/` por el contenido de `observatorio.yml`; no añadir un segundo workflow si ya hay uno.

Mantener intactos `guardar_historico.py`, `backtest_6plus1.py`, `validacion_6plus1.py`, `historico/` y `historico_inicial/`.

## Qué cambia

- El recopilador elimina **solo los CSV temporales esperados de `output/`** antes de descargar, evitando reutilizar series de una ejecución anterior. Nunca elimina `historico/`.
- La ejecución falla si falta alguna de las cinco series de mercado o alguna de las ocho series FRED; el informe `output/report.json` registra errores.
- El radar sincroniza fechas para SPY, QQQ y SMH, calcula fortaleza relativa sobre las mismas 21 sesiones comunes y bloquea el semáforo cuando falta alguna de sus seis señales.
- El proxy Fed se mantiene como **descriptivo**, no como señal histórica apta para backtest: sus fechas son de observación, no necesariamente de publicación.
- GitHub conserva el histórico solo tras ejecución correcta, y sube artefactos incluso ante errores.

## Advertencias

- Las cuotas de Alpha Vantage pueden hacer fallar la recopilación completa; **no** significa que los datos históricos estén perdidos. Se conservarán en `historico/` si ya estaban versionados.
- `historico_inicial/` continúa separado del histórico incremental; no se ha cambiado el backtest ni la validación.
- Los cálculos de SPY MA20 ahora usan sesiones comunes SPY/QQQ/SMH para garantizar sincronización. En condiciones normales las fechas coinciden.
- No se ha cambiado el horario del cron ni se ha añadido una descarga inicial de diez años.
- Para que el histórico persista, `historico/` debe poder subirse al repositorio (no estar ignorado por `.gitignore`) y GitHub Actions debe tener permiso de escritura.
- Si la API devuelve fallos transitorios, el workflow se detiene sin actualizar el histórico; es intencional para no emitir señales engañosas.

## Verificación local sin credenciales

`python -m py_compile collector.py radar.py`

Para ejecutar el workflow real: GitHub → Actions → Observatorio 6+1 → Run workflow. Comprobar el estado de cada paso, `output/report.json`, `output/radar_6plus1.json` y que `historico/` se haya actualizado.
