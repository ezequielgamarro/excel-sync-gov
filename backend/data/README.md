# Datos locales del backend

> **Nota:** el endpoint `GET /api/hospitales/estadisticas` ahora lee la planilla
> **directamente desde Google Sheets**, no desde un archivo local. Este directorio
> y su montaje en Docker se conservan por compatibilidad, pero ya no son usados.

## Fuente de datos (Google Sheets)

Configurá el enlace en una de estas dos vías:

- Editar la constante `SHEET_URL` en `backend/app/api/hospitales.py`, o
- Definir la variable de entorno `HOSPITALES_SHEET_URL`.

El enlace se normaliza automáticamente a descarga `.xlsx` (p. ej.
`.../edit?usp=sharing` → `.../export?format=xlsx`). La planilla debe tener, en su
**primera pestaña**, un cuadro que empiece en la **fila 7** con columnas como
`Localidad`, `Homicidios`, `Lesiones Culposas`, `Heridos con arma de fuego`,
`Violencia familiar` y `Femicidio`.
