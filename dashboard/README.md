# Dashboard (React)

El dashboard es una **SPA de solo lectura** servida desde Cloudflare Pages que consume **Supabase** directamente mediante `supabase-js` (datos + autenticación). Renderiza los visuales (KPIs con variación, regional de barras horizontales, turnos operativos, ranking Top 5 y estadísticas) con un contrato visual táctico de alto contraste en modo oscuro para salas de operaciones.

**Stack:** React 18 · Vite · Tailwind CSS · Recharts · `@supabase/supabase-js` · SheetJS (XLSX en cliente) · Cloudflare Pages.

## Arquitectura

- **Datos:** lectura/escritura de la tabla `intervenciones_diarias` y agregados vía `supabase-js` (PostgREST). No hay backend propio ni `REST`/`WSS` intermedios.
- **Autenticación:** **Supabase Auth** nativa (email/contraseña). La sesión la gestiona el cliente y la autorización efectiva la aplica **RLS** en Supabase (el cliente no decide permisos).
- **Exportación:** el `.xlsx` del reporte se genera **en el navegador** con SheetJS a partir de las filas leídas de Supabase.
- **Estado de conexión:** el badge muestra de forma estática **EN VIVO**; no hay canal WSS ni polling de cold start.
- **Configuración no secreta:** `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` (clave pública `anon`, segura con RLS activo). No hay secretos en el bundle.

Responsabilidades principales: aplicar filtros de fecha/unidad, mantener el contrato visual y no contener secretos ni decidir autorización.
