# SPEC-001 — Sistema de Sincronización en Tiempo Real "Google Sheets-to-Web" y Dashboard de Monitoreo

**Enfoque:** Zero Trust (Arquitectura de Seguridad Gubernamental)
**Estado:** Especificación aprobada; `plan.md` y `tasks.md` generados (Fase 3 — SDD).
**Versión del documento:** 0.2 (borrador para revisión — migración del origen local a Google Sheets + Apps Script)
**Stack:** Google Sheets (fuente de datos, cuenta Gmail estándar) + Google Apps Script (trigger onEdit/onChange + webhook firmado HMAC) · FastAPI (REST + WebSockets + **auth nativa JWT usuario/contraseña, sin MFA**) · React 18 + Vite + Tailwind CSS + Recharts (Cloudflare Pages) · PostgreSQL (historiales + usuarios locales) · Redis (pub/sub + presencia)

---

## Índice

1. Contexto y objetivos
2. Enfoque Zero Trust
3. Arquitectura de alto nivel
4. Alcance / No-alcance
5. Requisitos funcionales (EARS)
6. Requisitos no funcionales (RNF)
7. Modelo de datos
8. Modelo de seguridad y amenazas
9. Gestión de claves y secretos
10. Contrato de API
11. Contrato visual / Especificación de UI
12. Criterios de aceptación
13. Métricas y límites
14. Riesgos técnicos y decisiones abiertas
15. Trazabilidad
- Anexo A — Glosario
- Anexo B — Catálogo de variables de Tailwind/CSS

---

## 1. Contexto y objetivos

### 1.1 Problema

El sistema institucional **SIFCOP** (fuente de los indicadores) publica sus cifras en un documento de Google Sheets que es actualizado manualmente por analistas. Las unidades regionales de referencia son **Capital, Sur, Este, Oeste, Norte** y el detalle granularity está en el ranking de **comisarías/dependencias**. El consumo de esa información se produce en una **sala de operaciones de seguridad pública** con pantallas de monitoreo continuo, donde una cifra desactualizada o manipulada tiene consecuencias operativas directas.

> **Nota de origen (cuenta estándar):** el documento de Google Sheets vive en una **cuenta Gmail estándar** (p. ej. la cuenta gratuita del comisario), **no** en un dominio de Google Workspace ni en un correo institucional. El webhook, la reconciliación por *service account* de solo lectura y los permisos se configuran contra esa cuenta estándar; el sistema **no** depende de APIs ni permisos exclusivos de Google Workspace.

Este modelo manual genera:

- **Retraso en la publicación**: decenas de minutos u horas entre la edición guardada del documento y la disponibilidad del dato en la sala de operaciones.
- **Punto único de fallo humano**: el depender de que un analista "se acuerde" de publicar produce huecos y cifras contradictorias entre pantallas.
- **Sin trazabilidad**: no existe registro fiable de *quién* cambió *qué* y *cuándo* ni de *qué cifra vio cada operador*.
- **Superficie de exposición**: documentos de Google Sheets (con datos sensibles) compartidos por canales no gobernados, enlaces públicos y exportaciones no controladas.
- **Riesgo de manipulación**: cualquier cuenta con acceso de escritura al documento puede alterar cifras oficiales sin detección.
- **Auditoría imposible**: las actualizaciones no son reproducibles ni atribuibles.
- **Auditoría de consumo**: no se sabe qué indicadores fueron consumidos por qué operador, lo cual es inaceptable en un dominio de seguridad pública.

### 1.2 Objetivo general

Construir un sistema que **detecte automáticamente** los cambios guardados en un documento de Google Sheets, los **transmita de forma segura y firmados** a un backend bajo **verificación constante de identidad**, los **archive** como historiales consultables, y los **redistribuya en tiempo real** a todos los dashboards web autenticados y autorizados, con un **contrato visual táctico** de alto contraste diseñado para lectura sostenida en pantallas de sala de operaciones.

### 1.3 Objetivos específicos

| ID | Objetivo |
|----|----------|
| OBJ-1 | Convertir la edición guardada en Google Sheets en un evento de distribución en tiempo real con **p95 ≤ 1,5 s** desde el evento de cambio (trigger de Apps Script) hasta el refresco visual. |
| OBJ-2 | Garantir **confidencialidad e integridad** del dato en tránsito (doble capa: TLS 1.3 + AES-256 a nivel aplicación) y en reposo. |
| OBJ-3 | Impedir la **suplantación del origen** y del operador mediante verificación de identidad en cada salto (firma HMAC-SHA256 del webhook con secreto compartido, **JWT nativo** emitido por el backend tras login usuario/contraseña). |
| OBJ-4 | Aplicar **mínimo privilegio y mínimo privilegio de datos**: el navegador solo recibe agregados que su rol tiene permitidos; nunca datos crudos ni filas con PII. |
| OBJ-5 | Ofrecer **trazabilidad total**: quién envió qué, quién consultó qué, con resultado y marca de tiempo verificable. |
| OBJ-6 | Proveer un **dashboard de sala de operaciones** legible 24/7: 4 KPIs con variación, distribución regional, tendencia por turno operativo y ranking Top 5. |
| OBJ-7 | Mantener el servicio operativo con **degradación controlada**: si el WSS cae, el dashboard degrada a polling y lo señala explícitamente (nunca muestra datos caducados como si fueran frescos). |
| OBJ-8 | Resistir replay, interceptación, inyección de contenido vía celdas de Google Sheets, DoS y exfiltración. |

### 1.4 Usuarios y actores

| Actor | Descripción | Necesidad principal |
|-------|-------------|---------------------|
| **Operador de sala de monitoreo** (`viewer`) | Personal que vigila el panel de forma continua durante turnos de hasta 12 h. | Lectura inmediata del estado, sin ruido, sin fricción de sesión. |
| **Mando / Supervisor** (`supervisor`) | Responsable de turno; analiza tendencia, histórico y desviaciones. | Profundizar en histórico y comparar turnos/unidades. |
| **Auditor** (`auditor`) | Personal de control y auditoría interna. | Trazabilidad: qué se publicó, cuándo y quién lo consumió. |
| **Administrador de plataforma** (`platform-admin`) | Responsable técnico de la plataforma. | Gestión de secretos de webhook, claves, **usuarios locales y roles**. **No ve indicadores por defecto** (mínimo privilegio). |
| **Analista SIFCOP** | Usuario que edita el documento de Google Sheets. No interactúa con el sistema más allá de editar/guardar el documento. | Que su edición se publique sin intervención adicional. |
| **Google Sheets (SIFCOP)** | Documento de hoja de cálculo compartido que contiene los indicadores y que editan los analistas. | Ser la fuente de verdad y notificar sus cambios. |
| **Apps Script (trigger + webhook)** | Script vinculado al documento que detecta ediciones (`onEdit`/`onChange`) y notifica al backend mediante un webhook firmado. | Publicar cambios de forma segura y silenciosa. |
| **Backend FastAPI** | Servicio que verifica, valida, archiva y redistribuye. | — (componente) |
| **PostgreSQL** | Almacén de historiales y eventos de auditoría. | — (componente) |
| **Dashboard React (SPA)** | Cliente served desde Cloudflare Pages, consumida por navegador. | — (componente) |

### 1.5 Alcance del documento

Esta especificación cubre **el sistema completo "Google Sheets-to-Web"**: (a) el pipeline de ingesta firmada (Google Sheets → Apps Script → backend → distribución en tiempo real) y (b) el dashboard de monitoreo que lo visualiza. Ambos son un único sistema: el contrato de datos, el modelo de seguridad y el modelo de trazabilidad son compartidos.

### 1.6 Definiciones de alcance funcional (lo que el dashboard muestra)

Siete (7) **visuales** de primer nivel:

| ID Visual | Nombre | Tipo | Origen del dato |
|------------|--------|------|-----------------|
| VIS-01 | Total Consultas SIFCOP | Tarjeta KPI + variación | Google Sheets, celdas de totales de la hoja de resumen |
| VIS-02 | Personas Capturadas | Tarjeta KPI + variación | Google Sheets |
| VIS-03 | Vehículos Secuestrados | Tarjeta KPI + variación | Google Sheets |
| VIS-04 | Armas Secuestradas | Tarjeta KPI + variación | Google Sheets |
| VIS-05 | Intervenciones por Unidad Regional | Barras horizontales (5 categorías) | Google Sheets, agregado por unidad regional |
| VIS-06 | Incidentes por Turno Operativo | Gráfico temporal (3 turnos) | Google Sheets, agregado por turno |
| VIS-07 | Ranking de Dependencias - Top 5 | Tabla (5 filas, 4 columnas) | Google Sheets, agregado por dependencia |

---

## 2. Enfoque Zero Trust

### 2.0 Premisa de sensibilidad

**Los datos de esta aplicación son sensibles.** Las cifras agregadas que se distribuyen (tasas de consultas, capturas, secuestros de vehículos y armas, distribución territorial y ranking de dependencias) tienen **valor operativo y de inteligencia**: suficiente combinarlos, actualizarlos o filtrarlos selectivamente para derivar información sobre la capacidad y el despliegue efectivo de unidades de seguridad pública. Por tanto:

- La aplicación se clasifica internamente como **datos sensibles de dominio restringido** (equivalente a "uso interno / distribución controlada"), **no** como dato público.
- El **agregado no es dato público por ser agregado**: la granularidad mínima distribuible es el indicador de la celda agregada; no se distribuyen filas de detalle ni columnas con campos de personas.
- La exposición se trata como un **incidente de seguridad**, no como un error de disponibilidad.

### 2.1 Principios aplicados

| # | Principio | Traducción concreta en este sistema |
|---|-----------|--------------------------------------|
| P1 | **Nunca confiar, verificar siempre** | Ningún mensaje se acepta sin verificación explícita de identidad y autorización: firma `HMAC-SHA256` del webhook con secreto compartido (rotación + revocación), **JWT nativo** firmado por el backend para el operador, comprobación de capacidad (RBAC) en cada lectura y en cada conexión WSS. No se confía en la red, ni en el `Referer`, ni en el nombre del documento, ni en el contenido del payload antes de verificar. |
| P2 | **Red de confianza cero** | El origen (Apps Script) opera desde la nube del proveedor (potencialmente no confiable). Cada salto se autentica y cifra de forma independiente: Apps Script → API (TLS 1.3 + webhook firmado HMAC-SHA256), API → almacén (TLS + credenciales de servicio), API ↔ navegador (WSS con TLS 1.3 + ticket de un solo uso + JWT). Ninguna comunicación asume que el tramo anterior es íntegro. |
| P3 | **Mínimo privilegio** | El origen (Apps Script) solo puede notificar cambios de un documento declarado; el visor solo lee y no escribe; el `platform-admin` gestiona plataforma y **no** ve indicadores; el almacenamiento de historiales se cifra y se particiona por documento. Las capacidades (capabilities) son ortogonales a los roles. |
| P4 | **Defensa en profundidad** | TLS 1.3 obligatorio + **firma HMAC-SHA256 del webhook** + cifrado en reposo (PostgreSQL TDE o cifrado de volumen + cifrado de columna en historiales) + RBAC + CSP estricta + rate limiting + WAF + auditoría inmutable + validación estricta de entrada. |
| P5 | **Asumir la red comprometida** | Aunque un atacante controle la red o termine el TLS del cliente, el payload es inservible sin un `HMAC-SHA256` válido y sin el secreto compartido; aunque intercepte el WSS, los eventos van firmados y el cliente rechaza secuencias tardías/duplicadas; aunque tenga acceso de solo lectura al backend, RBAC impide escalar a datos no autorizados. |
| P6 | **El cliente no es frontera de seguridad** | El navegador es un **consumidor no confiable**: todo lo que se le entrega se valida y se autoriza en el servidor. El cliente no recibe el secreto del webhook, ni claves de descifrado de aplicación, ni credenciales de almacén. Toda decisión de autorización se toma server-side. |
| P7 | **Superficie de ataque mínima** | El origen (Apps Script) no abre puertos de escucha; solo realiza salida HTTPS al endpoint allowlisted del backend. El backend expone un conjunto mínimo y versionado de endpoints. La SPA no contiene secretos. El WSS usa **ticket de un solo uso**, no el token de sesión en la URL. |
| P8 | **Trazabilidad total** | Cada acción produce un evento de auditoría: registro/rotación de secreto de webhook, envío rechazado, instantánea aceptada, conexión WSS abierta/cerrada, lectura de dashboard, consulta de histórico, exportación, rotación de clave, cambio de rol. Registro estructurado, append-only, con `correlation_id`. |
| P9 | **Fallar cerrado (fail-closed)** | Ante cualquier duda de identidad, integridad o autorización, el sistema **rechaza** (401/403/4003) y registra el intento. Ante duda sobre frescura del dato, el dashboard **lo declara** (banner "DATOS DESACTUALIZADOS"), nunca lo presenta como actual. |
| P10 | **Identidad de servicio** | El backend accede al almacén con una identidad propia de servicio, con permisos reducidos (SELECT sobre vistas materializadas; INSERT-only sobre auditoría), nunca con credenciales de administrador ni con el secreto del webhook. |

### 2.2 Aplicación a cada pieza

#### 2.2.1 Verificación del origen (Google Sheets / Apps Script)

- El origen se configura con un **secreto compartido de webhook** generado por el `platform-admin` en el backend. El secreto se guarda en Apps Script en **`Script Properties`** (almacén de propiedades del script, cifrado en reposo por Google) y **nunca** se escribe en el código versionado ni en el repositorio. El backend conserva el **material del secreto** en el secret manager y en la base de datos solo guarda **metadata** (`webhook_id`, `key_id`, estado, fechas) para rotación y revocación.
- Cada `POST /ingest/webhook` incluye: `X-Webhook-Id`, `X-Webhook-Key-Id` (versión del secreto usada), `X-Webhook-Nonce` (128 bits aleatorios), `X-Webhook-Timestamp` (ISO-8601 UTC), `X-Webhook-Version` y `X-Webhook-Signature: sha256=<hex>` (HMAC-SHA256 sobre el cuerpo canónico y los metadatos).
- El backend verifica, **en este orden y antes de deserializar el cuerpo**: (1) presencia y formato de las cabeceras; (2) `webhook_id` existe, activo y no revocado; (3) `key_id` conocido y vigente; (4) **firma HMAC-SHA256 válida** por comparación en tiempo constante; (5) desalineación temporal dentro de ±300 s; (6) `X-Webhook-Nonce` no visto en la ventana de replay (cache de 600 s); (7) esquema y rangos del payload.
- Un origen desconocido, revocado, con reloj desviado o con firma inválida recibe `401`/`403` y **se audita** el intento. Apps Script registra el fallo en su log de ejecución y rota/avisa al administrador; el endpoint **nunca** se convierte en una vía de publicación para terceros.
- El secreto es **por origen/despliegue** (un documento = un webhook), de modo que la revocación es individual y la rotación con solape de **24 h** no obliga a reconfigurar toda la plataforma.

#### 2.2.2 Autenticación del operador del dashboard

- El login es **nativo y local al backend** (FastAPI): el operador se autentica con **usuario y contraseña**. No hay proveedor de identidad externo (Keycloak/SSO) ni MFA/step-up. El backend verifica la credencial contra el almacén local de usuarios y **rechaza** credenciales inválidas o cuentas deshabilitadas.
- **Almacenamiento de contraseñas**: hash fuerte con **Argon2id** (sal por usuario y parámetros de coste configurables); nunca se almacena ni se registra una contraseña en claro. **Bloqueo por intentos** (p. ej. 5 fallos → bloqueo temporal con backoff progresivo) y rate limit de login por IP/usuario (RNF-12.e). Política mínima de contraseñas (longitud y complejidad) documentada.
- **Tokens**: el login emite un **JWT de acceso de vida corta (15 min)** firmado por el backend (`HS256` con `JWT_SIGNING_KEY` rotativa, o firma asimétrica equivalente) con `sub`, capacidades y `aud=dashboard-api`; y un **refresh token rotativo** con detección de reutilización (reutilizar un refresh token revoca la cadena completa). No hay refresh contra un IdP externo.
- La SPA se sirve desde Cloudflare Pages; la API vive en **otro origen**, por lo que no hay problema de same-origin, pero sí de **CORS**: allowlist exacta de orígenes, `Access-Control-Allow-Credentials` solo con esa allowlist, `Vary: Origin`.
- **Sesiones de sala 24/7**: el requisito de *nunca desconectar* se resuelve con **sin expiración mientras el navegador esté abierto**. El **refresh token es rotativo e indefinido mientras hay actividad** (latido de WSS o heartbeat de aplicación cada 15 s). **Sin MFA y sin step-up**; las acciones sensibles (gestión de secretos de webhook/usuarios, exportar, replay) exigen la **capacidad correspondiente y se auditan**. **Se elimina el bloqueo a los 30 min de inactividad para la visualización en vivo**.
- Cada evento WSS y cada lectura REST se autoriza con el token vigente (el WSS se abre con ticket de un solo uso que encarna el `sub` + capacidades, con TTL de 60 s).

#### 2.2.3 Autorización / permisos por rol (qué indicador ve cada rol)

La autorización se modela como **capacidades ortogonales**, no como roles cerrados. Un rol es un conjunto de capacidades; una capacidad es el único objeto que el backend comprueba.

| Capacidad | `viewer` (Operador) | `supervisor` (Mando) | `auditor` | `platform-admin` |
|---|---|---|---|---|
| `dash.view.live` — KPIs, regional, turnos, ranking en vivo | Sí | Sí | **No** | **No** |
| `dash.view.history` — histórico hasta 90 días | No | Sí | Sí | No |
| `dash.export.csv` — exportación de agregados | No | Sí | Sí | No |
| `audit.view` — eventos de auditoría | No | No | Sí | No |
| `platform.manage_webhook` — registrar/rotar/revocar el secreto del webhook de Google Sheets | No | No | No | Sí |
| `platform.manage_users` — gestionar **usuarios locales** y sus roles (sin IdP externo) | No | No | No | Sí |
| `platform.rotate_secrets` — rotar secretos (webhook, cifrado en reposo, backups) | No | No | No | Sí |
| `platform.replay` — reconstruir desde histórico | No | Sí | Sí | No |

Consecuencias de diseño explícitas:

- El **`platform-admin` no ve indicadores operativos**: administra la tubería sin convertirse en un consumidor de intelligence. Es el reverso de "admin ve todo".
- El **`auditor` no ve el dashboard en vivo**: audita la cadena (qué se publicó, quién lo consumió) sin mezclarse en la operación.
- Las capacidades se evalúan **por capacidad**, de modo que añadir un rol nuevo no obliga a tocar el código de autorización: es una tabla de configuración.
- El backend aplica el filtro **antes** de serializar: un `viewer` que manipule parámetros de query (`?unit=...`, `?from=...`) no puede obtener unidades, turnos o periodos no autorizados; los parámetros se validan contra una allowlist.

#### 2.2.4 Mínimo privilegio en almacenamiento

- El backend accede a PostgreSQL con una identidad de servicio propia (`svc_dashboard`) con permisos granulares: `SELECT` solo sobre vistas materializadas de agregados; `INSERT` y `SELECT` sobre `audit_event`; **sin** `DELETE`, **sin** DDL, **sin** acceso a la tabla cruda de instantáneas.
- Los historiales se particionan por `mes` y se cifran en reposo (cifrado de volumen gestionado + cifrado por columna `pgcrypto` para el blob de instantáneas). La tabla de auditoría es **append-only**: el rol de servicio no puede `UPDATE`/`DELETE`.
- Las instantáneas cifradas se conservan **90 días**; los agregados horarios **60 meses**; los eventos de auditoría **60 meses**.
- El backend **nunca** escribe en el documento de Google Sheets ni en ningún almacenamiento del origen: el sistema es unidireccional.

#### 2.2.5 Cero confianza en el cliente

- El navegador **no decide** qué se le muestra: el backend ya filtró por capacidad y por documento. El cliente solo *representa*.
- El bundle de la SPA **no contiene** secretos, ni el secreto del webhook, ni la clave de firma JWT, ni claves de descifrado, ni URLs internas de almacén. Solo el origen público de la API.
- **CSP estricta** (`default-src 'self'`; sin `unsafe-inline` en `script-src`; `connect-src` limitado al origen de la API; `frame-ancestors 'none'`; `object-src 'none'`; `base-uri 'none'`). Esto mitiga XSS y clickjacking de raíz.
- El cliente **valida defensivamente** la forma del mensaje WSS (schema check), rechaza versiones mayores desconocidas, e ignora campos desconocidos; pero la validez contractual es responsabilidad del emisor.
- La caché del cliente está prohibida para respuestas con datos: `Cache-Control: no-store, private`, `Pragma: no-cache`, sin Service Worker de caché de API, y `Clear-Site-Data: "cache", "storage", "cookies"` en el logout.

#### 2.2.6 Identidad de servicio

- El backend se autentica ante el almacén con identidad de servicio de mínimo privilegio (usuario de BD dedicado + credencial inyectada) y no requiere ningún proveedor de identidad externo: la emisión y verificación de JWT es propia (clave de firma gestionada por el backend).
- El origen (Apps Script) y el navegador **no** tienen camino al almacén. No existe ninguna ruta de datos desde el cliente al almacén: el backend es el único escritor de historiales y el único que puede leerlos.
- Los secretos de infraestructura (credenciales de BD, `JWT_SIGNING_KEY`, claves de datos, secreto del webhook) se inyectan en tiempo de ejecución desde un secret manager; **jamás** se versionan, **jamás** se registran en logs (`§9.5`).

---

## 3. Arquitectura de alto nivel

### 3.1 Diagrama de flujo

```text
╔══════════════════════════════════════════════════════════════════════════════════════╗
║  GOOGLE (cuenta estándar Gmail)  (nube del proveedor, no confiable)                   ║
║                                                                                       ║
║   ┌───────────────────┐   onEdit / onChange      ┌───────────────────────────────┐   ║
║   │  Google Sheets    │ ────────────────────────► │  Apps Script (vinculado)     │   ║
║   │  SIFCOP (analista)│   trigger instalable       │  · lee con SpreadsheetApp    │   ║
║   │  · hoja Resumen   │                            │  · normaliza + valida        │   ║
║   │  · hoja Regional  │                            │  · calcula hash de contenido │   ║
║   │  · hoja Turnos    │                            │  · firma HMAC-SHA256         │   ║
║   │  · hoja Ranking   │                            │  · secreto en Script Properties│ ║
║   └───────────────────┘                            └───────────────┬───────────────┘   ║
║           ▲ solo lectura del sistema                              │                   ║
║           │ (nunca escritura de vuelta)                          │                   ║
║  ═════════╪══════════════════════════════════════════════════════════╪═══════════════   ║
║           ║  HTTPS 1.3  ·  POST /api/v1/ingest/webhook                ║                   ║
║           ║  headers: X-Webhook-Signature: sha256=<hex>               ║                   ║
║           ║           X-Webhook-Id, X-Webhook-Nonce,                  ║                   ║
║           ║           X-Webhook-Timestamp, X-Webhook-Version,         ║                   ║
║           ║           X-Webhook-Key-Id                               ║                   ║
║           ║  {webhook_id,key_id,nonce,timestamp,event_id,snapshot}    ║                   ║
╚═══════════╪══════════════════════════════════════════════════════════╪═══════════════   ║
            ║                                                          ▼
╔═══════════╪══════════════════════════════════════════════════════════════════════════╗
║  BACKEND FASTAPI  (frontera de confianza: única que valida)                              ║
║  ┌─────────────────────────────────────────────────────────────────────────────────┐ ║
║  │ Capa 1 · Identidad      rate limit → authn webhook (HMAC) → authn JWT nativo → RBAC ║
║  ├─────────────────────────────────────────────────────────────────────────────────┤ ║
║  │ Capa 2 · Integridad     anti-replay (nonce+ts) → verificar firma HMAC → validar    │ ║
║  │                          esquema/rangos → validar celdas (listas allowlist)         │ ║
║  ├─────────────────────────────────────────────────────────────────────────────────┤ ║
║  │ Capa 3 · Persistencia   idempotencia (event_id UNIQUE) → INSERT snapshots →       │ ║
║  │                          UPSERT hourly_current → INSERT audit_event (append-only)  │ ║
║  ├─────────────────────────────────────────────────────────────────────────────────┤ ║
║  │ Capa 4 · Distribución   Redis Pub/Sub → WS hub → WSS por sala (fan-out con        │ ║
║  │                          filtrado de sala y de capacidad por conexión)             │ ║
║  └───────────────┬─────────────────────────────────┬─────────────────────────────────┘ ║
║                  │ SQL (TLS, identidad svc)        │ eventos                        ║
║                  ▼                                 ▼                                 ║
║   ┌──────────────────────────────┐        (distribución en tiempo real)                 ║
║   │ PostgreSQL                  │                                                      ║
║   │ · ingest_event (90 d)        │                                                      ║
║   │ · agg_hourly / agg_daily     │                                                      ║
║   │ · audit_event (60 meses)     │                                                      ║
║   │ · webhook_registry / secretos │                                                      ║
║   └──────────────────────────────┘                                                      ║
╚════════════════════════════════════════════════════════════════════════════════════════╝
            ║                                              ║
            ║ HTTPS REST (cold start, histórico)         ║ WSS (wss://, TLS 1.3)
            ║  Authorization: Bearer <JWT nativo>        ║  ticket de 1 solo uso (60 s)
            ▼                                              ▼
╔════════════════════════════════════════════════════════════════════════════════════════╗
║  DASHBOARD  ·  React 18 + Vite + Tailwind CSS + Recharts  ·  Cloudflare Pages          ║
║  ┌─────────────────────────────────────────────────────────────────────────────────┐  ║
║  │  Cabecera: título · reloj/TZ · estado de conexión · última actualización · usuario │  ║
║  ├──────────┬──────────┬──────────┬──────────┬─────────────────────────────────────────┤  ║
║  │ VIS-01   │ VIS-02   │ VIS-03   │ VIS-04   │  4 tarjetas KPI (fila superior)        │  ║
║  │ Consultas│ Capturas │ Vehículos│ Armas    │  valor + variación abs/% vs ayer       │  ║
║  ├──────────┴──────────┴──────────┴──────────┴─────────────────────────────────────────┤  ║
║  │  VIS-05 Intervenciones por Unidad Regional  │  VIS-06 Incidentes por Turno Operativo  │  ║
║  │  BarChart layout="vertical" (5 barras)      │  3 turnos MAÑANA/TARDE/NOCHE (EN CURSO)   │  ║
║  ├───────────────────────────────────────────────────────────────────────────────────┤  ║
║  │  VIS-07 Ranking de Dependencias - Top 5 (Posición · Comisaría · Intervenciones ·  │  ║
║  │         Variación)                                                                  │  ║
║  └─────────────────────────────────────────────────────────────────────────────────┘  ║
║  Retícula CSS Grid 12 col · Sin recarga manual · Degradación a polling · CSP estricta  ║
╚════════════════════════════════════════════════════════════════════════════════════════╝
```

### 3.2 Leyenda del flujo

| Salto | Protocolo | Autenticación | Cifrado | Verificación |
|-------|-----------|----------------|---------|--------------|
| 1. Google Sheets → Apps Script | local (contenedor Google) | — (mismo documento, solo lectura) | — | trigger `onEdit`/`onChange`, sin escritura |
| 2. Apps Script → Backend | HTTPS/1.1 o HTTP/2 sobre TLS 1.3 | `HMAC-SHA256` con secreto compartido (`X-Webhook-Signature`) | TLS 1.3 (cifrado en tránsito) | firma + nonce + timestamp + esquema |
| 3. Backend → PostgreSQL | TLS + SCRAM | identidad de servicio `svc_dashboard` | TLS + cifrado de columna | parámetros, RBAC de BD, idempotencia |
| 4. Backend ↔ Navegador (REST) | HTTPS/TLS 1.3 | JWT nativo (15 min) | TLS 1.3 | RBAC por capacidad, CORS allowlist |
| 5. Backend ↔ Navegador (WSS) | **WSS**/TLS 1.3 | ticket 1 uso (60 s) + JWT | TLS 1.3 | RBAC al abrir + `seq` monotónico + heartbeat |

### 3.3 Componentes y responsabilidades

| Componente | Responsabilidades | No debe |
|------------|-------------------|---------|
| **Google Sheets + Apps Script (origen)** | Detectar la edición con trigger instalable (`onEdit`/`onChange`); leer en solo lectura el documento declarado; normalizar y validar; calcular hash de contenido; **firmar con HMAC-SHA256**; enviar por HTTPS con reintentos y backoff; reportar salud | Escribir en el documento; hardcodear el secreto en el código; abrir puertos; sobrepasar las cuotas de Google; conocer los roles del dashboard |
| **Backend FastAPI** | Verificar la **firma del webhook** y la identidad del operador; **emitir y verificar el JWT nativo (login local usuario/contraseña, Argon2id)**; validar; persistir con idempotencia; distribuir por WSS; servir REST; emitir auditoría; aplicar rate limiting; filtrar por capacidad | Confiar en el cliente; emitir datos a un rol sin capacidad; aceptar eventos duplicados; registrar PII; exponer el secreto del webhook |
| **PostgreSQL** | Historial inmutable de eventos; agregados horarios/diarios; auditoría append-only; registro de webhooks; secretos de webhook (metadata) | Aceptar `UPDATE`/`DELETE` desde el rol de servicio; almacenar datos en claro |
| **Redis** | Pub/Sub de eventos entre réplicas del backend; presencia y conteo de conexiones; rate limit distribuido | Almacenar datos funcionales (es descartable) |
| **Dashboard React** | Cold start REST; suscripción WSS; aplicar instantáneas de forma idempotente; renderizar 7 visuales; declarar estado de frescura/conexión; auditar visualizaciones | Recargar la página; inventar datos; ocultar caducidad; contener secretos; decidir autorización |

### 3.4 Topología de despliegue

```text
Cloudflare (edge)
  ├── Cloudflare Pages  ─────────►  SPA estática (assets con hash, inmutables, 1 año)
  └── Proxy/TLS 1.3 + WAF ─────►  origin: FastAPI (3 réplicas mínimo) ─► Redis ─► PostgreSQL (failover)
                                    ▲
Analista ───── HTTPS/WSS (TLS 1.3) ─┘   egress allowlist: solo api.<dominio-gob>
```

- El origen (Apps Script) **solo puede** salir a `api.<dominio-gob>:443`; el código no realiza llamadas a ningún otro destino. El backend no abre puertos de escucha para el origen y Apps Script no abre escucha.
- El edge aplica **WAF gestionado**, rate limiting por IP y bloqueo de USER-Agents no declarados para `/ingest/webhook`.
- La **autenticación nativa (JWT)** corre en el propio backend (sin componente de identidad externo): el almacén de usuarios locales reside en PostgreSQL y la clave de firma (`JWT_SIGNING_KEY`) en el secret manager. Solo se expone `/auth/*` detrás de WAF con rate limiting estricto.

---

## 4. Alcance / No-alcance

### 4.1 En alcance

- Integración con **Google Sheets** (documento en **cuenta Gmail estándar**): trigger instalable de Google Apps Script (`onEdit`/`onChange`) que detecta ediciones de un **único** documento declarado y notifica al backend.
- Webhook firmado con **HMAC-SHA256** (secreto compartido) desde Apps Script al backend, con nonce + timestamp y verificación previa a la deserialización.
- Verificación del origen por **secreto de webhook** versionado (`key_id`), con rotación (solape 24 h) y revocación.
- Backend FastAPI con endpoints REST de ingesta, **cold start** del dashboard, histórico, salud y **WebSocket seguro** con fan-out por `room_id` (una instancia = una sala; no hay selector de sala en la UI).
- **Reconciliación por polling de respaldo** mediante la API de Google Sheets (service account de solo lectura) como red de seguridad ante triggers perdidos; opera sobre la **cuenta Gmail estándar** del documento.
- Persistencia de historiales en PostgreSQL con idempotencia por `event_id` y agregados horarios/diarios para comparativas "vs ayer".
- Dashboard React (Vite + Tailwind + Recharts) en Cloudflare Pages con: 4 tarjetas KPI con variación, gráfico de barras horizontales por unidad regional, gráfico de incidentes por **turno operativo**, tabla de ranking Top 5 y diseño táctico de alto contraste en modo oscuro.
- Autenticación del operador por **login nativo (usuario+contraseña → JWT)** emitido por el backend, autorización por **capacidades**, auditoría de lecturas y de escrituras.
- Gestión de **usuarios y roles locales** en el backend (hash Argon2id, bloqueo por intentos, rotación de `JWT_SIGNING_KEY`); **sin** IdP externo, SSO ni MFA.
- Reconexión automática del WSS con backoff exponencial, heartbeat y degradación a polling con señalización visible.
- Internacionalización de la interfaz a **español** (es-CR por defecto), formato numérico local (`es-CL`: miles con punto, decimal con coma).

### 4.2 Fuera de alcance (out of scope, explícito)

| ID | Excluido | Motivo / nota |
|----|----------|----------------|
| OOS-01 | **Escritura o edición de datos desde el dashboard** | El dashboard es de solo lectura. Toda escritura en el documento de Google Sheets es responsabilidad del analista y del SIFCOP. |
| OOS-02 | **Carga manual de datos desde la UI** | Solo el webhook de Apps Script (o la reconciliación de respaldo) publica. Un endpoint de carga manual por usuario se consideraría un bypass de la cadena de confianza. |
| OOS-03 | **Escritura de vuelta al documento de Google Sheets (bidireccional)** | Rompe el modelo de un solo sentido y abriría una vía de manipulación del origen. |
| OOS-04 | **Generación de reportes PDF / impresión de informe** | Solo se admite exportación CSV de agregados con `dash.export.csv`. |
| OOS-05 | **Aplicación móvil (iOS/Android) nativa** | El consumo previsto es pantalla fija de sala de operaciones. |
| OOS-06 | **Edición del schema del documento por el sistema** | El validador **tolera** cambios de layout dentro de una lista allowlist; si la cabecera no coincide, falla cerrado y avisa. No "adivina" columnas. |
| OOS-07 | **Ingesta desde otras fuentes** (CSV, SFTP, base de datos, API del SIFCOP) | Especificado únicamente el origen Google Sheets. Otros orígenes requerirían su propio RF. |
| OOS-08 | **Cifrado extremo a extremo navegador↔origen** | El navegador no puede custodiar un secreto compartido sin degradar la seguridad (XSS, devtools, caché). El tramo navegador↔backend va protegido con TLS 1.3 + WSS + autorización; el tramo Apps Script↔backend va firmado con HMAC sobre TLS 1.3. |
| OOS-09 | **Predicción, modelado o analítica avanzada** (IA/ML) | Solo visualización de lo publicado. |
| OOS-10 | **Geo-mapeo / mapas** | No solicitado; el requisito es gráfico de barras por unidad regional. |
| OOS-11 | **Multi-tenant / multi-instalación en el mismo despliegue** | Una instancia = una sala. Multi-sala se resuelve con `room_id` en el mismo modelo de datos, sin UI de conmutación. |
| OOS-12 | **Disponibilidad 24×7 con SLA contractual de uptime** | Se define objetivo técnico (99,9 % mensual) pero no acuerdo de nivel de servicio con penalización. |
| OOS-13 | **SSO federado / MFA / step-up** | La autenticación es nativa (usuario+contraseña → JWT) **sin MFA ni step-up**; integrar un IdP externo queda fuera de este sistema. |
| OOS-14 | **Formación/capacitación de usuarios** | Fuera del alcance técnico. |

---

## 5. Requisitos funcionales (EARS)

**Notación EARS usada en este documento** (patrones explícitos y literales):

| Patrón | Uso |
|--------|-----|
| `CUANDO <evento> ENTONCES EL SISTEMA <respuesta>` | Impulsado por evento, una respuesta. |
| `SI <condición> ENTONCES EL SISTEMA <respuesta>` | Condicional, sin evento temporal. |
| `MIENTRAS <estado> EL SISTEMA <respuesta>` | Invariante sostenido mientras se cumple el estado. |
| `EL SISTEMA DEBE <comportamiento>` (precedido de `Where` / `While`) | Comportamiento obligatorio, en forma universal/de evento/estado. |

El **actor responsable** se indica explícitamente entre paréntesis cuando procede. Las sub-letras (`RF-01.a`) desglosan cada RF en unidades verificables **sin alterar la letra del RF original**, que se conserva textualmente arriba del desglose.

---

### RF-01 — Transmisión Segura

> **Texto original (literal):**
> *CUANDO un trigger instalable de Google Apps Script detecte cambios en un documento de Google Sheets, EL SISTEMA notificará al backend (FastAPI) mediante un webhook firmado con HMAC-SHA256, validará el origen y retransmitirá la actualización a React vía WebSockets Seguros (WSS).*

| ID | Requisito (EARS) |
|----|------------------|
| **RF-01.a** | EL SISTEMA DEBE detectar la edición del documento de Google Sheets mediante un **trigger instalable de Apps Script (`onEdit`/`onChange`)**, con una **reconciliación por polling de respaldo** (red de seguridad) cada **60 s** y coalescencia de **750 ms**. |
| **RF-01.b** | EL SISTEMA DEBE agrupar (coalescer) ráfagas de ediciones sobre el mismo documento y descartar notificaciones sin cambios reales (rangos vacíos, cambios de formato o estructura que no alteran el contenido de los indicadores). |
| **RF-01.c** | CUANDO se detecte una edición efectiva, EL SISTEMA DEBE calcular un **hash SHA-256 del contenido normalizado** del documento y omitir la transmisión si el hash es idéntico al último enviado con éxito (**deduplicación por contenido**). |
| **RF-01.d** | CUANDO haya que transmitir, EL SISTEMA DEBE **firmar el payload con HMAC-SHA256** (secreto compartido, versión `key_id`) incluyendo **nonce de 128 bits y timestamp UTC**, y enviarlo por HTTPS con **TLS 1.3**. |
| **RF-01.e** | CUANDO el backend reciba el webhook, EL SISTEMA DEBE validar la **firma HMAC-SHA256** (comparación en tiempo constante), que el `webhook_id` esté activo y sin revocar y que el `key_id` esté vigente, y **rechazar con `401/403` cualquier mensaje que no lo supere**, sin deserializar el cuerpo. |
| **RF-01.f** | CUANDO el backend verifique el mensaje, EL SISTEMA DEBE comprobar **firma y frescura (nonce + timestamp) antes de interpretar cualquier campo** (fallo cerrado ante firma inválida o replay, `401`/`409` + auditoría). |
| **RF-01.g** | CUANDO el backend acepte la instantánea, EL SISTEMA DEBE **redistribuírla por WSS** a todas las conexiones autorizadas de la sala en menos de **100 ms (p95)** desde la aceptación. |
| **RF-01.h** | EL SISTEMA DEBE registrar en auditoría cada envío aceptado o rechazado, con `webhook_id`, `event_id`, `doc_id`, `hash`, `key_id`, resultado y `correlation_id`. |
| **RF-01.i** | CUANDO la transmisión falle por error transitorio (red caída, `5xx`, timeout), EL SISTEMA DEBE reintentar en Apps Script con **backoff exponencial 2 s, 4 s, 8 s, 16 s, 32 s, 60 s (tope)** con jitter ±20 %, y el backend DEBE **reconciliar por polling de respaldo** (service account de solo lectura) para no perder eventos. |
| **RF-01.j** | CUANDO transcurran **15 minutos** sin contacto del webhook con el backend, EL SISTEMA DEBE poner el origen en modo *degradado*, registrar el evento y activar la reconciliación por polling sin descartar datos. |
| **RF-01.k** | CUANDO el backend rechace un mensaje por **anti-replay** (`X-Webhook-Nonce` repetido o timestamp fuera de ±300 s), EL SISTEMA DEBE responder `409` y el origen DEBE generar un nonce nuevo, sin reintentar el mismo nonce. |
| **RF-01.l** | CUANDO el backend supere firma y frescura, EL SISTEMA DEBE validar las **cabeceras, el esquema y los rangos** del payload contra el JSON Schema y los catálogos fijos (5 unidades, 3 turnos, 4 KPIs, ranking ≤ 5), rechazar con `422` los valores inválidos (KPI negativo/`NaN`, unidad/turno fuera de allowlist) y **no persistir ni redistribuir** el evento (fallo cerrado). |
| **RF-01.m** | CUANDO el backend reciba un `event_id` ya aceptado, EL SISTEMA DEBE aplicar **idempotencia** (restricción `UNIQUE` por `event_id`): responde `200` con `duplicate=true` y **no vuelve a persistir ni a redistribuir**. |

---

### RF-02 — Tarjetas de Indicadores (KPIs)

> **Texto original (literal):**
> *CUANDO React reciba los datos por WebSocket, EL SISTEMA actualizará en tiempo real 4 bloques superiores: "Total Consultas SIFCOP", "Personas Capturadas", "Vehículos Secuestrados" y "Armas Secuestradas", mostrando la cifra total y la variación respecto a ayer.*

| ID | Requisito (EARS) |
|----|------------------|
| **RF-02.a** | CUANDO React reciba por WSS un evento `kpi.snapshot`, EL SISTEMA DEBE actualizar **sin recarga manual de página** los **4 bloques superiores**, en el mismo orden fijo: (1) Total Consultas SIFCOP, (2) Personas Capturadas, (3) Vehículos Secuestrados, (4) Armas Secuestradas. |
| **RF-02.b** | EL SISTEMA DEBE colocar las 4 tarjetas en una **fila superior de la retícula** (Row 1), de ancho igual (3 de 12 columnas cada una), con el mismo formato y la misma alineación. |
| **RF-02.c** | CADA tarjeta DEBE mostrar: **etiqueta** (12 px, versalitas), **valor total** (número entero, 34 px, tabular), **variación absoluta** (`+N` / `−N` / `0`) y **variación porcentual** (`+N,N %` / `−N,N %`), ambas con **signo explícito**, y un **indicador de dirección** (▲ / ▼ / =) que no depende del color. |
| **RF-02.d** | EL SISTEMA DEBE calcular la variación respecto a ayer como **comparación del acumulado del día actual hasta la misma hora (HH:MM) contra el acumulado del día anterior hasta la misma hora**, en la zona horaria canónica declarada (§13). Si el día anterior no tiene registro, la variación se marca como `null` y la tarjeta muestra "—" y el texto "sin referencia". |
| **RF-02.e** | EL SISTEMA DEBE aplicar color al indicador de variación: **verde `#34D399`** si la variación es positiva, **rojo `#F87171`** si es negativa, **gris `#94A3B8`** si es cero, **manteniendo siempre el glifo y el signo textual** (nunca solo color) — fulfil RNF-09. |
| **RF-02.f** | CUANDO el valor de un KPI no cambie entre dos instantáneas, EL SISTEMA DEBE **omitir la animación de recuento** y no modificar el DOM de forma visible (idempotencia visual). |
| **RF-02.g** | CUANDO cambie el valor, EL SISTEMA DEBE animar el recuento en **400 ms** con easing `ease-out`, y **marcar visualmente la tarjeta durante 600 ms** con un borde de acento para que el operador perciba qué tarjeta cambió. |
| **RF-02.h** | MIENTRAS no haya ninguna instantánea válida recibida (cold start fallido o primer arranque), EL SISTEMA DEBE mostrar el esqueleto de carga (skeleton) en las 4 tarjetas, **nunca ceros inventados**. |
| **RF-02.i** | CUANDO el valor de cualquier KPI sea **negativo, no numérico o `NaN`**, EL SISTEMA DEBE rechazar la instantánea completa y mostrar el banner `DATOS NO VÁLIDOS` (tratamiento *fail-closed*). |
| **RF-02.j** | EL SISTEMA DEBE registrar en auditoría **la primera visualización de la sala por cada operador y cada cambio de día de datos**, asociando `sub`, `room_id`, `data_date` e `event_id` visualizado. |
| **RF-02.k** | SI el operador no posee la capacidad `dash.view.live`, ENTONCES EL SISTEMA DEBE responder `403` y renderizar la pantalla de acceso denegado **sin filtrar qué indicadores existen** (ni nombres, ni valores, ni su ausencia). |

---

### RF-03 — Gráfico Regional

> **Texto original (literal):**
> *MIENTRAS el panel esté activo, EL SISTEMA mostrará un gráfico de barras horizontales detallando las "Intervenciones por Unidad Regional" (Capital, Sur, Este, Oeste, Norte).*

| ID | Requisito (EARS) |
|----|------------------|
| **RF-03.a** | MIENTRAS el panel esté activo (conexión WSS abierta o fallback polling activo), EL SISTEMA DEBE mostrar un gráfico de **barras horizontales** titled "Intervenciones por Unidad Regional", implementado con Recharts `BarChart` y `layout="vertical"`. |
| **RF-03.b** | EL SISTEMA DEBE representar exactamente **5 categorías**: `Capital`, `Sur`, `Este`, `Oeste`, `Norte`, en **orden fijo estable** (alfabético configurable; por defecto el orden canónico de la lista), con etiqueta visible en el eje Y. |
| **RF-03.c** | EL SISTEMA DEBE escalar el eje X a `[0, max(datos) × 1,15]` con marcas cada unidad de 5 (mínimo 4 marcas) y **líneas de guía solo horizontales** (`CartesianGrid vertical={false}`) para no competir con las barras. |
| **RF-03.d** | CUANDO hover o foco de teclado sobre una barra, EL SISTEMA DEBE mostrar un tooltip con: Unidad Regional, Intervenciones, Variación absoluta, Variación porcentual y puesto en el ranking regional. |
| **RF-03.e** | CUANDO los datos de una unidad regional no existan, EL SISTEMA DEBE mantener la categoría visible con barra en **0 px y etiqueta "sin datos"** (la categoría se mantiene, no se elimina). |
| **RF-03.f** | CUANDO una snapshot cambie, EL SISTEMA DEBE animar la transición de barras en **400 ms** `ease-out` y **debe mantener la posición Y estable** (sin reordenación por valor: el orden es territorial, no por magnitud, para evitar saltos visuales). |
| **RF-03.g** | EL SISTEMA DEBE etiquetar el valor al final de cada barra (`LabelList position="right"`, 12 px) para permitir lectura sin interacción. |
| **RF-03.h** | SI el conjunto de unidades recibido contiene una unidad **fuera de la allowlist** de 5, EL SISTEMA DEBE ignorarla, auditarla como `rejected_unknown_unit` y continuar mostrando las 5 conocidas. |

---

### RF-04 — Tendencia y Ranking

> **Texto original (literal):**
> *CUANDO haya datos, EL SISTEMA renderizará un gráfico de "Incidentes por Franja Horaria" (00-03, 03-06, etc.) y una tabla con el "Ranking de Dependencias - Top 5" indicando Posición, Comisaría, Intervenciones y Variación.*

> **Nota de diseño:** La implementación usa **3 turnos operativos** (06-14, 14-22, 22-06) en lugar de 8 franjas de 3h, por decisión OD-12 confirmada.

| ID | Requisito (EARS) |
|----|------------------|
| **RF-04.a** | CUANDO haya datos, EL SISTEMA DEBE renderizar un gráfico titled **"Incidentes por Turno Operativo"** con exactamente **3 turnos** en orden cronológico: `MAÑANA` (06:00–14:00), `TARDE` (14:00–22:00), `NOCHE` (22:00–06:00+1). |
| **RF-04.b** | EL SISTEMA DEBE **resaltar el turno en curso** (el que contiene la hora actual en la zona horaria canónica `America/Argentina/Buenos_Aires`) con color de acento `#38BDF8` y una etiqueta `EN CURSO`; los turnos ya cerrados usan `#0EA5E9` y los futuros usan `#1E2A3D` (con etiqueta `—` para evitar lectura de ceros como ausencia de incidentes). |
| **RF-04.c** | CUANDO hover o foco sobre una barra de turno, EL SISTEMA DEBE mostrar tooltip con: Turno, Intervenciones, Variación absoluta, Variación porcentual y estado (`CERRADA` / `EN CURSO` / `PENDIENTE`). |
| **RF-04.d** | CUANDO haya datos, EL SISTEMA DEBE renderizar una tabla titled **"Ranking de Dependencias - Top 5"** con exactamente **4 columnas** y encabezado fijo: `Posición`, `Comisaría`, `Intervenciones`, `Variación`. |
| **RF-04.e** | EL SISTEMA DEBE poblar la tabla con **hasta 5 filas**, ordenadas por intervenciones descendentes y, en empate, por orden alfabético de nombre de dependencia (desempate determinista). |
| **RF-04.f** | EL SISTEMA DEBE formatear la columna `Posición` como badge numérico `1`–`5`, con la fila de mayor valor destacada con acento; `Intervenciones` como entero con separador de miles local; `Variación` con **signo, glifo y porcentaje** (`▲ +12 (+3,4 %)` / `▼ −5 (−1,1 %)` / `= 0 (0,0 %)`). |
| **RF-04.g** | CUANDO una dependencia cambie de puesto respecto de la instantánea anterior, EL SISTEMA DEBE **marcar la fila durante 600 ms** (destello de acento) y registrar la causa en el `aria-label` de la fila para lectores de pantalla. |
| **RF-04.h** | SI existen menos de 5 dependencias con datos, EL SISTEMA DEBE mostrar **solo las existentes** (nunca filas de relleno) y, si no hay ninguna, el estado vacío `SIN DATOS` con el motivo (`sin datos en origen` / `sin datos en caché`). |
| **RF-04.i** | EL SISTEMA DEBE exponer tabla y gráfico como regiones ARIA (`role="table"`, `<caption>`, encabezados con `scope`), navegables por teclado con `Tab` y con **lectores de pantalla**. |
| **RF-04.j** | EL SISTEMA DEBE **no** entregar al navegador datos de filas de detalle (personas, matrículas, armas individuales): solo agregados por dependencia y turno. |

---

### RF-05 — UI Táctica

> **Texto original (literal):**
> *SI el usuario visualiza el dashboard, ENTONCES EL SISTEMA utilizará un diseño de alto contraste en modo oscuro (fondos azul marino/negro, texto blanco y acentos celestes) optimizado para pantallas de monitoreo continuo.*

| ID | Requisito (EARS) |
|----|------------------|
| **RF-05.a** | SI el usuario visualiza el dashboard, ENTONCES EL SISTEMA DEBE aplicar un tema **modo oscuro** (el sistema no ofrece tema claro) con fondo azul marino/negro, texto blanco y acentos celestes según la paleta de §11.2. |
| **RF-05.b** | EL SISTEMA DEBE alcanzar **contraste ≥ 4,5:1** para texto normal y **≥ 3:1** para texto grande, componentes de UI y objetos gráficos (`#FFFFFF` sobre `#0B1220` = **15,8:1**; `#38BDF8` sobre `#0B1220` = **9,1:1**). |
| **RF-05.c** | EL SISTEMA DEBE usar **una retícula fija de 12 columnas** (§11.1) sin scroll vertical en **1920×1080** con escala 100 %, y sin scroll horizontal en 1920×1080, 2560×1440 y 3840×2160. |
| **RF-05.d** | EL SISTEMA DEBE fijar `min-width` del panel en **1280 px**; por debajo de 1280 px muestra un aviso de resolución no soportada en lugar de un diseño roto. |
| **RF-05.e** | EL SISTEMA DEBE usar **numeración tabular** (`font-variant-numeric: tabular-nums`) en KPI, ejes y tabla, de modo que los dígitos no "bailen" al actualizarse. |
| **RF-05.f** | EL SISTEMA DEBE alcanzar **60 fps** en las animaciones de actualización (marco de 16,7 ms) y **no superar 250 ms de trabajo de render por actualización**; si `requestAnimationFrame` reporta frames > 32 ms durante 60 frames consecutivos, DEBE degradar la animación a actualización instantánea y registrar el evento. |
| **RF-05.g** | EL SISTEMA DEBE declarar el estado de conexión de forma permanente y textual: `EN VIVO` (verde), `RECONECTANDO` (ámbar), `DEGRADADO · POLLING` (ámbar), `SIN CONEXIÓN` (rojo), con la hora de la **última actualización de datos**. |
| **RF-05.h** | CUANDO la última actualización de datos supere **120 s**, EL SISTEMA DEBE mostrar el banner ámbar `DATOS DESACTUALIZADOS — hace Xs` y **atenuar visualmente los visuales affected** (opacidad 0,75) sin alterar sus valores. |
| **RF-05.i** | EL SISTEMA DEBE respetar `prefers-reduced-motion: reduce` desactivando las transiciones de recuento y de barras (manteniendo el cambio de valor). |
| **RF-05.j** | CUANDO el operador navegue por teclado, EL SISTEMA DEBE ofrecer **foco visible** (contorno `#38BDF8` de 2 px con desfase de 2 px), orden de tabulación lógico (cabecera → tarjetas → gráfico regional → gráfico turnos → tabla) y *skip link* "Saltar al contenido". |
| **RF-05.k** | EL SISTEMA DEBE **no** comunicar información solo por color: toda variación lleva glifo + signo; toda serie de gráfico es identificable por etiqueta; los estados llevan texto. |
| **RF-05.l** | EL SISTEMA DEBE usar **espaciado mínimo de 8 px** en todos los ejes, y un área de contacto mínima de **44×44 px** para elementos interactivos. |

---

## 6. Requisitos no funcionales (RNF)

Todos los valores son **verificables y concretos**. La columna "Medición" indica cómo se comprueba en la validación automatizada o en la auditoría de configuración.

### RNF-01 — Cifrado en tránsito

| ID | Requisito |
|----|-----------|
| **RNF-01.a** | EL SISTEMA DEBE aceptar **únicamente TLS 1.3** en el borde y en el salto Apps Script→backend (`ssl_version = TLSv1_3`); **TLS 1.2 queda deshabilitado** sin ventana de compatibilidad (coherente con OD-09). |
| **RNF-01.b** | EL SISTEMA DEBE servir HSTS con `max-age=31536000; includeSubDomains; preload` y `Strict-Transport-Security` en toda respuesta HTML y en los endpoints de API. |
| **RNF-01.c** | EL SISTEMA DEBE forzar redirección `HTTP → HTTPS` con `301` y **no servir contenido en el origen HTTP**. |
| **RNF-01.d** | EL SISTEMA DEBE usar **WSS** (`wss://`) exclusivamente para el canal de tiempo real; la conexión en claro debe ser rechazada en el handshake. |
| **RNF-01.e** | EL SISTEMA DEBE presentar solo certificados **públicamente confiables** (cadena completa), sin cadenas inseguras, con `OCSP stapling` habilitado y HPKP no requerido (obsoleto). |
| **RNF-01.f** | EL SISTEMA DEBE verificar además la **autenticidad e integridad** del tramo Apps Script→backend con **firma HMAC-SHA256** (capa adicional a TLS), según §9. |
| **RNF-01.g** | El backend→PostgreSQL DEBE ir cifrado con TLS y autenticación **SCRAM-SHA-256**, con `sslmode=verify-full` (validación de CA y hostname). |

**Medición:** `testssl.sh`/ZAP reportan solo TLS 1.3; la respuesta incluye HSTS; la firma HMAC-SHA256 del webhook se verifica antes de deserializar (rechazo sin firma o con firma manipulada).

### RNF-02 — Cifrado en reposo

| ID | Requisito |
|----|-----------|
| **RNF-02.a** | EL SISTEMA DEBE cifrar en reposo las instantáneas almacenadas con **AES-256-GCM** (columna `payload_ciphertext`) mediante `pgcrypto`, con la clave en el secret manager, **nunca** en la base de datos, aunque el payload llegue en claro sobre TLS desde el webhook. |
| **RNF-02.b** | EL SISTEMA DEBE cifrar en reposo el **secreto del webhook**: en el backend reside en el secret manager (nunca en la base de datos); en Apps Script reside en **`Script Properties`** (cifrado en reposo por Google), nunca en el código versionado. |
| **RNF-02.c** | EL SISTEMA DEBE cifrar los volúmenes/backups del almacén con cifrado gestionado por el proveedor (AES-256 en reposo) y **verificar la restauración** cifrada en el procedimiento de recuperación (§RNF-14). |
| **RNF-02.d** | Los **eventos de auditoría** se almacenan cifrados en reposo pero **no** deben contener PII (§RNF-08), para permitir su consulta por el rol `auditor` sin descifrar datos operativos. |
| **RNF-02.e** | EL SISTEMA DEBE **no** almacenar en claro el secreto del webhook en ningún componente; en el backend el material del secreto reside únicamente en el secret manager y en la base de datos se guarda solo metadata (`webhook_secret`: `key_id`, estado, fechas). |
| **RNF-02.f** | Cualquier dump de base de datos usado en soporte o análisis se considera **dato sensible** y debe cifrarse y destruirse tras su uso. |

**Medición:** `SELECT` sobre columnas de texto plano → solo se obtienen ciphertext/base64; `pg_dump` sin la clave no es utilizable.

### RNF-03 — Autenticación y autorización

| ID | Requisito |
|----|-----------|
| **RNF-03.a** | EL SISTEMA DEBE autenticar operadores con **login nativo (usuario y contraseña)** contra el almacén local del backend, **sin MFA ni SSO**; las contraseñas se almacenan solo como **hash fuerte (Argon2id)** con sal por usuario. |
| **RNF-03.b** | EL SISTEMA DEBE emitir **tokens de acceso de 15 min** (JWT firmado por el backend con `JWT_SIGNING_KEY`; `HS256` o firma asimétrica equivalente) y **refresh tokens rotativos indefinidos mientras haya actividad** (sin TTL fijo; se renuevan en cada latido WSS/heartbeat). Detección de reutilización obligatoria (reuse detection: reutilizar un refresh token revoca la cadena completa). |
| **RNF-03.c** | EL SISTEMA DEBE comprobar la **capacidad** requerida en cada endpoint y en cada apertura de WSS; por defecto `deny`. |
| **RNF-03.d** | El acceso al WSS DEBE requerir un **ticket de un solo uso** (TTL 60 s, ligado a `sub` + capacidades + `room_id`); un ticket no puede abrir más de una conexión ni reutilizarse. |
| **RNF-03.e** | EL SISTEMA DEBE revocar refrescos y cerrar WSS activos cuando un usuario pierde rol o se desactiva la cuenta (`sub` en lista de revocación), en ≤ 30 s. |
| **RNF-03.f** | El acceso del webhook se autentica con **firma HMAC-SHA256** sobre el cuerpo canónico y los metadatos, con **secreto compartido por origen** en `Script Properties`, con revocación individual, rotación (solape 24 h) y **anti-replay** (nonce + timestamp ±300 s). |
| **RNF-03.g** | Las acciones sensibles (gestionar el secreto del webhook/usuarios, exportar, replay) exigen la **capacidad correspondiente y se auditan**; **no hay MFA ni step-up**; **no hay bloqueo por inactividad para la visualización en vivo** (la sesión persiste mientras el navegador esté abierto y haya actividad). |
| **RNF-03.h** | EL SISTEMA DEBE registrar el resultado (`permitido`/`denegado`, capacidad, motivo) de **cada** intento de autorización. |
| **RNF-03.i** | EL SISTEMA DEBE **bloquear temporalmente** una cuenta tras N intentos fallidos de login (con backoff progresivo) y aplicar rate limit por IP/usuario; todo intento fallido se audita **sin** registrar la contraseña. |

**Medición:** tests que iteran roles × endpoints asserting 200/403; intento con token expirado → 401; ticket reutilizado → 4401.

### RNF-04 — Rendimiento y latencia

| ID | Requisito |
|----|-----------|
| **RNF-04.a** | EL SISTEMA DEBE alcanzar **p95 ≤ 1,5 s** y **p99 ≤ 3 s** desde el evento de edición en Google Sheets hasta el refresco visual en el dashboard, descompuesto así: |

| Tramo | Objetivo p95 |
|-------|--------------|
| Detección de edición + ejecución del trigger (Apps Script) | ≤ 300 ms (coalescencia 750 ms) |
| Lectura + normalización + firma (Apps Script) | ≤ 250 ms |
| Red + verificación de firma + validación (backend) | ≤ 350 ms |
| Persistencia + fan-out WSS (backend) | ≤ 200 ms |
| Recepción + validación de esquema + render (navegador) | ≤ 250 ms |
| **Total** | **≤ 1,5 s** (p99 ≤ 3 s) |

> **Nota:** Con **3 réplicas mínimo** (antes 2) el objetivo p95 ≤ 1,5 s se mantiene bajo carga media (100–1 000 ediciones/día).

| ID | Requisito |
|----|-----------|
| **RNF-04.b** | EL SISTEMA DEBE mantener **60 fps** (16,7 ms/frame) durante las animaciones de actualización, con presupuesto de render ≤ 250 ms por actualización y degradación automática si el frame time supera 32 ms (ver RF-05.f). |
| **RNF-04.c** | El **cold start** (`GET /dashboard/snapshot`) DEBE devolver p95 ≤ 800 ms desde el borde y renderizar el panel completo (7 visuales) en ≤ 1,5 s. |
| **RNF-04.d** | El **fan-out WSS** a una sala con 50 conexiones DEBE entregar la instantánea en ≤ 100 ms (p95) desde la aceptación. |
| **RNF-04.e** | El payload de una instantánea DEBE ser ≤ 64 KB comprimidos (§13), permitiendo entregas sub-100 ms en enlaces de sala. |
| **RNF-04.f** | El backend DEBE sostener ≥ 50 conexiones WSS y ≥ 100 req/s REST por réplica sin degradación; el objetivo global es **200 clientes concurrentes**. |
| **RNF-04.g** | MIENTRAS haya una actualización de KPI, EL SISTEMA NO DEBE bloquear la interacción del operador (la entrada de teclado y el foco siguen respondiendo < 100 ms). |

**Medición:** pruebas de carga (k6) + marcas de tiempo (`performance.now()`) en el navegador inyectadas en `data-seq`; histograma en observabilidad.

### RNF-05 — Reconexión, reintentos y resiliencia del canal

| ID | Requisito |
|----|-----------|
| **RNF-05.a** | CUANDO el WSS se cierre o se degrade, EL SISTEMA DEBE reconectar con **backoff exponencial con jitter**: intentos en 1 s, 2 s, 4 s, 8 s, 16 s, 30 s y luego **topado en 30 s**, jitter ±20 %, sin límites de reintento (reintento indefinido mientras la pestaña esté visible). |
| **RNF-05.b** | EL SISTEMA DEBE enviar **heartbeat/ping de aplicación cada 15 s** (el backend responde `pong`); si no hay actividad del servidor en **45 s**, el cliente cierra la conexión y reconecta. |
| **RNF-05.c** | CUANDO el cliente detects cierre **anómalo** (código distinto de `1000`), EL SISTEMA DEBE reconectar de inmediato (sin esperar el backoff) **solo** si el cierre fue por red/caída, y aplicar backoff si el servidor rechaza (p. ej. `4003`/`4401`, requieren re-autenticación). |
| **RNF-05.d** | CUANDO el WSS no se establezca en **60 s**, EL SISTEMA DEBE **degradar a polling REST** (`GET /dashboard/snapshot`) cada **10 s** y rotular la sesión como `DEGRADADO · POLLING` (visible). |
| **RNF-05.e** | CUANDO se restablezca el WSS, EL SISTEMA DEBE **cerrar el polling** y solicitar un cold start (para no dejar huecos) antes de reanudar eventos en vivo. |
| **RNF-05.f** | CUANDO se pierda la conexión durante > 120 s, EL SISTEMA DEBE mostrar `DATOS DESACTUALIZADOS` (RF-05.h) aunque el polling devuelva 200 con datos viejos: la frescura se evalúa por `ts` del dato, no por el éxito HTTP. |
| **RNF-05.g** | EL SISTEMA DEBE **ignorar y descartar** mensajes WSS con `seq ≤ lastSeq` o `event_id` ya aplicado (idempotencia de red, ver RNF-15). |

**Medición:** tests que cortan la red, cierran el socket y verifican secuencia de reintentos (con jitter dentro de rango), transición a polling, y retorno a `EN VIVO` con cold start.

### RNF-06 — Disponibilidad

| ID | Requisito |
|----|-----------|
| **RNF-06.a** | Objetivo de disponibilidad de la API (lectura dashboard + ingesta) **99,9 % mensual** (excluye ventanas de mantenimiento announced de ≥ 48 h por adelantado; *maintenance windows no cuentan para el SLA*, según OD-10). |
| **RNF-06.b** | Objetivo de disponibilidad de la distribución WSS **99,5 % mensual**; un fallo de WSS degrada a polling (RNF-05.d) sin perder el servicio de lectura. |
| **RNF-06.c** | El servicio DEBE ser **multi-réplica sin estado en el servidor** (estado de fan-out en Redis), permitiendo *rolling deploy* sin corte para el dashboard. |
| **RNF-06.d** | El storage DEBE operar con **failover** (réplica síncrona en otra zona) y **PITR** (recovery point in time). |
| **RNF-06.e** | El cold start DEBE funcionar **aunque Redis no esté disponible** (lee de PostgreSQL), degradando el fan-out en vivo a "recibirás datos con retraso de réplica" (mismo `seq`, sin pérdida histórica). |
| **RNF-06.f** | EL SISTEMA DEBE no perder eventos si el backend no está disponible: Apps Script reintenta con backoff y el backend **reconcilia por polling de respaldo** mediante la API de Google Sheets (service account de solo lectura) al recuperarse (RF-01.i). |

**Medición:** synthetic checks por minuto (`/health/ready`); historia de incidentes; failover ensayado trimestralmente.

### RNF-07 — Observabilidad

| ID | Requisito |
|----|-----------|
| **RNF-07.a** | EL SISTEMA DEBE emitir **métricas** (Prometheus) de: latencia ingesta (p50/p95/p99), eventos/s, conexiones WSS activas, reconexiones/s, mensajes rechazados por causa, tasa de polling, tamaño de payload, errores 4xx/5xx por endpoint. |
| **RNF-07.b** | EL SISTEMA DEBE emitir **trazas distribuidas** (OpenTelemetry) con `trace_id` propagado del origen (Apps Script) al backend al cliente (header `X-Correlation-Id` y campo `correlation_id` en el evento), de modo que una actualización de KPI sea rastreable extremo a extremo. |
| **RNF-07.c** | EL SISTEMA DEBE exponer **healthchecks**: `/health/live` (proceso), `/health/ready` (BD + Redis), y un endpoint **interno** `/metrics` no público. |
| **RNF-07.d** | EL SISTEMA DEBE generar **alertas** configurables: p95 de latencia > 2 s (10 min), tasa de rechazo > 1 %, conexiones WSS a 0 con sala activa, reintentos de webhook agotados / último webhook > 5 min, payload > 64 KB, debounce de SQL > 1 %. |
| **RNF-07.e** | EL SISTEMA DEBE exponer un **panel de salud de la sala** (uso interno de `platform-admin`): última actualización de datos, estado del webhook (última recepción, reintentos), estado de cada réplica, estado del storage, y "edad del dato" global. |
| **RNF-07.f** | EL SISTEMA DEBE medir y reportar la **fracción de actualizaciones** que llegan al dashboard (agregando por `event_id`), exponiendo la **latencia percibida real** por operador. |

**Medición:** panel Grafana operativo; un evento de prueba se localiza por `correlation_id` en menos de 2 min.

### RNF-08 — Auditoría y trazabilidad (quién consultó qué)

| ID | Requisito |
|----|-----------|
| **RNF-08.a** | EL SISTEMA DEBE registrar **toda** acción sensible en una bitácora **append-only** (`audit_event`): registro/rotación/revocación de secreto de webhook, ingestión aceptada/rechazada (con causa), conexión WSS abierta/cerrada, lectura de dashboard (con `room_id`, `sub`, capacidades, `event_id`s vistos), consulta de histórico, exportación, rotación de clave, cambio de rol/revocación. |
| **RNF-08.b** | Cada entrada DEBE incluir: `ts` (UTC, ISO-8601), `actor` (`sub` o `webhook_id`), `action`, `resource`, `result`, `ip` (seudonimizada), `user_agent`, `correlation_id`, `schema_version`. |
| **RNF-08.c** | EL SISTEMA DEBE usar **logging estructurado JSON** a stdout (recolectado por el agregador) **sin datos personales**: prohibido incluir en logs nombres de personas, matrículas, armas individuales o cualquier celda sensible; los identificadores de persona se **hash/trunc**an o se omiten. |
| **RNF-08.d** | La bitácora DEBE tener retención de **60 meses** y ser **append-only** (el rol de servicio no la altera); su consulta requiere capacidad `audit.view`. |
| **RNF-08.e** | El registro de **lecturas del dashboard** DEBE ser **muestreado a bajo volumen pero completo en cambios de estado**: cada operador genera entradas al conectarse, al ver el primer `event_id` de cada día de datos, y en cada exportación (no por cada frame, para no inundar). |
| **RNF-08.f** | EL SISTEMA DEBE registrar **por separado** los eventos de auditoría (persistentes, 60 meses) de los **logs de aplicación** (efímeros, 14-30 días), con PII prohibida en ambos. |
| **RNF-08.g** | La auditoría DEBE ser **reconstruible**: cada cambio en el documento de Google Sheets puede reconstruirse (qué valor tenía cada KPI/unidad/turno/ranking) sumando los parches desde la línea base del día. |

**Medición:** consulta de auditoría devuelve la secuencia completa de un `event_id` (quién lo generó, quién lo vio); escaneo de logs confirma ausencia de PII (regresión con datos sembrados).

### RNF-09 — Accesibilidad

| ID | Requisito |
|----|-----------|
| **RNF-09.a** | EL SISTEMA DEBE cumplir **WCAG 2.2 nivel AA** para contraste, foco, navegación y semántica. |
| **RNF-09.b** | Contraste mínimo: **≥ 4,5:1** texto normal, **≥ 3:1** texto ≥ 18,66 px bold o ≥ 24 px, y **≥ 3:1** para bordes de componentes y objetos gráficos (barras de gráfico contiguas con etiqueta textual obligatoria). |
| **RNF-09.c** | EL SISTEMA DEBE ofrecer navegación **completa por teclado** (Tab/Shift+Tab, flechas en tabla, Enter/Espacio en elementos accionables) con **foco visible** (≥ 3:1 contra el fondo adyacente). |
| **RNF-09.d** | La información NO DEBE depender **solo del color**: cada estado tiene glifo y/o texto; el ranking usa números de posición; la variación usa flecha + signo. |
| **RNF-09.e** | Los gráficos DEBEN tener **tabla de datos accesible** equivalente (visualmente oculta pero navegable por lector de pantalla) con los mismos valores. |
| **RNF-09.f** | Los valores animados DEBEN anunciar el nuevo valor a lectores de pantalla (`aria-live="polite"`) **una vez** por cambio, no por frame. |
| **RNF-09.g** | Se respeta `prefers-reduced-motion` (RF-05.i) y se provee texto alternativo a cualquier elemento informativo. |
| **RNF-09.h** | Los objetivos táctiles (elementos interactivos) DEBEN tener **≥ 44×44 px**. |

**Medición:** axe-core/Lighthouse sin violaciones críticas; verificación de contraste con los hex de §11.2; navegación 100 % por teclado.

### RNF-10 — Compatibilidad (navegadores y resoluciones)

| ID | Requisito |
|----|-----------|
| **RNF-10.a** | Navegadores soportados: **Chrome/Edge 121+**, **Firefox 122+**, **Safari 17+** (evergreen). |
| **RNF-10.b** | Resoluciones objetivo de sala: **1920×1080** (principal), **2560×1440** y **3840×2160 (4K)**. Retícula fluida que escala sin scroll en ninguna de las tres. |
| **RNF-10.c** | Escalado de DPI soportado **100 %–200 %** sin pérdida de contenido (uso de unidades relativas y `clamp()`); a 200 % en 1920×1080 se activa scroll vertical (aceptado, no se rompe). |
| **RNF-10.d** | Identificadores únicos por instancia de sala (`room_id`) para permitir varias salas sin interferencia (mensajes WSS llevan `room_id`; el cliente filtra). |
| **RNF-10.e** | La SPA DEBE funcionar como **PWA instalable** con *manifest* y *service worker* de **solo shell** (precache del app shell; **jamás** cachear respuestas de API ni datos WSS — ver AM-10). |
| **RNF-10.f** | La App DEBE degradar de forma segura en navegadores sin WebSocket? No aplica: WebSocket es universal en los navegadores soportados; se documenta que `EN VIVO` requiere WebSocket y, si falta, arranca en modo polling (misma lógica que RNF-05.d). |
| **RNF-10.g** | La SPA DEBE ser **accesible también con lector de pantalla y por voz**, sin dependencia de hover (tooltips replicados en tabla accesible). |

### RNF-11 — Idempotencia y consistencia de la actualización visual

| ID | Requisito |
|----|-----------|
| **RNF-11.a** | Cada instantánea lleva un `event_id` **único** (UUIDv7). El backend lo persiste con restricción `UNIQUE`; un reenvío del origen con el mismo `event_id` DEBE devolver el resultado previo (`200`/`202` con `duplicate=true`) **sin volver a aplicar** ni redistribuir. |
| **RNF-11.b** | Cada instantánea lleva un `seq` **monótono creciente por `room_id`** (asignado por el backend). El cliente Aplica **solo si `seq > lastSeq`** (último wins por orden de secuencia); mensajes con `seq ≤ lastSeq` se descartan. |
| **RNF-11.c** | CUANDO el cliente reciba instantáneas **fuera de orden** (p. ej. por reconexión y replay), EL SISTEMA DEBE recomponer el estado aplicando solo la de mayor `seq` por campo y re-solicitando un cold start si detecta un salto de secuencia grande (`Δseq > 50` → pide `GET /snapshot` antes de continuar). |
| **RNF-11.d** | Los KPIs y series son de **semántica de instantánea (valor absoluto del acumulado)**, no de deltas incrementales; esto hace la aplicación **idempotente por construcción** (aplicar dos veces = mismo resultado). |
| **RNF-11.e** | CUANDO dos instantáneas-sequentes tengan el mismo `event_id`, el cliente DEBE ignorar la segunda. |
| **RNF-11.f** | La actualización visual DEBE ser **atómica por evento**: un evento actualiza los 7 visuales de forma consistente; no se muestra un KPI nuevo junto a un ranking viejo tras una misma actualización (se aplican en un único commit de estado React). |

### RNF-12 — Rate limiting, anti-abuso y resiliencia a carga maliciosa

| ID | Requisito |
|----|-----------|
| **RNF-12.a** | Rate limit **webhook**: **200 req/min (≈3,3 msg/s)**, ráfaga **20**, por `webhook_id`; excedente → `429` con `Retry-After`. |
| **RNF-12.b** | Rate limit **REST por operador**: 120 req/min por `sub` (cold start cuenta). |
| **RNF-12.c** | Rate limit **WSS entrante**: máximo **10 msg/s por conexión** y **20 conexiones WSS por token** (anti multiplexación anormal). |
| **RNF-12.d** | Rate limit **conexiones WSS concurrentes**: **50 por sala**, **200 globales**; al exceder, se rechaza con `1013 Try Again Later`. |
| **RNF-12.e** | Rate limit **edge/WAF** por IP para `/ingest` y endpoints de autenticación (p. ej. 60 req/min por IP en login), para mitigar credential stuffing. |
| **RNF-12.f** | EL SISTEMA DEBE limitar el **tamaño de payload** a **64 KB (comprimido) / 256 KB (plano)** por evento de ingesta; excedido → `413`. Rate limits vigentes: webhook **200 req/min** (RNF-12.a), admin **50 req/min** (ver §10.6). |
| **RNF-12.g** | EL SISTEMA DEBE aplicar **límites de conexión y tiempo** (timeouts) por defensa en profundidad: `read_timeout 15 s`, `keepalive` y máximo de conexiones del pool acotados. |

### RNF-13 — Gestión de secretos

| ID | Requisito |
|----|-----------|
| **RNF-13.a** | El secreto de aplicación (secreto del webhook, `JWT_SIGNING_KEY` y credenciales de BD) DEBE residir en un **secret manager** del entorno (integración con el gestor de secretos del proveedor de nube), inyectado como variables de entorno/montajes en runtime; el secreto del webhook se replica en `Script Properties` del lado de Apps Script. |
| **RNF-13.b** | El secreto **NO** se versiona, **NO** aparece en logs, **NO** se expone al bundle del navegador, **NO** se embebe en el código de Apps Script (§9.4). |
| **RNF-13.c** | La rotación de secretos tiene **procedimiento documentado** y **ventana de solapamiento** para no cortar la operación (§9.3). |
| **RNF-13.d** | En desarrollo, los secretos usan **valores de prueba** separados del producción, y un **secret scanning** en CI bloquea el merge si detecta un secreto. |

### RNF-14 — Respaldo y recuperación (RPO/RTO)

| ID | Requisito |
|----|-----------|
| **RNF-14.a** | **RPO (Recovery Point Objective) = 15 minutos**: PITR (Point-In-Time Recovery) de PostgreSQL con archivado continuo de WAL y **snapshot diario**. |
| **RNF-14.b** | **RTO (Recovery Time Objective) = 2 horas**: restaurar desde snapshot+PITR, reconstruir réplicas y Redis (Redis es descartable) y reconectar el webhook y los operadores. |
| **RNF-14.c** | **Backups**: instantáneas cifradas **diarias** (retención 35 días), **semanales** (retención 12 semanas), **mensuales** (retención 24 meses). Los backups se cifran con clave distinta a la de producción. |
| **RNF-14.d** | EL SISTEMA DEBE **verificar la integridad de los backups** (checksum) y **ensayar la restauración** al menos **trimestralmente** (documentando fecha y resultado). |
| **RNF-14.e** | Los backups residen en ** Storage de respaldo cifrado, geográficamente separado**, con acceso solo del rol de servicio de respaldo. |
| **RNF-14.f** | **Usuarios locales**: backup **diario cifrado** de la tabla de usuarios (incluidos los hashes de contraseña) con retención **35 días / 12 semanas / 24 meses** (misma política que PostgreSQL principal). Verificación de integridad y ensayo de restauración **trimestral**. |
| **RNF-14.g** | **Autenticación local HA**: la emisión/verificación de JWT es *stateless* y corre en las réplicas del backend; `JWT_SIGNING_KEY` se distribuye por secret manager; failover automático < 30 s y healthcheck `/health/ready` incluye el acceso al almacén local de usuarios. |

### RNF-15 — Formato, localización y consistencia de datos

| ID | Requisito |
|----|-----------|
| **RNF-15.a** | Interfaz, mensajes de auditoría y exportación en **español**; formato numérico y de fecha local **`es-CL`** (miles `1.234`, decimal `1,5`, fecha `03-10-2026 14:22`), timestamps en el header en **hora local canónica + UTC en tooltip**. |
| **RNF-15.b** | Todos los números de KPI/series son **enteros no negativos**; los porcentajes tienen **2 decimales**; toda variación incluye signo. |
| **RNF-15.c** | CUANDO el backend sirva un dato con esquema/version no soportado por el cliente, DEBE enviar la versión en el evento (§7.7) para que el cliente decida; el cliente rechaza versiones mayores y pide actualización. |

---

## 7. Modelo de datos

### 7.1 Principio de modelado

- El sistema es de **instantáneas absolutas** (snapshot), no de deltas: cada envío describe el estado completo de los indicadores en un instante. Esto elimina la clase de errores de *conteo doble* y hace la actualización idempotente (RNF-11.d).
- Los agregados derivados ("variación vs ayer") se calculan **en el backend** y viajan en el mensaje ya resueltos, para que todos los operadores vean exactamente la misma cifra (fuente única de verdad, sin divergencia por zona horaria del cliente).
- Todas las cantidades son **enteros no negativos**. Toda comparación incluye **ambos** deltas (absoluto y porcentual).

### 7.2 Sobre del mensaje WSS (`indicators.snapshot`)

El mensaje base que el dashboard consume por WebSocket:

```json
{
  "schema_version": "1.0.0",
  "type": "indicators.snapshot",
  "event_id": "018e2a4f-6b1c-7c2d-9f10-5a3b8c7d1e42",
  "seq": 10427,
  "room_id": "sala-central",
  "ts": "2026-10-03T14:22:05.412Z",
  "tz": "America/Argentina/Buenos_Aires",
  "data_date": "2026-10-03",
  "tz_offset_minutes": -240,
  "source": {
    "webhook_id": "wh-sifcop-central",
    "doc_id": "sifcop-resumen",
    "content_sha256": "9f2c1ab4...",
    "sheet_modified_at": "2026-10-03T14:21:58Z"
  },
  "payload": { "...": "§7.3 – §7.6" },
  "correlation_id": "tr-01JQ8Z..."
}
```

Campos clave:

| Campo | Tipo | Regla |
|-------|------|-------|
| `schema_version` | `x.y.z` semver | Mayor → cliente pide actualización; menor → acepta (campos opcionales). |
| `type` | enum | `indicators.snapshot` \| `heartbeat` \| `error` \| `hello` (ver §10.3). |
| `event_id` | UUIDv7 | Único; clave de idempotencia. |
| `seq` | entero | Monótono por `room_id`; ordencanónico de aplicación. |
| `ts` | ISO-8601 UTC | Momento de aceptación backend (reloj autoritativo). |
| `tz` / `tz_offset_minutes` | IANA / int | Zona horaria canónica del dato (la del SIFCOP, no la del navegador). |
| `data_date` | `YYYY-MM-DD` | Día de datos al que corresponde el acumulado (clave para "vs ayer"). |
| `payload` | objeto | Estructura de §7.3 (kpis) + §7.5 (regional) + §7.4 (turnos) + §7.6 (ranking). |

### 7.3 Esquema de los 4 KPIs

```json
"kpis": {
  "total_consultas_sifcop": {
    "label": "Total Consultas SIFCOP",
    "value": 184732,
    "delta_abs": 3120,
    "delta_pct": 1.71,
    "direction": "up",              // "up" | "down" | "flat"
    "comparison": "ayer_mismo_tramo",// base de comparación (ver §7.3.1)
    "baseline_value": 181612,       // acumulado de ayer hasta la misma hora
    "as_of": "2026-10-03T14:22:05Z",
    "has_reference": true
  },
  "personas_capturadas":  { "label": "Personas Capturadas",        "value": 4128, "delta_abs": 218,  "delta_pct": 5.57, "direction": "up",   "comparison": "ayer_mismo_tramo", "baseline_value": 3910,  "as_of": "2026-10-03T14:22:05Z", "has_reference": true },
  "vehiculos_secuestrados":{ "label": "Vehículos Secuestrados",     "value": 37,   "delta_abs": -6,   "delta_pct": -13.95,"direction": "down", "comparison": "ayer_mismo_tramo", "baseline_value": 43,   "as_of": "2026-10-03T14:22:05Z", "has_reference": true },
  "armas_secuestradas":    { "label": "Armas Secuestradas",         "value": 12,   "delta_abs": 2,    "delta_pct": 20.00,"direction": "up",   "comparison": "ayer_mismo_tramo", "baseline_value": 10,   "as_of": "2026-10-03T14:22:05Z", "has_reference": true }
}
```

- `value`: acumulado del día actual hasta `as_of`.
- `delta_abs` = `value − baseline_value`; `delta_pct = round((delta_abs / baseline_value) × 100, 2)`; si `baseline_value == 0` → `delta_pct = null` y `has_reference = true` con `delta_abs = value` (se muestra solo el absoluto). Si **no hay** registro del día anterior → `has_reference = false`, `delta_abs = null`, `delta_pct = null`.
- `direction` se deriva de `delta_abs` (no del porcentaje): `up` si `> 0`, `down` si `< 0`, `flat` si `== 0`.
- La clave canónica de cada KPI (`total_consultas_sifcop`, …) es estable entre versiones; la etiqueta visible (`label`) puede traducirse sin romper clientes.

#### 7.3.1 Base de comparación "variación respecto a ayer" — decisión y nota

Se adopta por defecto **`ayer_mismo_tramo`** (acumulado del día anterior hasta la misma `HH:MM` de reloj, en la zona horaria canónica). Es la comparación operationally más justa: evita que el "drop" matinal o el "pico" nocturno se interpreten como caída o caída real, porque ambas cifras cubren la misma duración acumulada. Se documentan dos alternativas para validación:

| Opción | Definición | Nota |
|--------|-----------|------|
| `ayer_mismo_tramo` **(por defecto / propuesta)** | Acumulado de ayer hasta la misma hora que ahora | Comparable en duración; evita sesgo por hora del día. |
| `ayer_completo` | Total acumulado del día anterior completo | Simple, pero penaliza las mañanas (siempre "baja") y premia las noches. |
| `ayer_total_mismo_tramo_pct` | % sobre el total de ayer | Útil para "participación del día", no para "variación". |

→ **OD-02**: validar `ayer_mismo_tramo` frente a `ayer_completo` con el usuario (y, si aplica, un "contador fijo" que compara contra el total esperado del día, p. ej. meta).

### 7.4 Estructura de la serie de turnos operativos

`turno` = bloque de 8 horas en la zona horaria canónica `America/Argentina/Buenos_Aires`; son **3 turnos** (`MAÑANA` 06–14, `TARDE` 14–22, `NOCHE` 22–06+1) y siempre están en orden cronológico.

```json
"turnos": [
  { "turno_id": "MAÑANA", "inicio_min": 360, "fin_min": 840, "label": "MAÑANA (06-14)", "intervenciones": 231, "variacion_abs": 25, "variacion_pct": 12.14, "estado": "cerrada" },
  { "turno_id": "TARDE",  "inicio_min": 840, "fin_min": 1320,"label": "TARDE (14-22)", "intervenciones": 318, "variacion_abs": 12, "variacion_pct": 3.92,  "estado": "en_curso" },
  { "turno_id": "NOCHE",  "inicio_min": 1320,"fin_min": 360,  "label": "NOCHE (22-06)", "intervenciones": 142, "variacion_abs": -8, "variacion_pct": -5.33, "estado": "pendiente" }
]
```

- `estado ∈ {pendiente, en_curso, cerrada}` (sección RF-04.b): `pendiente` = el turno aún no ha ocurrido (dato no disponible, no 0); `en_curso` = contiene la hora actual; `cerrada` = ya pasó.
- `variacion_*` de cada turno compara **el valor de ese turno hoy** contra **el mismo turno ayer** (`ayer_mismo_turno`).
- Las claves canónicas son `turno_id ∈ {MAÑANA, TARDE, NOCHE}`; el orden canónico es `MAÑANA → TARDE → NOCHE`.
- Nota: el turno NOCHE cruza medianoche (`fin_min < inicio_min`); la fecha lógica del turno es la **fecha de inicio** (p. ej. turno 22:00 del 15/10 → 06:00 del 16/10 se guarda como `fecha_turno: "2025-10-15", turno_id: "NOCHE"`).

### 7.5 Estructura de la serie regional (5 unidades)

```json
"regional": [
  { "unidad_id": "capital", "label": "Capital", "intervenciones": 268, "variacion_abs": 22, "variacion_pct": 8.93, "rank": 1 },
  { "unidad_id": "sur",    "label": "Sur",    "intervenciones": 142, "variacion_abs": -5, "variacion_pct": -3.40,"rank": 2 },
  { "unidad_id": "este",   "label": "Este",   "intervenciones": 98,  "variacion_abs": 7,  "variacion_pct": 7.74,  "rank": 3 },
  { "unidad_id": "oeste",  "label": "Oeste",  "intervenciones": 71,  "variacion_abs": -3, "variacion_pct": -4.05,"rank": 4 },
  { "unidad_id": "norte",  "label": "Norte",  "intervenciones": 34,  "variacion_abs": 1,  "variacion_pct": 3.03,  "rank": 5 }
]
```

- Catálogo cerrado de **5 unidades** (`capital`, `sur`, `este`, `oeste`, `norte`) con su etiqueta visible; una unidad no recibida se renderiza con 0 (RF-03.e), una unidad desconocida se descarta (RF-03.h).
- `rank` es derivado del orden por `intervenciones` descendente (desempate alfabético), consistente con `turnos`/regional.

### 7.6 Estructura del ranking Top 5

```json
"ranking": {
  "top_n": 5,
  "dependencias": [
    { "puesto": 1, "dependencia_id": "com-12",  "comisaria": "Comisaría 12",      "intervenciones": 94,  "variacion_abs": 12, "variacion_pct": 14.63, "puesto_previo": 2 },
    { "puesto": 2, "dependencia_id": "com-07",  "comisaria": "Comisaría 7",       "intervenciones": 88,  "variacion_abs": -4, "variacion_pct": -4.35, "puesto_previo": 1 },
    { "puesto": 3, "dependencia_id": "com-03",  "comisaria": "Comisaría 3",       "intervenciones": 81,  "variacion_abs": 5,  "variacion_pct": 6.58,  "puesto_previo": 3 },
    { "puesto": 4, "dependencia_id": "dep-norte","comisaria": "Dependencia Norte", "intervenciones": 74,  "variacion_abs": 1,  "variacion_pct": 1.37, "puesto_previo": 5 },
    { "puesto": 5, "dependencia_id": "com-21",  "comisaria": "Comisaría 21",      "intervenciones": 69,  "variacion_abs": -6, "variacion_pct": -8.00,"puesto_previo": 4 }
  ]
}
```

- `puesto_previo` habilita el destello de cambio de posición (RF-04.g) y la auditoría de "quién vio un reordenamiento".
- Se incluyen **hasta 5** dependencias; nunca filas de relleno (RF-04.h).

### 7.7 Estructura completa del `payload` (ensamblado)

```json
"payload": {
  "kpis": { /* §7.3 → 4 tarjetas */ },
  "regional": [ /* §7.5 → 5 barras horizontales */ ],
  "turnos": [ /* §7.4 → 3 turnos */ ],
  "ranking": { /* §7.6 → tabla Top 5 */ },
  "freshness": {
    "last_event_ts": "2026-10-03T14:22:05.412Z",
    "sheet_modified_at": "2026-10-03T14:21:58Z",
    "stale": false, "age_seconds": 0
  },
  "quality": { "partial": false, "source_rows": 5, "warnings": [] }
}
```

- `freshness.stale` lo computa el **cliente** a partir de `last_event_ts` y su reloj (con la tolerancia de deriva de §13); el backend lo incluye como hint.
- `quality.partial = true` si el backend observa un agregado de una fuente degradada (p. ej. solo 3 de 5 unidades); el cliente muestra un aviso no bloqueante.

### 7.8 Versionado del esquema de mensajes y cambios de contrato

| Regla | Detalle |
|-------|---------|
| **Semver del mensaje** | `schema_version` semver. `MAJOR.MINOR.PATCH`. |
| **Major** (cambio incompatible: campo renombrado/eliminado, tipo cambiado, unidad cambiada) → cliente rechaza (`410` en REST o cierra WSS con `4010`) y exige recarga; el backend publica `/schema/messages/{version}`. |
| **Minor** (campo opcional nuevo) → cliente anterior **tolera** el campo desconocido (lo ignora) y sigue funcionando; cliente nuevo **debe** ser capaz de trabajar con el payload sin el campo nuevo (valor por defecto). |
| **Patch** (fix editorial, p. ej. `label` más largo, descripción de un tooltip) → transparente. |
| **Campos desconocidos** | El cliente los **ignora** y los registra en consola como `warn` (no rompen). |
| **Campos obligatorios ausentes o tipos inválidos** | El cliente **rechaza el evento completo** (fail-closed), registra y mantiene el último estado válido (no parcial). |
| **Evolución de la clave de KPI/dependencia/unidad** | Se mantiene la clave canónica estable; se **añaden** claves, no se renombran, dentro de un major. |
| **Publicación del esquema** | El backend sirve el JSON Schema del mensaje en `/schema/messages/1.0.0`; CI valida que el ejemplo cumple el esquema. |
| **Ventana de soporte** | El backend soporta las **dos últimas minors** del cliente en coexistencia durante despliegues; el cliente (SPA) se despliega antes que el backend para evitar incompatibilidades. |

### 7.9 Modelo de almacenamiento (resumen)

| Relación | Propósito | Retención | Notas |
|----------|-----------|-----------|-------|
| `ingest_event` | Cabecera de cada evento recibido | 90 días | `event_id` UNIQUE, `payload_ciphertext` (AES-256-GCM), `content_sha256`. |
| `snapshot_current` | Último payload aceptado por `doc_id` | permanente (1 fila/doc) | Se sobrescribe; base del cold start. |
| `agg_hourly` | Agregado por hora, unidad, turno, KPI | 60 meses | Alimenta histórico y "vs ayer". |
| `agg_daily` | Agregado por día (para baselines "ayer") | 60 meses | Alimenta `baseline_value` de KPIs y `variacion` de turnos. |
| `ranking_snapshot` | Top 5 por día/turno (histórico de ranking) | 60 meses | Alimenta `puesto_previo`. |
| `audit_event` | Bitácora append-only (RNF-08) | 60 meses | Roles de servicio sin UPDATE/DELETE. |
| `webhook_registry` | Webhooks de Google Sheets, estado, documento asociado, revocación | permanente | Secreto en el secret manager; en BD solo metadata. |
| `webhook_secret` | Versiones del secreto del webhook (`key_id`, estado, fechas) | permanente | `key_id` del mensaje apunta aquí. |

---

## 8. Modelo de seguridad y amenazas

Clasificación **STRIDE** por activo. La columna "Mitigaciones" referencia los RF/RNF y las secciones donde se aplica. `AM-xx` es el identificador de amenaza usado en la trazabilidad (§15).

| ID | Amenaza (STRIDE) | Activo afectado | Descripción / vector | Impacto | Mitigación concreta | RF / RNF |
|----|------------------|------------------|----------------------|---------|----------------------|----------|
| **AM-01** | Spoofing / Elevación | Dashboard | Un usuario no autenticado o con rol insuficiente accede al panel; o un `viewer` manipula parámetros para ver unidades/periodos no autorizados. | Filtración de intelligence | **Login nativo (usuario+contraseña) obligatorio; JWT validado (firma/aud/exp/nbf)**; **RBAC por capacidad en servidor** (fail-closed); el navegador no decide autorización; 403 sin revelar qué datos existen; CORS allowlist. | RNF-03.a..c, RF-02.k, P1/P3/P6 |
| **AM-02** | Elevación de privilegios | Identidades / Roles | Un `viewer` o `auditor` escala a `platform-admin` (o un admin intenta ver datos que no le tocan) mediante manipulated de claims, rol en caché, o endpoint sin control. | Control total de la plataforma o acceso a intelligence no autorizado | Capacidades ortogonales (no "admin ve todo"); **roles de datos y de plataforma separados**; fuente de roles = **tabla local del backend**, nunca el cliente; re-verificación de rol al abrir WSS y periodicamente; auditoría de cada denied. | RNF-03.c/h, §2.2.3, RF-02.k |
| **AM-03** | Information Disclosure / MITM | Canal WSS / REST | Interceptación o desvío del tráfico (roaming hostil, proxy malicioso, TLS roto en un salto) para leer o alterar el flujo de indicadores. | Lectura/alteración de intelligence en tránsito | TLS 1.3 only + HSTS + `sslmode=verify-full`; WSS exclusivamente; sin cadena insegura; el tramo Apps Script→backend va **firmado con HMAC-SHA256** (integridad/autenticidad aunque el TLS del tramo se rompa); datos agregados mínimos. | RNF-01.a..g, §9.1 |
| **AM-04** | Spoofing (origen) | Identidad del webhook | Un atacante que robe el **secreto compartido** del webhook se hace pasar por Apps Script e inyecta cifras falsas (suplantar la fuente). | Inyección de datos falsos en sala de operaciones | **Firma HMAC-SHA256** con comparación en tiempo constante; `webhook_id` activo/no revocado y `key_id` vigente; anti-replay por nonce + timestamp; secreto en `Script Properties`/secret manager, **nunca versionado**; rotación con solape y revocación individual sin downtime global; auditoría con `webhook_id` + origen. | RF-01.e/f/h/k, RNF-03.f, §9.4 |
| **AM-05** | Tampering / Replay | Mensajes WSS y webhook | Un atacante **reemplaza** un mensaje o **reenvía** eventos previamente capturados para alterar cifras o simular actividad. | Cifras erróneas en pantalla | **Firma HMAC-SHA256** (detecta cualquier alteración y acredita el origen); anti-replay por nonce + ventana temporal; `event_id` UNIQUE (idempotencia en ingesta); `seq` monótono (descartar `≤ lastSeq`); almacenamiento append-only (historial inalterable) + replay reconstructivo; comparación de hash de contenido. | RF-01.f/k, RNF-11.a..e, RNF-05.g |
| **AM-06** | Injection (XSS) | Dashboard / navegador | Contenido malicioso en **celdas de Google Sheets** (p. ej. `<script>`, `javascript:`, HTML en nombres de comisaría) se inyecta en el dashboard y se ejecuta en el navegador del operador. | Secuestro de sesión del operador, robo de token | **Sanitización estricta y React escape-by-default** (nunca `dangerouslySetInnerHTML`); CSP estricta sin `unsafe-inline`; validación de longitud y charset en el backend; las etiquetas de unidad/turno son de catálogo **fijo** (allowlist), no texto libre; auditoría de `rejected_unknown_unit`. | RF-03.h, RNF-09, §2.2.5, AM-05 |
| **AM-07** | Denial of Service | Backend / WSS | (a) Flood de mensajes del webhook o de un atacante con el secreto del webhook; (b) **datos maliciosos** (payload enorme, turnos/unidades inexistentes, turnos con valores absurdos) que degradan o rompen el render; (c) inundación de conexiones WSS. | Panel caído o inutilizable en sala de operaciones | Rate limiting multinivel (webhook, por `sub`, por conexión, WAF por IP); límites de tamaño de payload (64 KB/256 KB) → 413; validación de rangos y catálogos; `seq` monotónico; alertas por tasa de rechazo; el WSS es de solo *push* (el cliente no escribe). | RNF-12.a..f, RF-03.h, §13 |
| **AM-08** | Tampering (origen) | Documento Google Sheets | Manipulación del documento en el origen (cifras alteradas antes de que Apps Script las lea) o edición no autorizada. | Publicación de cifras falsas como oficiales | Apps Script **solo lee** el rango declarado y calcula `content_sha256`; toda versión se archiva (append-only) y es **auditable/reconstructible**; permisos de la **cuenta estándar de Google** restringidos (solo analistas autorizados); el hash y la **firma HMAC** permiten demostrar alteración y acreditar el origen (`webhook_id`). | RF-01.c/h, §1.6, RNF-08.g, §9 |
| **AM-09** | Information Disclosure (exfiltración) | Datos sensibles | Filtración de intelligence a terceros: Insider con acceso legítimo exporta o fotografía; API mal configurada sirve de más; CSV/backup expuesto. | Difusión no controlada de datos sensibles | Clasificación de sensibilidad (§2.0); mínimo privilegio + capacidades (exportar exige `dash.export.csv` y se audita, sin step-up); `Cache-Control: no-store` + `Clear-Site-Data` al logout; WAF/rate limit; CSV con marcas de agua de auditoría; backups cifrados y separados. | §2.0, RNF-03.g, RNF-08.a/e, RNF-13 |
| **AM-10** | Information Disclosure (caché) | Cliente / Cloudflare Pages | El **Service Worker / caché del navegador o del edge** sirve respuestas con datos a un usuario que **ya cerró sesión** (datos cacheados legibles por quien reutilice el perfil/navegador). | Datos sensibles visibles tras deslogueo | `no-store, private` en toda respuesta de API/datos; el Service Worker **solo** precachea el app shell (nunca `/api` ni tramas WSS); `Clear-Site-Data` en logout; política de Cloudflare Pages sin caché de API (la API está en otro origen). | RNF-10.e, §2.2.5 |
| **AM-11** | Spoofing / UI Redress (Clickjacking) | Dashboard | Un sitio externo **encuadra** el dashboard en un `iframe` para que el operador interactúe sin saberlo (clickjacking) o inyecta clicks falsos. | Acciones no intencionadas del operador | Cabecera **`X-Frame-Options: DENY`** y CSP `frame-ancestors 'none'`; sin *framing* por terceros; `Same-Origin-Policy`/`Cross-Origin-Opener-Policy` estrictos. | RNF-09, §2.2.5, AM-12 |
| **AM-12** | Spoofing (CSRF) / Forgery | API REST | Un sitio externo hace que el navegador autenticado envíe solicitudes con las credenciales del operador (p. ej. exportar histórico o invocar un endpoint). | Acción no intencionada con la identidad del operador | Tokens **no** en cookies de sesión automate (bearer en memoria); API en **otro origen** que la SPA + `SameSite=Strict` cuando aplique; **anti-CSRF token** en cualquier mutación; CORS con allowlist exacta; 요구 de `Content-Type: application/json` + preflight; `credentials` no se envía a terceros. | RNF-03, §2.2.2 |
| **AM-13** | Repudiation (falsificación de authorship) | Cadena de datos | Un origen malicioso/robo de secreto intenta que una cifra parezca venir del sistema oficial, o un operador niega haber consultado datos. | Pérdida de confianza en la cadena | Cada evento lleva `webhook_id` + **firma HMAC-SHA256** + `correlation_id` + `ts` autoritativa; auditoría append-only de envíos y de **lecturas** (quién vio qué); los eventos de lectura se asocian a `event_id`s vistos. | RNF-08.a/b/e, RF-01.h, RF-02.j |
| **AM-14** | Information Disclosure (secreto en reposo) | Código de Apps Script / repositorio | El secreto del webhook queda expuesto en el código de Apps Script versionado, en un repositorio o en logs, permitiendo suplantar el origen. | Compromise total de la cadena de ingesta | Secreto en **`Script Properties`** (Apps Script) y en el **secret manager** (backend); **nunca** en el código ni en el repo; `secret scanning` en CI; rotación con solape; en la base de datos solo metadata. | §9.2/§9.4, RNF-02.b/e, AM-04 |

---

## 9. Gestión de claves y secretos

### 9.1 Autenticación del webhook: **HMAC-SHA256** — decisión y justificación

Se elige **HMAC-SHA256** (RFC 2104) como mecanismo de **autenticación del origen e integridad** del webhook Apps Script → backend, con un **secreto compartido** por origen.

Justificación frente a la alternativa de **cifrado simétrico AES-256-GCM a nivel aplicación**:

| Criterio | HMAC-SHA256 (elegido) | AES-256-GCM a nivel app (descartado para el webhook) |
|----------|-----------------------|------------------------------------------------------|
| **Objetivo** | Autentica el **origen** y garantiza **integridad** del payload; la confidencialidad la aporta TLS 1.3. | Aporta confidencialidad en el tramo, que ya cubre TLS 1.3, y **no** sustituye la autenticación del origen. |
| **Simplicidad** | Una sola primitiva y un solo secreto; el payload permanece JSON para validación y auditoría. | Obliga a gestionar clave de datos, KEK, sobre binario y descifrado previo a la validación. |
| **Riesgo de implementación** | Bajo: comparación en tiempo constante de un digest; soporte nativo en Apps Script (`Utilities.computeHmacSha256Signature`) y en el backend. | Mayor superficie (nonce, envelope, tag, custodia de clave) sin ventaja al ir el canal ya cifrado por TLS. |
| **Fail-closed** | Firma inválida → `401` **antes** de deserializar; explícito y auditable. | Tag inválido → `401`; igual de explícito pero con más piezas. |
| **Rotación** | Secreto versionado (`key_id`) con solape de 24 h sin redesplegar el origen. | Requiere re-envoltura (re-wrap) de clave y coordinación adicional. |

**Conclusión:** como el transporte es TLS 1.3 obligatorio, el problema real del tramo Apps Script→backend es **autenticar el origen**, y HMAC-SHA256 lo resuelve con menos superficie y sin custodiar claves de datos en el origen. Se mantiene **AES-256-GCM en reposo** (§RNF-02.a) para las instantáneas almacenadas.

**Metadatos firmados:** la firma cubre el **cuerpo canónico** y los metadatos (`webhook_id`, `key_id`, `nonce`, `timestamp`, `schema_version`), de modo que un atacante no puede mover un payload válido a otro origen, versión o timestamp sin romper la firma.

### 9.2 Firma (cadena canónica) y dónde vive el secreto

- Cada webhook viaja acompañado de su firma:

```text
firma = HMAC-SHA256(secreto, canonical_string)
canonical_string = "{webhook_id}|{key_id}|{nonce}|{timestamp}|{schema_version}|{sha256(cuerpo)}"
X-Webhook-Signature: sha256=<hex>
```

- El **secreto compartido** (`key_id` referenciado en la cabecera) es una cadena aleatoria de 256 bits generada por el backend.
- **Dónde vive el secreto (Apps Script):** en **`Script Properties`** (almacén de propiedades del script, cifrado en reposo y asociado al script/contenedor de Google). No se escribe en el código `.gs` ni en `appsscript.json` versionado; no se comparte entre documentos.
- **Dónde vive el secreto (backend):** en el **secret manager** del entorno, inyectado en runtime. En la base de datos solo se guarda metadata de `webhook_secret` (`key_id`, estado, fechas); **nunca** el material del secreto. La tabla `webhook_secret` permite alinear el `X-Webhook-Key-Id` del mensaje con el secreto vigente.
- El backend **recalcula la firma** sobre el cuerpo canónico y la compara en **tiempo constante**; el resultado (aceptado/rechazado) se audita. El secreto no se persiste en claro ni se registra en logs.

### 9.3 Rotación de claves

| Elemento | Periodicidad / disparador | Procedimiento | Impacto en operación |
|----------|----------------------------|---------------|------------------------|
| **Secreto del webhook** (`key_id`) | **Cada 90 días** o ante sospecha/compromiso | El admin genera una nueva versión en `webhook_secret` (nueva `key_id`); el backend publica la lista de `key_id` aceptados; el administrador actualiza el secreto en `Script Properties`. El webhook siguiente usa la nueva `key_id`. | **Ninguno**: solapamiento de **24 h** en que el backend acepta el secreto antiguo y el nuevo. |
| **Secreto de cifrado en reposo (pgcrypto)** | **Cada 90 días** o ante compromiso | Se añade la nueva clave al secret manager y se re-cifran las columnas afectadas; se retira la antigua tras el solapamiento. | Ninguno (re-cifrado por lotes). |
| **Tokens de sesión / refresh** | Access 15 min; refresh **indefinido con actividad** (rotativo, sin TTL fijo); rotación por reutilización | Automática; el refresh rotativo con detección de reutilización revoca la cadena si se detecta robo. | Transparente para el operador. |
| **Clave de firma JWT (`JWT_SIGNING_KEY`)** | **Cada 90 días** o ante compromiso | Se genera una nueva clave en el secret manager y se acepta la anterior en solape durante la vida del access token (≤ 15 min); el refresh re-emite los tokens. | Ninguno (tokens vigentes expiran solos). |
| **Cifrado de backups** | Clave independiente de producción | Clave nueva por ciclo de backups; se conserva la clave histórica necesaria para restaurar cada copia. | Ninguno. |

La rotación del **secreto del webhook** **no** requiere redesplegar el origen (Apps Script) ni la SPA: basta con actualizar `Script Properties` (Apps Script) y el secret manager (backend).

### 9.4 Por qué el secreto NO va en el código de Apps Script ni en el repositorio

El código del script (`.gs`, `appsscript.json`) es un artefacto que se **comparte con el proyecto del documento**, se **copia entre documentos** y queda **en claro en el editor y en los repositorios**. Embeber el secreto en él tendría consecuencias inaceptables:

| Si el secreto está en el código… | Consecuencia |
|------------------------------------|-------------|
| Se puede extraer leyendo el proyecto de Apps Script o su historial de versiones. | Cualquiera con acceso al script obtiene el secreto. |
| El secreto es **compartido por el código desplegado**. | El compromiso de una copia del script compromete la fuente: no hay atribución individual. |
| Cambiar el secreto obliga a **editar, versionar y redesplegar** el script. | La rotación se vuelve lenta y propensa a fallar → en la práctica **el secreto casi nunca rota**, anulando el control. |
| El código se cachea, se copia y se versiona (repositorio, historial de Apps Script). | El secreto queda **persistente** en copias y en el historial. |
| Violaría el principio de **mínimo privilegio** y de **atribución**. | No se puede distinguir una notificación legítima de una suplantada. |

**Solución adoptada:** el secreto se genera y custodia en el **backend** (secret manager), se comparte con el origen a través de un canal gobernado y se guarda en **`Script Properties`** del script (cifrado en reposo por Google, con ámbito del script). El código **no contiene ningún material secreto** y se puede versionar sin riesgo. Cada origen tiene su propio `webhook_id`/`key_id`, de modo que la revocación es individual.

### 9.5 Inventario de secretos y su custodia

| Secreto | Dónde vive (custodia) | Rotación | Exposición prohibida |
|---------|------------------------|----------|----------------------|
| Secreto del webhook (firma HMAC) | Secret manager (backend); `Script Properties` (Apps Script) | 90 días (solape 24 h) | Código `.gs`/`appsscript.json`, repositorio, logs, bundle web |
| Clave de cifrado en reposo (pgcrypto) | Secret manager (backend) | 90 días | Base de datos, `.env` versionado, logs |
| Credenciales del almacén | Secret manager → variable de entorno del backend | 90 días | Código, base de datos, logs |
| Clave de firma JWT (`JWT_SIGNING_KEY`) | Secret manager (backend) | 90 días (con solape) | Código, `.env` versionado, bundle web, logs |
| Hashes de contraseñas locales (Argon2id) | Tabla de usuarios (PostgreSQL) | por cambio de contraseña | Logs, respuestas HTTP, backups sin cifrar |
| Clave de cifrado de backups | Secret manager (dominio de respaldo) | por ciclo | Copias de producción |
| Credenciales de Redis | Secret manager | 90 días | Logs, código |
| Credenciales de la service account de Google (solo lectura, reconciliación) | Secret manager | 90 días | Código, repositorio, logs |

**Regla transversal:** ningún secreto se imprime en logs, se devuelve en respuestas HTTP, se incluye en el bundle del navegador ni se versiona. Un *secret scanning* en CI bloquea cualquier commit que introduzca un valor plausible de secreto.

---

## 10. Contrato de API

Convención: todos los endpoints bajo `/api/v1`. Formato `application/json; charset=utf-8`. Errores con cuerpo uniforme:

```json
{ "error": { "code": "CAPACIDAD_DENEGADA", "message": "…", "correlation_id": "tr-…" } }
```

### 10.1 REST — Ingesta del webhook

#### `POST /api/v1/ingest/webhook`

Autenticación: firma `HMAC-SHA256` con secreto compartido (§9.1–§9.2).
Transporte: HTTPS sobre TLS 1.3; el cuerpo viaja en JSON firmado (sin cifrado de aplicación adicional).

**Request (cabeceras):**

```http
POST /api/v1/ingest/webhook HTTP/1.1
Host: api.<dominio-gob>
X-Webhook-Id: wh-sifcop-central
X-Webhook-Key-Id: wk-2026-10
X-Webhook-Nonce: 7f3c9a2b1d8e4c6f5a0b3d9e8c7f6a1b
X-Webhook-Timestamp: 2026-10-03T14:22:05Z
X-Webhook-Version: 1.0.0
X-Webhook-Signature: sha256=9f2c1ab4…
X-Correlation-Id: tr-01JQ8Z…
Content-Type: application/json
```

**Request (cuerpo lógico, firmado; el backend lo verifica antes de deserializar):**

```json
{
  "schema_version": "1.0.0",
  "event_id": "018e2a4f-6b1c-7c2d-9f10-5a3b8c7d1e42",
  "doc_id": "sifcop-resumen",
  "sheet_modified_at": "2026-10-03T14:21:58Z",
  "data_date": "2026-10-03",
  "tz": "America/Argentina/Buenos_Aires",
  "content_sha256": "9f2c1ab4…",
  "payload": { "kpis": {…}, "regional": […], "turnos": […], "ranking": {…} }
}
```

**Response `202 Accepted`:**

```json
{
  "status": "accepted",
  "duplicate": false,
  "event_id": "018e2a4f-6b1c-7c2d-9f10-5a3b8c7d1e42",
  "seq": 10427,
  "received_at": "2026-10-03T14:22:06Z",
  "correlation_id": "tr-01JQ8Z…"
}
```

**Códigos de estado:**

| Código | Significado | Acción del origen (Apps Script) |
|--------|-------------|----------------------------------|
| `202` | Aceptado y redistribuido. | Confirmar y registrar en el log de ejecución. |
| `200` | Aceptado, pero **duplicado** (`event_id` ya visto); `duplicate: true`. | Tratar como éxito (idempotencia). |
| `400` | Cuerpo malformado / versión no soportada. | No reintentar; registrar y alertar (bug de normalización). |
| `401` | **Firma HMAC inválida** (o ausente); no se deserializa. | Alertar y rotar/verificar el secreto. |
| `403` | Webhook revocado o `key_id` no vigente. | Alertar al administrador; detener envíos hasta verificar. |
| `409` | Anti-replay: nonce repetido o timestamp fuera de ventana. | Regenerar nonce y reintentar **una** vez. |
| `413` | Payload > 256 KB (plano) / > 64 KB (comprimido). | Reducir/dividir; alertar. |
| `422` | Esquema/rangos inválidos (KPI negativo, unidad/turno no permitida). | No reintentar; alertar (`rejected_*`). |
| `429` | Rate limit (200 req/min, ráfaga 20). | Reintentar tras `Retry-After`. |

#### Provisión y rotación del secreto del webhook

El `platform-admin` genera/rota el secreto mediante `POST /api/v1/admin/webhook/secret/rotate` (capacidad `platform.manage_webhook`): el backend responde `201` con `{ "webhook_id": "wh-sifcop-central", "key_id": "wk-2026-10", "secret": "<secreto>", "overlap_until": "…" }`. El secreto se muestra **una sola vez** y se configura en `Script Properties` del script de Apps Script. La rotación mantiene vigentes el secreto anterior y el nuevo durante **24 h**.

### 10.2 REST — Operador (dashboard)

Autenticación: `Authorization: Bearer <JWT nativo>`. Autorización: **capacidad por endpoint** (fail-closed). CORS: allowlist exacta de orígenes de la SPA.

#### `GET /api/v1/dashboard/snapshot` — **cold start**

Capacidad: `dash.view.live`. Consulta: `?tz=<IANA>&room_id=<id>` (opcionales; `tz` por defecto la canónica).

**Response `200`:**

```json
{
  "schema_version": "1.0.0",
  "type": "indicators.snapshot",
  "event_id": "018e2a4f-…",
  "seq": 10427,
  "room_id": "sala-central",
  "ts": "2026-10-03T14:22:05.412Z",
  "tz": "America/Argentina/Buenos_Aires",
  "data_date": "2026-10-03",
  "payload": { "kpis": {…}, "regional": […], "turnos": […], "ranking": {…}, "freshness": {…}, "quality": {…} },
  "correlation_id": "tr-…"
}
```

| Código | Significado |
|--------|-------------|
| `200` | OK. |
| `401` | Token ausente/inválido/expirado. |
| `403` | Sin capacidad `dash.view.live`. |
| `409` | Hay un snapshot más nuevo disponible vía WSS (el cliente puede proceder; informativo). |
| `503` | Backend no listo (arranque o mantenimiento). |

#### `GET /api/v1/dashboard/history` — histórico

Capacidad: `dash.view.history`. Query: `from`, `to` (ISO), `bucket=hour|day`, `unit` (opcional), `timezone`. Límite: rango máximo **90 días** para `supervisor`, **60 meses** para `auditor` (retiro por defecto 90 días; ver OD-07).

**Response `200`:** `{ "series": [ { "ts": "2026-10-03T14:00:00Z", "kpis": {…}, "regional": […] } ], "meta": { "bucket": "hour", "count": 720 } }`

| Código | Significado |
|--------|-------------|
| `200` / `400` (rango inválido) / `401` / `403` / `429` (rate limit) |

#### `GET /api/v1/dashboard/export.csv` — exportación

Capacidad: `dash.export.csv` (se **audita**; sin step-up). Genera CSV de agregados con cabecera de auditoría (`generado_por`, `event_id_base`, `ts`). Se **audita** (AM-09). `200 text/csv` / `401` / `403` / `429`.

#### `GET /api/v1/audit/events` — auditoría

Capacidad: `audit.view`. Query: `from`, `to`, `actor`, `action`, `event_id`. `200` con la lista (sin PII, §RNF-08.c). `401`/`403`.

### 10.3 WebSocket Seguro (WSS) — contrato

- **Endpoint:** `wss://api.<dominio-gob>/ws/dashboard`.
- **Apertura:** el cliente primero obtiene un **ticket de un solo uso** con `POST /api/v1/auth/ws-ticket` (capacidad `dash.view.live`, JWT válido) → `{ "ticket": "tkt_…", "expires_in": 60 }`. Luego abre `wss://…/ws/dashboard?ticket=tkt_…`. El ticket **encarna** `sub`, capacidades, `room_id`; es de **un solo uso** y TTL **60 s**. (No se viaja el token de sesión en la URL para no filtrarlo en logs del edge.)
- **Autorización al abrir:** si el JWT ya no es válido o la capacidad cambió → se acepta el socket y se cierra con `4403` (para que el cliente distinga "recuperable" de "prohibido").
- **Mensajes servidor→cliente (JSON, texto):**

```json
{"type":"hello","room_id":"sala-central","schema_version":"1.0.0","server_ts":"2026-10-03T14:22:07Z","last_seq":10427,"heartbeat_interval_s":15}
{"type":"indicators.snapshot","schema_version":"1.0.0","event_id":"…","seq":10428,"room_id":"…","ts":"…","payload":{…}}
{"type":"heartbeat","server_ts":"2026-10-03T14:22:22Z","seq_hint":10428}
{"type":"error","code":"PAYLOAD_INVALID","correlation_id":"tr-…"}
```

- **Mensajes cliente→servidor:** el cliente **no envía datos de negocio**. Solo `{"type":"ping","t":"<epoch_ms>"}` para *keepalive* de aplicación y, opcionalmente, `{"type":"ack","seq":N}` (métrica de entrega). Ignorar/no requerir el `ack`.
- **Heartbeat / Keepalive:** servidor envía `heartbeat` (o `ping`) **cada 15 s**; si el cliente no registra actividad del servidor en **45 s**, either el servidor o el cliente cierran y reconectan (RNF-05.b). El cliente envía `ping` de aplicación cada 15 s.
- **Orden e idempotencia en el canal:** cada mensaje lleva `seq` monótono; el cliente aplica solo `seq > lastSeq` (RNF-11.b). Un hueco grande (`Δseq > 50`) hace que el cliente pida un cold start para rellenar.
- **Reconexión (a cargo del cliente):** backoff exponencial 1→30 s con jitter ±20 % (RNF-05.a); ante `4003`/`4401` → **re-autenticar y obtener ticket nuevo** (refrescar token) antes de reconectar; tras 60 s sin éxito → **degradar a polling** (§RNF-05.d).
- **Códigos de cierre relevantes:**

| Código | Significado | Reacción del cliente |
|--------|-------------|---------------------|
| `1000` | Cierre normal. | Reconectar con backoff (p. ej. rotación de token). |
| `1001` | Going away (mantenimiento). | Reconectar con backoff. |
| `1008` | Violación de política (rate limit de conexión). | Backoff largo (≥ 30 s). |
| `1009` | Mensaje demasiado grande. | Bug; no reintentar igual. |
| `4001` | Heartbeat/keepalive expirado. | Reconectar inmediato. |
| `4003` | Capacidad revocada / no autorizado. | Re-autenticar; si persiste → pantalla de acceso denegado. |
| `4401` | Ticket inválido/expirado/ya usado. | Pedir ticket nuevo (y refrescar token si expiró). |
| `4403` | Rol/capacidades cambiaron desde la apertura. | Re-autenticar y reabrir. |

### 10.4 REST — Salud y observabilidad

| Endpoint | Acceso | Significado |
|----------|--------|-------------|
| `GET /health/live` | público (edge) | El proceso está vivo → `200 { "status": "ok" }`. |
| `GET /health/ready` | red interna | BD + Redis accesibles → `200` / `503`. |
| `GET /metrics` | **solo red interna** | Métricas Prometheus. No público en el edge. |
| `GET /schema/messages/{version}` | autenticado | JSON Schema del contrato de mensaje (§7.8). |

### 10.5 Códigos de estado HTTP comunes

`200` OK · `201` Created (provisión de secreto de webhook) · `202` Accepted (ingesta) · `204` No Content (logout) · `400` Bad Request · `401` Unauthorized (no autenticado/firma inválida) · `403` Forbidden (autenticado sin capacidad / webhook revocado) · `404` Not Found · `409` Conflict (duplicado/anti-replay) · `413` Payload Too Large · `422` Unprocessable (esquema) · `429` Too Many Requests · `500` Internal · `503` Unavailable (no listo / mantenimiento).

### 10.6 REST — Autenticación nativa y gestión de usuarios locales

La autenticación es **nativa del backend** (no hay Keycloak/IdP). Las contraseñas se almacenan como hash **Argon2id**; el login emite JWT de acceso corto + refresh rotativo y aplica bloqueo por intentos.

#### Endpoints de autenticación

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `/api/v1/auth/login` | `POST` | público (+ rate limit por IP/usuario) | Valida usuario/contraseña, aplica bloqueo por intentos; responde `200` `{access_token, refresh_token, expires_in, capabilities}` o `401`. |
| `/api/v1/auth/refresh` | `POST` | refresh token | Rota el refresh con *reuse detection* (reuso revoca la cadena); responde nuevos tokens o `401`. |
| `/api/v1/auth/logout` | `POST` | JWT | Revoca el refresh y cierra los WSS activos del usuario; `204`. |
| `/api/v1/auth/ws-ticket` | `POST` | JWT (capacidad `dash.view.live`) | Ticket de un solo uso (TTL 60 s) que encarna `sub`+capacidades+`room_id` (§10.3). |

#### Gestión de usuarios locales

Protegidos por capacidad `platform.manage_users`; el backend escribe directamente en el almacén local (**sin** proxy a Keycloak).

| Endpoint | Método | Capacidad | Descripción |
|----------|--------|-----------|-------------|
| `/api/v1/admin/users` | `GET` | `platform.manage_users` | Listar usuarios (paginado, filtro por rol/estado) |
| `/api/v1/admin/users` | `POST` | `platform.manage_users` | Crear usuario local (`username`, nombre, `roles[]`; contraseña inicial) |
| `/api/v1/admin/users/{userId}` | `GET` | `platform.manage_users` | Detalle de usuario (roles, capacidades derivadas, último login) |
| `/api/v1/admin/users/{userId}` | `PUT` | `platform.manage_users` | Actualizar atributos/roles del usuario |
| `/api/v1/admin/users/{userId}` | `DELETE` | `platform.manage_users` | Deshabilitar usuario (soft-delete preferido) |
| `/api/v1/admin/users/{userId}/reset-password` | `POST` | `platform.manage_users` | Fijar contraseña temporal / forzar cambio (auditado) |
| `/api/v1/admin/roles` | `GET` | `platform.manage_users` | Listar roles y mapeo a capacidades del sistema |
| `/api/v1/admin/roles/{roleName}/capabilities` | `PUT` | `platform.manage_users` | Actualizar mapeo rol → capacidades (tabla `role_capability`) |
| `/api/v1/admin/webhook` | `GET` | `platform.manage_webhook` | Estado del webhook de Google Sheets (última recepción, `key_id` vigente, reintentos) |
| `/api/v1/admin/webhook/secret/rotate` | `POST` | `platform.manage_webhook` | Rotar el secreto del webhook (nueva `key_id`, solape 24 h); el secreto se muestra una sola vez |

**Notas:**
- Los roles (`viewer`, `supervisor`, `auditor`, `platform-admin`) son **contenedores de capacidades**; el mapeo rol→capacidad vive en la tabla `role_capability` del backend.
- Cualquier cambio en usuarios/roles **genera evento de auditoría** (`audit_event` con `action = user.created/updated/disabled/role.assigned/revoked`).
- Rate limit estricto: **50 req/min** por `sub` en estos endpoints; el login tiene rate limit por IP/usuario (RNF-12.e) y bloqueo por intentos (RNF-03.i).

---

## 11. Contrato visual / Especificación de UI

Esta sección es **normativa**: define la retícula, la paleta, la tipografía y el comportamiento de cada visual de forma **implementable sin ambigüedad**. El objetivo es que un equipo de UI/implementación pueda maquetar y un equipo de QA pueda verificar sin interpretar.

### 11.1 Retícula del dashboard (layout canónico)

- **Retícula:** CSS **Grid de 12 columnas**, `gutter` de **24 px**, `padding` exterior **24 px**. Ancho completo del viewport (sin ancho máximo fijo). La altura de referencia del diseño es **1080 px** (1920×1080) y debe caber **sin scroll vertical** en ese tamaño.
- **Filas y spans (a 1920×1080):**

| Fila | Contenido | Colspan | Altura de fila | Span vertical (grid-row) |
|------|-----------|---------|----------------|---------------------------|
| **0** | Cabecera: título · reloj+tz · estado conexión · última actualización · usuario/rol | 12 | **64 px** | — |
| **1** | **4 tarjetas KPI** (VIS-01..04) | **3** cada una | **168 px** | — |
| **2a** | VIS-05 Gráfico "Intervenciones por Unidad Regional" | **7** | **flex** (≈ 360 px) | 1 |
| **2b** | VIS-06 Gráfico "Incidentes por Turno Operativo" | **3** | (misma fila) | 1 |
| **3** | VIS-07 Tabla "Ranking de Dependencias - Top 5" | **12** | resto (≈ 300 px) | 1 |

- **Anchos resultantes a 1920 px** (con padding 24×2 y gutters 24×3 en las filas de 4 y de 2): cada KPI ≈ 456 px; regional ≈ 1092 px; **turnos** ≈ 780 px. Valores concretos que la implementación puede usar como referencia fija.
- **Comportamiento responsivo:**
  - `1920–2559 px`: layout canónico de arriba.
  - `1280–1919 px`: KPI pasan a **2×2** (colspan 6), graficos mantiene 7/5; se acepta scroll vertical si el alto no alcanza (a 1440×900 es inevitable).
  - `< 1280 px`: se muestra el aviso "resolución no soportada" (RF-05.d).
  - `2560+ / 4K`: la retícula se escala manteniendo proporciones (todos los textos y alturas en unidades relativas/`clamp()`), sin scroll.
- **Espaciado:** todo el espaciado es múltiplo de **8 px**. Áreas de contacto ≥ **44×44 px**.
- **Bordes de panel:** cada visual va en una **tarjeta** con fondo `--bg-surface` (`#0B1220`), radio **12 px**, borde `1 px #1E2A3D`, y **padding interno 24 px**.

### 11.2 Paleta concreta (tokens)

| Token | Valor | Uso |
|-------|-------|-----|
| `--bg-base` | **`#05080F`** | Fondo de la aplicación (azul marino casi negro). |
| `--bg-surface` | **`#0B1220`** | Fondo de tarjetas/paneles. |
| `--bg-surface-2` | **`#111A2B`** | Fondo alterno / cabeceras de tabla / hover. |
| `--border` | **`#1E2A3D`** | Bordes de tarjetas y separadores. |
| `--text-primary` | **`#FFFFFF`** | Texto principal (valores KPI, títulos). |
| `--text-secondary` | **`#C7D2DE`** | Etiquetas y texto secundario. |
| `--text-muted` | **`#8A9BB0`** | Texto terciario (unidades de ejes, metadatos). |
| `--accent` | **`#38BDF8`** | **Acento celeste** principal (foco, turno en curso, resaltes, barra top). |
| `--accent-strong` | **`#0EA5E9`** | Barras "en curso"/secundarias, acentos fillers. |
| `--accent-soft` | **`rgba(56,189,248,0.14)`** | Rellenos tenues, fondo de foco. |
| `--pos` | **`#34D399`** | Variación **positiva** (verde). |
| `--neg` | **`#F87171`** | Variación **negativa** (rojo). |
| `--warn` | **`#FBBF24`** | Estados de atención (reconectando, datos caducados, pendiente). |
| `--neutral` | **`#94A3B8`** | Variación **cero** / deshabilitado / "sin datos". |

Verificación de contraste (sobre `#0B1220`): `#FFFFFF` **15,8:1**, `#C7D2DE` **12,6:1**, `#8A9BB0` **6,4:1**, `#38BDF8` **9,1:1**, `#34D399` **10,5:1**, `#F87171` **7,0:1**, `#FBBF24` **11,6:1** — todas ≥ 4,5:1 (RNF-09.b cumplida).

### 11.3 Tipografía y escala de tamaños

- **Familia:** **Inter** (self-host vía `@fontsource`, fallback `system-ui, -apple-system, "Segoe UI", sans-serif`). **Numeración tabular** (`font-variant-numeric: tabular-nums`) en KPI, ejes y tabla.
- **Escala (px / line-height / peso):**

| Rol | Tamaño | Peso | Line-height | Tracking | Uso |
|-----|--------|------|--------------|----------|-----|
| Valor KPI | **34** | 700 | 1.05 | −0,01em | Cifra grande de las 4 tarjetas |
| Variación KPI | 14 | 600 | 1.2 | 0 | `▲ +3.120 (+1,7 %)` |
| Título de panel (h2) | 16 | 600 | 1.3 | 0 | "Intervenciones por Unidad Regional" |
| Etiqueta KPI / campo | 12 | 600 | 1.2 | **0,06em**, **versalitas (uppercase)** | "TOTAL CONSULTAS SIFCOP", "VARIACIÓN" |
| Texto de tabla / tooltip | 14 | 400–600 | 1.4 | 0 | Filas, tooltips |
| Texto de eje / secundario | 12 | 400 | 1.2 | 0 | Unidades, marcas |
| Valor de etiqueta en barra | 12 | 700 | 1 | 0 | Número al final de la barra (RF-03.g) |
| Estado / badge | 12 | 700 | 1 | 0,04em | "EN VIVO", "EN CURSO", badges de posición |

### 11.4 Reglas por visual

#### VIS-01..04 — Tarjetas KPI (fila superior)

- **Estructura por tarjeta (de arriba abajo):** (1) etiqueta en versalitas 12 px; (2) **valor** 34 px tabular; (3) fila de **variación**: glifo + absoluto + porcentaje (14 px), coloreada por dirección (verde/rojo/gris). A la derecha, en pequeño, `vs ayer`.
- **Formato numérico:** miles con punto (`184.732`), sin decimales en el valor. La variación absoluta usa signo explícito (`+3.120`, `−412`, `0`); el porcentaje con 1 decimal y coma decimal (`+1,7 %`).
- **Estado "sin referencia":** si `has_reference = false`, la línea de variación muestra `— sin referencia de ayer` en `--text-muted`.
- **Micro-interacción:** al cambiar, la tarjeta recibe un **borde de acento de 2 px** (`--accent`) durante **600 ms** (RF-02.g). En hover, `--accent-soft` como fondo sutil.
- **ARIA:** contenedor `role="group"` con `aria-label="<etiqueta>, valor actual y variación respecto a ayer"`; el valor actualizado se anuncia una vez vía `aria-live="polite"` (RNF-09.f).

#### VIS-05 — "Intervenciones por Unidad Regional" (barras horizontales)

- **Componente:** Recharts `<BarChart layout="vertical">` (`dataKey="intervenciones"`), en un panel de 7 columnas.
- **Ejes:** Y = `type="category"` con las **5 unidades** en orden canónico fijo (no reordenar por valor; RF-03.f). X = `type="number"` con `domain={[0, dataMax * 1.15]}`, `ticks` cada 5. Rejilla: `CartesianGrid` con `vertical={false}` (solo líneas horizontales).
- **Barras:** `radius={[0, 4, 4, 0]}`, altura por defecto, **relleno con gradiente** de `--accent-strong` (`#0EA5E9`) a `--accent` (`#38BDF8`), ancho máximo de barra comfortable (escala categórica `bandSize` ~28–40 px). La barra de la unidad con **mayor valor** se resalta a opacidad 1 y las demás a 0,85 (jerarquía visual, sin ocultar datos).
- **Etiquetas de valor:** `<LabelList dataKey="intervenciones" position="right" />` en 12 px `--text-primary` (RF-03.g).
- **Tooltip (custom):** fondo `#111A2B`, borde `#38BDF8`, texto blanco; muestra **Unidad**, **Intervenciones**, **Variación abs**, **Variación %**, **Puesto regional**. Accesible por teclado además de hover.
- **Categoría sin datos:** barra de 0 px con texto `sin datos` en `--text-muted` (no se elimina la categoría) (RF-03.e).
- **Animación:** transición de barras **400 ms** `ease-out`; respeta `prefers-reduced-motion` (sin transición).

#### VIS-06 — "Incidentes por Turno Operativo" (barras por turno)

- **Tipo de gráfico (decisión):** **barras verticales** (`<BarChart>` con `<Bar>`), **3 categorías** en orden cronológico: `MAÑANA` (06:00–14:00), `TARDE` (14:00–22:00), `NOCHE` (22:00–06:00+1). *(Alternativa considerada: barras horizontales o línea — se elige barras verticales por ser más precisa para conteos por bucket discreto y por leerse mejor de lejos en una pantalla de sala.)*
- **Ejes:** X = `type="category"` con los **3 turnos** en orden cronológico (`MAÑANA`, `TARDE`, `NOCHE`); Y = `type="number"` con `domain={[0, dataMax*1.15]}`. Rejilla solo horizontal.
- **Color por estado de turno (RF-04.b):** `cerrada` → `--accent-strong` (`#0EA5E9`); `en_curso` → `--accent` (`#38BDF8`) + etiqueta `EN CURSO` encima; `pendiente` → `--border` (`#1E2A3D`) + marcador `—` (no es 0, es "aún no ocurrido").
- **Tooltip (custom):** **Turno**, **Intervenciones**, **Variación abs**, **Variación %**, **Estado** (`CERRADA`/`EN CURSO`/`PENDIENTE`).
- **Animación:** entrada/actualización 400 ms `ease-out`.

#### VIS-07 — "Ranking de Dependencias - Top 5" (tabla)

- **Componente:** tabla HTML semántica (`<table>`), en panel de 12 columnas, `caption` visible o accesible con el título.
- **Columnas (4, en este orden):**

| # | Columna | Ancho | Contenido | Formato / estilo |
|---|---------|-------|-----------|------------------|
| 1 | `Posición` | 90 px | 1–5 | **Badge numérico** (círculo/cuadrado 28 px, `--accent-soft` fondo, `--accent` texto bold). El **puesto 1** con acento lleno (`--accent` fondo, texto `#05080F`). |
| 2 | `Comisaría` | flexible (izquierda) | Nombre de la dependencia | Texto `--text-primary` 14 px, alineado a la izquierda, **recortado con elipsis** si es muy largo + `title` completo. |
| 3 | `Intervenciones` | 120 px (derecha) | Entero | **14 px tabular**, alineado a la **derecha**, separador de miles. |
| 4 | `Variación` | 200 px (derecha) | Abs + % | `▲ +12 (+3,4 %)` verde · `▼ −5 (−1,1 %)` rojo · `= 0 (0,0 %)` gris; **glifo + signo + color** (nunca solo color). |

- **Orden:** por intervenciones descendente; desempate alfabético (determinista). **Hasta 5 filas**, sin relleno.
- **Cambio de puesto:** al detectar `puesto != puesto_previo`, la fila se **destella** con `--accent-soft` durante **600 ms** (RF-04.g) y el `aria-label` de la fila incluye "subió/bajó N puestos".
- **Estilo de filas:** cebra suave alternando `--bg-surface` / `--bg-surface-2`; `border-bottom: 1px --border`; altura de fila **44 px** (cumple objetivo táctil); **encabezado fijo** (sticky) con `--text-muted` versalitas 12 px. Hover de fila: `--accent-soft`.
- **Estado vacío:** si no hay datos, una fila centrada `SIN DATOS` con el motivo en `--text-muted` (RF-04.h). Si hay datos parciales (`quality.partial`), nota discreta bajo la tabla.
- **Accesibilidad:** `role="table"`, `<th scope="col">`, navegación por flechas arriba/abajo entre filas, y **tabla de datos equivalente** accesible (RNF-09.e).

### 11.5 Estados globales de la interfaz

| Estado | Presentación | Disparador |
|--------|--------------|-------------|
| **Cold start** | Skeletos (bloques grises pulsantes `--bg-surface-2`) en los 7 visuales; nunca ceros. | Antes de la primera instantánea válida. |
| **EN VIVO** | Punto verde `#34D399` + texto `EN VIVO` en cabecera. | WSS conectado y con datos frescos (< 120 s). |
| **RECONECTANDO** | Punto ámbar `#FBBF24` + `RECONECTANDO (intento N…)`. | Socket caído, reintentando con backoff. |
| **DEGRADADO · POLLING** | Texto ámbar; se indica la frecuencia (10 s). | WSS sin éxito > 60 s (RNF-05.d). |
| **SIN CONEXIÓN** | Punto rojo `#F87171` + `SIN CONEXIÓN`. | WSS cerrado por `4003`/`4401` persistente, sin polling viable. |
| **DATOS DESACTUALIZADOS** | Banner ámbar superior: `DATOS DESACTUALIZADOS — hace Xs`; visuales atenuados (opacidad 0,75). | Edad del último `last_event_ts` > 120 s (RF-05.h). |
| **Acceso denegado** | Pantalla centrada `ACCESO DENEGADO`, sin revelar datos. | 403 / cierre `4003` (AM-01). |
| **Error de esquema** | Banner rojo `ACTUALIZACIÓN REQUERIDA` (cliente desactualizado). | `schema_version` mayor no soportada (§7.8). |

### 11.6 Ficha de componente KPI (contrato visual preciso)

Para eliminar ambigüedad en la tarjeta más importante, se fija:

```text
┌───────────────────────────────────────────┐  ← borde 1px #1E2A3D, radio 12px, fondo #0B1220
│  T O T A L   C O N S U L T A S   S I F C O P │  ← 12px/600/versalitas/tracking 0.06em, #C7D2DE
│  184.732                                   │  ← 34px/700, tabular, #FFFFFF, línea base a 8px
│  ▲ +3.120 (+1,7 %)  ·  vs ayer             │  ← 14px/600, #34D399, glifo+signo+%, "vs ayer" en #8A9BB0
└───────────────────────────────────────────┘
  padding interno 24px; altura total 168px;
```

- Separación etiqueta→valor: **8 px**; valor→variación: **10 px**.
- La variación se alinea a la **izquierda**, bajo el valor; `vs ayer` en tertiary a 4 px de espacio.

---

## 12. Criterios de aceptación

Formato **Given / When / Then**, verificables por test automatizado (Playwright para UI/E2E, Vitest/Jest para lógica, pytest para backend). Cada criterio tiene un ID estable `CA-xx.n` referenciado en §15.

### 12.1 RF-01 — Transmisión Segura

| ID | Given | When | Then | Test |
|----|-------|------|------|------|
| CA-01.1 | Un documento de Google Sheets con cambios y un webhook con secreto vigente | Se produce una edición efectiva | Apps Script envía `POST /ingest/webhook` con `X-Webhook-Id`, `X-Webhook-Nonce`, `X-Webhook-Timestamp` y `X-Webhook-Signature`; el backend responde `202` y el canal va sobre TLS 1.3 | E2E + captura TLS |
| CA-01.2 | Un mensaje con **firma HMAC inválida** | Se envía un `POST /ingest/webhook` | Backend responde `401` **sin deserializar** el cuerpo, registra auditoría `ingest.rejected` con `SIGNATURE_INVALID` y **no** redirige nada por WSS | pytest |
| CA-01.3 | Un cuerpo **alterado** tras el cálculo de la firma | Se envía | Backend responde `401`, no parsea, y audita `SIGNATURE_MISMATCH` (fail-closed) | pytest |
| CA-01.4 | Una edición que produce el **mismo `content_sha256`** | Se intenta transmitir | El origen **no envía** nada (deduplicación por contenido) | pytest/Apps Script test |
| CA-01.5 | Backend con dos clientes WSS autorizados en la sala | Llega una instantánea válida | Ambos reciben el mensaje `indicators.snapshot` en < 100 ms (p95) y ambos **registran auditoría de visualización** | Playwright ×2 |
| CA-01.6 | Un **nonce ya visto** dentro de la ventana | Se reenvía el mismo mensaje | Backend responde `409`; el origen regenera nonce y reintenta **una** vez | pytest |
| CA-01.7 | Backend caído y luego restaurado | El trigger detecta cambios durante la caída | Apps Script reintenta con backoff y, si persiste, el backend **reconcilia por polling de respaldo**, sin pérdida de eventos | pytest + test de integración |
| CA-01.8 | Un cliente WSS **no autorizado** (sin `dash.view.live`) | Intenta obtener ticket y abrir WSS | `POST /ws-ticket` responde `403`; ninguna conexión de datos se establece | Playwright (con token de rol bajo) |

### 12.2 RF-02 — Tarjetas de Indicadores

| ID | Given | When | Then | Test |
|----|-------|------|------|------|
| CA-02.1 | Dashboard cargado con cold start válido | Llega un `indicators.snapshot` por WSS con nuevos valores | Los **4 bloques superiores** (Total Consultas SIFCOP, Personas Capturadas, Vehículos Secuestrados, Armas Secuestradas) se actualizan **sin ninguna recarga de página** (no hay `page.reload()`; el DOM se muta in-place) | Playwright: mutar DOM sin reload |
| CA-02.2 | Las 4 tarjetas | Se renderiza el panel | Están en la **fila superior**, en orden fijo [Consultas, Capturadas, Vehículos, Armas], con igual ancho | Playwright: bounding boxes |
| CA-02.3 | Valor y baseline conocidos (184.732 vs 181.612) | Se calcula la variación | Muestra `+3.120 (+1,7 %)` con **signo**, glifo ▲ y texto `vs ayer`; el texto (no el color) es el aserto | Vitest |
| CA-02.4 | Sin referencia de ayer (`has_reference=false`) | Se renderiza la tarjeta | La variación muestra `— sin referencia de ayer` (nunca `NaN`, `0` ni `Infinity`) | Vitest |
| CA-02.5 | Dos instantáneas con el **mismo** valor de KPI | Se aplica la segunda | No hay animación de recuento ni cambio de DOM visible (idempotencia visual, RF-02.f) | Vitest (mock rAF) |
| CA-02.6 | Un KPI **negativo o NaN** | Llega la instantánea | El cliente **rechaza la instantánea completa** y muestra el banner de datos no válidos (no renderiza el valor corrupto) | Vitest |
| CA-02.7 | Un snapshot KPI con valor **numérico pero sin cambios** y luego un cambio real | Se renderiza | La primera no anima; la segunda anima 400 ms y marca la tarjeta 600 ms | Playwright con rAF |
| CA-02.8 | Controles de contraste de la paleta | Se mide la UI | Cada combinación texto/fondo usada cumple ≥ 4,5:1 y los objetos gráficos ≥ 3:1 (axe-core + cálculo) | axe/Lighthouse |
| CA-02.9 | Un operador con rol sin `dash.view.live` | Accede a `/` | Ve `ACCESO DENEGADO`; la respuesta **no** contiene nombres ni valores de KPI | Playwright + aserto de red |
| CA-02.10 | Un operador autenticado | Abre el panel | Se registra auditoría de primera visualización con `sub`, `room_id`, `data_date`, `event_id` | pytest (query auditoría) |

### 12.3 RF-03 — Gráfico Regional

| ID | Given | When | Then | Test |
|----|-------|------|------|------|
| CA-03.1 | Panel activo con datos regionales | Se monta el componente | Existe un Recharts `BarChart` con `layout="vertical"` con **exactamente 5 barras** etiquetadas Capital, Sur, Este, Oeste, Norte en orden canónico | Playwright/DOM |
| CA-03.2 | Datos de una unidad **ausentes** | Se renderiza | La categoría sigue visible con barra de 0 px y texto `sin datos`; no se elimina del eje | Vitest snapshot |
| CA-03.3 | La categoría `Noreste` (no allowlist) llega en el payload | Se aplica la instantánea | Se descarta, se registra `rejected_unknown_unit`, y el gráfico sigue mostrando las 5 unidades canónicas | Vitest |
| CA-03.4 | Regional con valores [268,142,98,71,34] | Se renderiza | Las barras son **crecientes de largo** según valor (assert de `width`/path) y llevan su valor etiquetado al extremo derecho | Playwright |
| CA-03.5 | Regional con 2 valores nuevos | Se aplica | La **posición Y no cambia** (orden territorial estable) y hay transición de 400 ms | Playwright (bbox antes/después) |
| CA-03.6 | Cualquier barra | Se pasa el foco de teclado | Aparece el tooltip accesible con Unidad, Intervenciones, Variación abs/%, Puesto | Playwright (teclado) |

### 12.4 RF-04 — Tendencia y Ranking

| ID | Given | When | Then | Test |
|----|-------|------|------|------|
| CA-04.1 | Payload con datos | Se renderiza | El gráfico de turnos muestra **3 categorías** en orden `MAÑANA, TARDE, NOCHE` | Playwright/DOM |
| CA-04.2 | Hora actual dentro de `TARDE` (TZ canónica `America/Argentina/Buenos_Aires`) | Se renderiza | El turno `TARDE` tiene acento `#38BDF8` y etiqueta `EN CURSO`; `NOCHE` (futuro) tiene `#1E2A3D` y `—` (pendiente, no 0) | Vitest |
| CA-04.3 | Payload con ranking de 7 dependencias | Se renderiza la tabla | La tabla tiene **4 columnas** con los encabezados `Posición`, `Comisaría`, `Intervenciones`, `Variación` y **exactamente 5 filas**, ordenadas por intervenciones desc con desempate alfabético | Playwright |
| CA-04.4 | Variación de una fila = +12 (3,4 %) y otra = −5 (−1,1 %) | Se renderiza | Formato exacto `▲ +12 (+3,4 %)` y `▼ −5 (−1,1 %)` (glifo + signo + coma decimal) | Vitest |
| CA-04.5 | Una dependencia cambia de puesto (2→1) | Se aplica la instantánea | La fila se destella 600 ms y el `aria-label` indica "subió 1 puesto" | Playwright |
| CA-04.6 | Ranking con solo 2 dependencias | Se renderiza | Se muestran **2 filas**, sin filas de relleno; con 0 → `SIN DATOS` con motivo | Vitest |
| CA-04.7 | Tabla de ranking | Se navega con flechas | La navegación arriba/abajo funciona y la tabla es navegable por teclado con encabezados `scope="col"` | Playwright |

### 12.5 RF-05 — UI Táctica

| ID | Given | When | Then | Test |
|----|-------|------|------|------|
| CA-05.1 | Panel a 1920×1080, escala 100 % | Se carga | **No hay scroll vertical ni horizontal**; los 7 visuales caben en pantalla | Playwright (viewport 1920×1080, sin overflow) |
| CA-05.2 | Panel a 3840×2160 | Se carga | Escala proporcionalmente, sin scroll y sin solapes | Playwright |
| CA-05.3 | Cualquier texto | Se mide contraste | ≥ 4,5:1 (normal) / ≥ 3:1 (gráficos y componentes) con la paleta de §11.2 | axe-core |
| CA-05.4 | `prefers-reduced-motion: reduce` | Llega una actualización | No hay animación de recuento ni de barras, pero el **valor cambia** | Playwright (emulateMedia) |
| CA-05.5 | Sin datos aún (arranque) | Se carga | Se muestran skeletons en los 7 visuales, **nunca ceros ni "—" como dato real** | Playwright |
| CA-05.6 | Última actualización hace **> 120 s** | Se evalúa frescura | Aparece banner `DATOS DESACTUALIZADOS — hace Xs` y los visuales se atenúan (opacidad < 1), sin alterar valores | Playwright (mock reloj) |
| CA-05.7 | Se navega solo con `Tab` | Se recorre la UI | Hay skip-link, foco visible (contorno ≥ 2 px, ≥ 3:1), y el orden es cabecera→KPI→regional→turnos→tabla | Playwright + axe |
| CA-05.8 | Estado de conexión cambiante | Se simula corte WSS | La cabecera refleja `EN VIVO → RECONECTANDO → DEGRADADO · POLLING` correctamente y con texto (no solo color) | Playwright (route WS) |
| CA-05.9 | Actualización en vivo | Se mide el frame time | No se supera 250 ms de render por actualización; si el frame time > 32 ms durante 60 frames, se degrada a render instantáneo | PerformanceObserver test |

---

## 13. Métricas y límites

Valores concretos que el sistema y sus pruebas deben respetar.

| Métrica / Límite | Valor | Ámbito | Ref. |
|-------------------|-------|--------|------|
| **Unidades regionales** | **5** (allowlist: Capital, Sur, Este, Oeste, Norte) | Config | RF-03 |
| **Turnos operativos** | **3** (MAÑANA 06-14, TARDE 14-22, NOCHE 22-06) | Config | RF-04 |
| **KPI** | **4** (Consultas, Capturadas, Vehículos, Armas) | Fijo | RF-02 |
| **Ranking** | **Top 5** dependencias | Fijo | RF-04 |
| **Zona horaria canónica** | **Configurable por instalación** (IANA), por defecto `America/Argentina/Buenos_Aires`; reloj autoritativo = backend. Ver OD-01 | Config | §7 |
| **Latencia edición→visual** | **p95 ≤ 1,5 s**, p99 ≤ 3 s | E2E | RNF-04 |
| **Detección de edición (trigger)** | Coalescencia **750 ms**; reconciliación por polling de respaldo **60 s** | Apps Script / Backend | RF-01.a |
| **Firma del webhook** | **HMAC-SHA256** (digest 256 bits) sobre cuerpo canónico + metadatos | Crypto | §9 |
| **Secreto de webhook — rotación** | **90 días**, solape **24 h** (2 secretos válidos) | Cripto | §9.3 |
| **Clave de cifrado en reposo — rotación** | **90 días** | Cripto | §9.3 |
| **Nonce de webhook** | **128 bits** aleatorios por mensaje | Origen (Apps Script) | RF-01.d |
| **Ventana anti-replay (webhook)** | **±300 s** (timestamp); cache de nonce **600 s** | Backend | RF-01.k |
| **Tamaño máx. payload** | **64 KB** comprimido / **256 KB** plano → `413` | Ingesta | RNF-12.f |
| **Filas máx. por evento** | **64** filas de detalle agregable (por encima → `413`) | Ingesta | — |
| **Rate limit webhook** | **200 req/min (≈3,3 msg/s)**, ráfaga **20** | Ingesta | RNF-12.a |
| **Rate limit por operador** | **120 req/min** por `sub` | REST | RNF-12.b |
| **WSS entrante** | **10 msg/s** por conexión; **20** conexiones por token | WSS | RNF-12.c |
| **Clientes WSS por sala** | **50** (exceder → `1013`) | Sala | RNF-12.d |
| **Clientes WSS global** | **200** | Instancia | RNF-12.d |
| **Heartbeat de aplicación** | Envío **15 s**; cierre si sin actividad **45 s** | WSS | RNF-05.b |
| **Backoff de reconexión** | `1, 2, 4, 8, 16, 30 s` (tope 30 s), jitter **±20 %** | Cliente | RNF-05.a |
| **Degradación a polling** | Tras **60 s** sin WSS; intervalo de polling **10 s** | Cliente | RNF-05.d |
| **Umbral de "datos desactualizados"** | **120 s** desde `last_event_ts` | Cliente | RF-05.h |
| **Vida del ticket WSS** | **60 s**, un solo uso | Auth | RNF-03.d |
| **Vida del token de acceso** | **15 min**; refresh **indefinido rotativo con actividad** (sin TTL fijo) | Auth | RNF-03.b |
| **Sesión de operador (sala)** | **Sin expiración mientras el navegador esté abierto**; refresh token rotativo indefinido con actividad; **sin MFA ni step-up** | Auth | RNF-03 |
| **Tolerancia de deriva de reloj** | **±5 s** para calcular "desactualizado" (usa reloj del backend como referencia) | Cliente | RF-05.h |
| **Retención — ingest_event** | **90 días** | Almacén | RNF-02 |
| **Retención — agregados (agg_hourly/daily, ranking)** | **60 meses** | Almacén | RNF-02 |
| **Retención — audit_event** | **60 meses** (append-only) | Almacén | RNF-08 |
| **Retención — logs de aplicación** | **14 días** (30 días si el agregador lo permite) | Observabilidad | RNF-08.f |
| **Backups** | Diarios (**35 d**), semanales (**12 sem**), mensuales (**24 meses**) | DR | RNF-14 |
| **RPO** | **15 min** | DR | RNF-14.a |
| **RTO** | **2 h** | DR | RNF-14.b |
| **Rango histórico máximo (`supervisor`)** | **90 días**; `auditor` hasta **60 meses** (OD-07) | API | §10.2 |
| **Resoluciones objetivo** | **1920×1080** (principal), 2560×1440, 3840×2160; `min-width` 1280 px | UI | RNF-10 |
| **Escala de DPI** | **100 %–200 %** | UI | RNF-10.c |
| **Presupuesto de render por actualización** | **≤ 250 ms**; 60 fps | UI | RNF-04.b |
| **Cold start (render completo)** | **≤ 1,5 s** | UI | RNF-04.c |

---

## 14. Riesgos técnicos y decisiones abiertas

### 14.1 Riesgos técnicos

| ID | Riesgo | Impacto | Mitigación / contención |
|----|--------|---------|--------------------------|
| RISK-01 | **Fiabilidad del trigger de Apps Script** (`onEdit`/`onChange`) ante ediciones programáticas, cambios que no disparan el trigger o cuotas/rate limits de Google | Falsos negativos (no se publica) o duplicados | Trigger instalable + **reconciliación por polling de respaldo** con la API de Google Sheets (service account de solo lectura) + hash de contenido (dedup); pruebas con ediciones reales. |
| RISK-02 | **Estructura del documento de Google Sheets** cambia de columnas/encabezados (analista renombra una hoja o inserta una columna) | El normalizador falla cerrado y no publica | Lista allowlist de cabeceras; validación estricta; mensaje de error accionable; sin "adivinar" columnas (OOS-06). |
| RISK-03 | **Calculadora de "ayer"**: el día local cambia a medianoche; zonas horarias y DST pueden desalinear los turnos | Variaciones erróneas al rollover del día | Todo en el backend con reloj autoritativo y TZ canónica; baselines por `data_date`+`turno_id`; test de rollover de día y de DST. |
| RISK-04 | **Fan-out WSS** con cientos de conexiones y deja evidencia de entregadas | Actualizaciones perdidas o alta latencia | Backpressure, fan-out por `room_id` en Redis, `seq` monotónico + cold start para rellenar huecos; SSL keepalive. |
| RISK-05 | **Coste/latencia** de "vs ayer" si se recalcula por petición | Latencia > p95 | Precalcular baselines y `variacion` en el backend y cachearlos por `data_date`+`turno_id`; el cliente solo pinta. |
| RISK-06 | **Contrato de esquema** deriva entre backend y SPA (deploys desacoplados) | Pantalla en blanco o malformada | Versionado semver (§7.8), ventana de soporte de 2 minors, deploy de SPA **antes** que backend, validación de esquema en CI. |
| RISK-07 | **CSP estricta vs librerías de gráficos** (Recharts/tailwind) que inyectan estilos inline | Rompe el CSP y se relajan (debilitando AM-06/AM-11) | Configurar CSP sin `unsafe-inline` en `style-src` solo si es necesario con hashes/nonces; test de CSP en E2E que falla si aparece `unsafe-inline` en script. |
| RISK-08 | **Accesibilidad vs estética táctica** (contrastes bajos para "impacto") | Incumplimiento WCAG AA | Paleta fijada con contraste verificado; toda variación con glifo+signo; auditoría de contraste automatizada. |
| RISK-09 | **Sesiones 24/7 vs seguridad** (pantallas siempre encendidas) | Credenciales de larga duración o logouts frecuentes que molestan en sala | OD-04 resuelto: sin expiración en sala 24/7, refresh indefinido con actividad, **sin MFA ni step-up**; las acciones sensibles se auditan. |
| RISK-10 | **DoS / flood** desde un webhook comprometido o Internet | Panel caído en sala | Rate limiting multinivel, límites de payload/conexiones, WAF, alertas, reintentos acotados del webhook. |
| RISK-11 | **Reconciliación de turnos "pendiente"** (el turno NOCHE cruza medianoche; turnos futuros no existen aún) | Gráfico con ceros que se leen como "cero incidentes" | Estados `pendiente`/`en_curso`/`cerrada` con color y etiqueta distintos (RF-04.b); nunca 0 para futuro. |
| RISK-12 | **Alta cardinalidad / duplicados** en el ranking si el documento lista una dependencia con variantes de nombre ("Comisaría 7" vs "COM 7") | Ranking incoherente | Normalización y catálogo de dependencias; desempate determinista; auditoría de nombres no reconocidos. |
| **RISK-13** | **Gestión de credenciales locales y rotación de `JWT_SIGNING_KEY`** | Fuga o mala gestión de credenciales locales, o rotación no coordinada de la clave de firma, degrada la autenticación de todos los operadores. | Contraseñas con **Argon2id** + bloqueo por intentos + rate limit de login (RNF-03.a/i, RNF-12.e); `JWT_SIGNING_KEY` en secret manager con rotación programada (90 días) y solape de validación (§9.3); auditoría de login y de cambios de usuario; backups cifrados del almacén local (RNF-14.f). | RNF-03, RNF-13, RNF-14.f |
| RISK-14 | **Cuotas y rate limits de Google Sheets API** (`UrlFetchApp`, `SpreadsheetApp`, triggers) | Retraso o pérdida de la notificación en picos de edición | Reintentos con backoff + reconciliación por polling de respaldo; coalescencia de ediciones; alerta si el último webhook supera el umbral (RNF-07.d). |
| RISK-15 | **Permisos OAuth de la cuenta estándar de Google** (la service account o el script pierde acceso al documento) | El trigger no puede leer o notificar | Verificación de permisos en el arranque de la reconciliación; alerta de salud del origen; polling de respaldo con service account de solo lectura; ensayo de rotación de credenciales. |

### 14.2 Decisiones abiertas (requieren validación del usuario)

| ID | Decisión abierta | Propuesta por defecto | Por qué importa |
|----|------------------|----------------------|-----------------|
| **OD-01** | **Zona horaria canónica** de turnos, "hoy" y baselines. | **Resuelto** — `America/Argentina/Buenos_Aires` configurable por instalación, reloj autoritativo backend. No queda decisión pendiente. | Define los límites de los 3 turnos operativos y qué día es "ayer". Confirmada por el usuario. |
| **OD-02** | **Base de la "variación respecto a ayer"**: `ayer_mismo_tramo` (acumulado hasta la misma hora), `ayer_completo` (día anterior entero), u otra (contador fijo / meta). | **Resuelto —** `ayer_mismo_tramo` (mismo tramo horario, acumulado hasta la misma hora). | Cambia el significado de los 4 KPIs y de las variaciones del gráfico y la tabla. Es una decisión **de negocio/operativa**, no técnica. |
| **OD-03** | **Semántica del color de la variación**: ¿verde = "sube" (dirección) o verde = "bueno" (deseable)? Para "Personas Capturadas"/"Armas Secuestradas", **subir no es necesariamente bueno**. | **Resuelto —** color por dirección del cambio (verde = sube, rojo = baja) + glifo + signo. | Si el mando lee "capturadas bajaron" en rojo, puede interpretar mal una buena noticia. Es una decisión de **semántica de sala**. |
| **OD-04** | **Política de sesión para turnos 24/7**: vida de sesión sin expiración en sala 24/7. | **Resuelto — Sin expiración en sala 24/7**. La sesión persiste mientras el navegador esté abierto (refresh token rotativo indefinido mientras hay actividad). **Sin MFA y sin step-up**; las acciones sensibles exigen capacidad y se auditan. **Se elimina el bloqueo a los 30 min de inactividad para la visualización en vivo**. | Impacto directo en seguridad vs experiencia de un operador que mira la pantalla 8–12 h seguidas. Decisión del Grupo B. |
| **OD-05** | **Identidad de acceso al dashboard**: ¿IdP institucional, Keycloak propio o autenticación nativa? | **Resuelto — Autenticación nativa con JWT (usuario y contraseña) emitido por el backend**, sin Keycloak/SSO/MFA. Los operadores no tienen correo institucional ni MFA; el backend gestiona usuarios locales (hash Argon2id) y emite access token corto + refresh rotativo. | Elimina el IdP externo y su SPOF; concentra la identidad en el backend. Añade el riesgo de gestión de credenciales locales y rotación de `JWT_SIGNING_KEY` (§14.1, RISK-13). |
| **OD-06** | **¿Múltiples salas / multi-instalación** en el mismo despliegue, o una sola sala por instalación? | **Resuelto — Una instancia = una sala**. Cada deployment es independiente (una sala, un documento, un webhook). El campo `room_id` existe en el modelo para futuro escalado, pero **no hay selector de sala en la UI**. Los roles `supervisor` y `auditor` ven **solo su sala**. | Decisión del Grupo C: aislamiento físico por deployment; `room_id` queda en modelo para trazabilidad y escalado futuro sin conmutación en UI. |
| **OD-07** | **Retención y alcance del histórico**: ¿90 días para `supervisor` es suficiente? ¿El `auditor` necesita 60 meses de detalle o solo el Top 5 diario? | **Resuelto — Supervisor 90 días detalle / Auditor 60 meses agregados**. El `supervisor` accede a histórico con granularidad horaria hasta 90 días (`dash.view.history`). El `auditor` accede a agregados horarios/diarios y ranking hasta 60 meses (`audit.view` + `dash.view.history` extendido). No se entregan filas de detalle (PII) a ningún rol. | Decisión del Grupo C: distingue "detalle" (horario, 90d) de "agregados" (horario/diario, 60m). Impacta almacenamiento y alcance de `dash.view.history` vs `audit.view`. |
| **OD-08** | **Volumen real de cambios**: ¿cuántas veces se edita el documento por hora/día en la práctica? | **Resuelto — Medio (100–1 000 ediciones/día)**. Rate limits: `/ingest/webhook` **200 req/min** por webhook; admin **50 req/min**. Réplicas backend: **mínimo 3**. Backoff del webhook: **base 2 s, máx 60 s**. Reconciliación por polling de respaldo. | Define rate limits, réplicas, backoff y reconciliación para carga media operativa. |
| **OD-09** | **Compatibilidad TLS**: ¿se puede exigir **solo TLS 1.3** o hay clientes legacy (navegadores/AV) que necesitan 1.2? | **Resuelto — Solo TLS 1.3** (confirmado). TLS 1.2 deshabilitado; sin ventana de compatibilidad. | Máxima seguridad; coherente con RNF-01.a. |
| **OD-10** | **Ventanas de mantenimiento**: ¿existen mantenimientos planificados que suspendan la operación (p. ej. patching del documento)? Si existen, ¿el dashboard debe estar degradado (solo lectura de caché) o caído? | **Resuelto — Mantenimiento anunciado ≥ 48 h + modo caché con banner**. Durante mantenimiento el dashboard muestra caché con banner `MODO MANTENIMIENTO`, sin conteo para SLA. | Define el modo caché/degradado oficial. |
| **OD-11** | **Tipo de gráfico de turnos**: **barras verticales** (propuesta) vs línea vs mixto. | **Resuelto — Barras verticales** (3 barras MAÑANA/TARDE/NOCHE; precisas para conteos por turno, legibles de lejos). | Cambia la lectura del gráfico y el test de aceptación CA-04.x. |
| **OD-12** | **Rollover de turnos operativos**: confirmado **3 turnos fijos** (MAÑANA 06-14, TARDE 14-22, NOCHE 22-06). El turno NOCHE cruza medianoche; la fecha lógica es la de **inicio** del turno. | Turnos fijos operativos, no franjas de 3h. Requiere lógica especial para `fin_min < inicio_min` en el backend y UI. | Resuelto — no queda decisión pendiente. |
| **OD-13** | **Cifrado extremo a extremo navegador**: ¿se exige cifrado a nivel aplicación también en el tramo navegador (p. ej. WebCrypto con clave por sesión) o basta con TLS 1.3 + WSS + autorización? | **Resuelto — TLS 1.3 + WSS + RBAC basta** (confirmado). Sin WebCrypto en navegador; la firma HMAC-SHA256 adicional cubre solo Apps Script↔backend. | Evita gestión de clave en cliente, superficie XSS ⇒ clave, y complejidad operativa. |
| **OD-14** | **Proveedor de almacenamiento de historiales**: ¿PostgreSQL gestionado (propuesto) u otra opción (D1, R2 + SQLite local)? | **Resuelto — PostgreSQL gestionado** (confirmado). PITR, failover, RPO 15 min, RTO 2 h (RNF-14). §3.4 ya dice PostgreSQL (failover). No queda D1/R2/Oracle como opción activa. | Confirmado: elimina alternativas; topología y RNF-14 ya coherentes. |
| **OD-15** | **Numeración de "Intervenciones"**: ¿"Intervenciones" de una unidad/turno es el **total de la hoja** o un subconjunto definido por el analista? ¿Cómo se mapea cada hoja del documento a estas 5 series? | **Resuelto — Mapeo 1:1 hojas→series** (4 KPI, regional, turnos, ranking), documentado y validado por el normalizador de Apps Script (cabeceras contra allowlist). | Define el significado de los 3 gráficos; sin mapeo claro la spec de datos no es implementable. |

---

## 15. Trazabilidad

Matriz **RF ↔ RNF ↔ amenaza mitigada ↔ criterio de aceptación ↔ visual**. Confirma cobertura completa: cada RF tiene RNF, amenaza y criterio; cada amenaza tiene al menos un RF/RNF.

| RF | RNF asociados | Amenazas mitigadas | Criterios de aceptación | Visual |
|----|----------------|--------------------|--------------------------|--------|
| **RF-01** (Transmisión segura) | RNF-01.a–g, RNF-02.a–b, RNF-03.f, RNF-05.g, RNF-11.a–b, RNF-12.a/f | AM-03 (MITM), AM-04 (suplantación del origen), AM-05 (replay/tampering), AM-14 (secreto en reposo) | CA-01.1 – CA-01.8 | — (pipeline) |
| **RF-02** (KPIs) | RNF-04.a–b, RNF-07.a, RNF-08.e, RNF-09.d/f, RNF-11.d/f, RNF-15.b | AM-01 (acceso no autorizado), AM-02 (escalada), AM-06 (XSS en etiquetas), AM-13 (repudio de consulta) | CA-02.1 – CA-02.10 | VIS-01..04 |
| **RF-03** (Gráfico regional) | RNF-04.b, RNF-09.b/d/e, RNF-11.d, RNF-15.b | AM-01, AM-06 (etiqueta de unidad), AM-07 (datos maliciosos) | CA-03.1 – CA-03.6 | VIS-05 |
| **RF-04** (Tendencia y ranking) | RNF-04.b, RNF-09.b/d/e, RNF-11.d, RNF-15.b | AM-01, AM-06, AM-07 | CA-04.1 – CA-04.7 | VIS-06, VIS-07 |
| **RF-05** (UI táctica) | RNF-04.b/c, RNF-05.a–g, RNF-09.a–h, RNF-10.a–g, RNF-13.b | AM-01 (403), AM-10 (caché), AM-11 (clickjacking), AM-12 (CSRF), AM-06 (CSP/XSS), AM-07 (degradación DoS) | CA-05.1 – CA-05.9 | Global |
| **§7 (Modelo de datos)** | RNF-11.a–f, RNF-15.a–c | AM-05 (replay/idempotencia), AM-07 | (validado por CA-01.x, CA-02.x, CA-04.x) | — |
| **§8 (Amenazas)** | RNF-01..15 | AM-01 – AM-14 | (cada amenaza se cierra por al menos un CA) | — |
| **§9 (Claves)** | RNF-02, RNF-03.f, RNF-13 | AM-03, AM-04, AM-14 | CA-01.1, CA-01.3 | — |
| **§10 (API)** | RNF-01.d, RNF-03, RNF-12 | AM-01, AM-05, AM-12 | CA-01.2, CA-01.8 | — |
| **§11 (UI)** | RNF-09, RNF-10 | AM-01, AM-06, AM-10, AM-11 | CA-02.8, CA-05.1–CA-05.9 | Todos |

**Cobertura de amenazas → mitigación (todas cerradas):**

| Amenaza | Mitigación principal | Verificado por |
|---------|----------------------|----------------|
| AM-01 Acceso no autorizado | Login nativo JWT + RBAC por capacidad, fail-closed | CA-01.8, CA-02.9 |
| AM-02 Escalada de privilegios | Capacidades ortogonales; admin no ve datos | CA-02.9 |
| AM-03 MITM de WSS | TLS 1.3 + WSS + firma HMAC del webhook | CA-01.1, CA-01.3 |
| AM-04 Suplantación del origen (webhook) | Firma HMAC + rotación + anti-replay + secreto no versionado | CA-01.2 |
| AM-05 Replay WSS | Firma HMAC + seq monotónico + event_id UNIQUE | CA-01.6 |
| AM-06 XSS vía celdas | Escape React + CSP + catálogos fijos | CA-02.8, CA-03.3 |
| AM-07 DoS / datos maliciosos | Rate limits + límites de payload + validación | CA-01.2, CA-04.6 |
| AM-08 Manipulación del documento | Hash de contenido + firma HMAC + archivo append-only | CA-01.4 |
| AM-09 Exfiltración a terceros | Mínimo privilegio + export auditado + no-store | CA-02.9 |
| AM-10 Caché tras deslogueo | no-store + Clear-Site-Data + SW solo shell | CA-05.1 (parcial) |
| AM-11 Clickjacking | X-Frame-Options + frame-ancestors 'none' | (test de cabeceras) |
| AM-12 CSRF | Bearer en memoria + CORS allowlist + preflight | (test de cabeceras) |
| AM-13 Repudio de consulta | Auditoría de lecturas por `event_id` | CA-02.10 |
| AM-14 Secreto en reposo | Script Properties + secret manager + no versionado | (revisión de config) |

> **Nota sobre decisiones resueltas (todas las OD):**  
> - **OD-01 (TZ):** `America/Argentina/Buenos_Aires` · **OD-02 (base variación):** ayer_mismo_tramo · **OD-03 (color):** dirección del cambio · **OD-04 (sesión):** sin expiración sala 24/7, sin MFA/step-up · **OD-05 (auth):** JWT nativo (usuario+contraseña) en el backend, sin Keycloak/MFA · **OD-06 (multi-sala):** una instancia = una sala · **OD-07 (retención):** supervisor 90 d / auditor 60 m · **OD-08 (volumen):** medio 100–1 000/día · **OD-09 (TLS):** solo 1.3 · **OD-10 (mantenimiento):** anunciado ≥48 h + caché · **OD-11 (gráfico):** barras verticales · **OD-12 (rollover):** 3 turnos fijos · **OD-13 (E2E):** TLS+WSS+RBAC basta · **OD-14 (almacenamiento):** PostgreSQL gestionado · **OD-15 (mapeo Google Sheets):** 1:1 hojas→series.  
> Todas las **15 decisiones abiertas** están resueltas y reflejadas en la tabla §14.2 y en el cuerpo del documento.

---

## Anexo A — Glosario

| Término | Definición |
|---------|------------|
| **SIFCOP** | Sistema institucional de origen de los indicadores. |
| **Google Sheets** | Hoja de cálculo en la nube del proveedor; fuente de datos del sistema (SIFCOP). |
| **Apps Script** | Plataforma de scripting de Google vinculada al documento; ejecuta el trigger y firma el webhook. |
| **Webhook firmado** | Notificación HTTP `POST` de Apps Script al backend, autenticada con HMAC-SHA256. |
| **Instantánea (snapshot)** | Estado completo y absoluto de los indicadores en un instante. |
| **Payload firmado** | Cuerpo JSON del webhook firmado con HMAC-SHA256 sobre su cadena canónica. |
| **Cadena canónica** | Concatenación firmada (`webhook_id`, `key_id`, `nonce`, `timestamp`, `schema_version`, hash del cuerpo). |
| **Key-Id** | Identificador de la versión del secreto del webhook vigente. |
| **WSS** | WebSocket sobre TLS. |
| **Cold start** | Carga inicial del dashboard vía REST antes de abrir el WSS. |
| **Seq** | Número monótono por sala que ordena y deduplica instantáneas. |
| **event_id** | UUIDv7 único de un evento; clave de idempotencia. |
| **Capacidad** | Permiso atómico (p. ej. `dash.view.live`); base del RBAC. |
| **Turno operativo** | Bloque de 8 horas (MAÑANA 06-14, TARDE 14-22, NOCHE 22-06); hay 3 por día. |
| **Ticket WSS** | Credencial de un solo uso (60 s) para abrir el WSS. |
| **HMAC-SHA256** | Código de autenticación de mensajes que acredita el origen y la integridad del webhook. |
| **Script Properties** | Almacén de propiedades del script de Apps Script, cifrado en reposo, donde reside el secreto del webhook. |
| **Zero Trust** | Marco de seguridad: nunca confiar, verificar siempre, mínimo privilegio, etc. |
| **JWT nativo** | Token firmado por el backend que acredita al operador tras un login local (usuario+contraseña); base de la sesión y del RBAC. |
| **Argon2id** | Función de hash de contraseñas con sal; algoritmo de almacenamiento de credenciales locales. |

## Anexo B — Catálogo de variables (Tailwind/CSS)

Mapa listo para `tailwind.config.js` y `:root` (los mismos hex que §11.2):

```js
// tailwind.config.js (extracto)
theme: {
  extend: {
    colors: {
      base:     "#05080F",
      surface:  "#0B1220",
      surface2: "#111A2B",
      border:   "#1E2D3D".replace("2D","3D"), // = #1E2A3D
      ink:      "#FFFFFF",
      ink2:     "#C7D2DE",
      muted:    "#8A9BB0",
      accent:   "#38BDF8",
      accent2:  "#0EA5E9",
      pos:      "#34D399",
      neg:      "#F87171",
      warn:     "#FBBF24",
      neutral:  "#94A3B8",
    },
    fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
  },
}
```

```css
:root{
  --bg-base:#05080F; --bg-surface:#0B1220; --bg-surface-2:#111A2B; --border:#1E2A3D;
  --text-primary:#FFFFFF; --text-secondary:#C7D2DE; --text-muted:#8A9BB0;
  --accent:#38BDF8; --accent-strong:#0EA5E9; --accent-soft:rgba(56,189,248,.14);
  --pos:#34D399; --neg:#F87171; --warn:#FBBF24; --neutral:#94A3B8;
}
/* numeración tabular global para cifras */
.num, .kpi-value, table td, .axis text{ font-variant-numeric: tabular-nums; }
/* foco visible accesible */
:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; }
```

---

**Fin de la especificación.** Siguiente fase (requiere aprobación): `plan.md` (arquitectura de detalle y decisiones de implementación) y `tasks.md` (plan de trabajo desglosado).