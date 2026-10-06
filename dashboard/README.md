# Dashboard (React)

El dashboard es una **SPA de solo lectura** servida desde Cloudflare Pages que consume el backend vía cold start REST y se suscribe al canal WSS para actualizarse en tiempo real. Renderiza los 7 visuales (4 KPIs con variación, regional de barras horizontales, turnos operativos y ranking Top 5) con un contrato visual táctico de alto contraste en modo oscuro para salas de operaciones.

**Stack:** React 18 · Vite · Tailwind CSS · Recharts · Cloudflare Pages.

Responsabilidades principales: aplicar instantáneas de forma idempotente (`seq` monotónico), declarar el estado de conexión/frescura (EN VIVO, RECONECTANDO, DEGRADADO·POLLING, SIN CONEXIÓN, DATOS DESACTUALIZADOS), degradar a polling si el WSS falla, autenticarse con login nativo (usuario+contraseña) y no contener secretos ni decidir autorización (el backend ya filtró por capacidad). Se completa en las tareas F7.
