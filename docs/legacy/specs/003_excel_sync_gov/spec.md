# SPEC-003 — Sistema de Sincronización en Tiempo Real "Excel-to-Web"

**Enfoque:** Zero Trust (Arquitectura de Seguridad Gubernamental)
**Estado:** Especificación (Fase 1 — SDD). Pendiente de aprobación antes de generar `plan.md` y `tasks.md`.
**Versión del documento:** 0.1 (borrador para revisión)
**Stack:** Python/PyInstaller (agente local) · FastAPI (backend) · React/Cloudflare Pages (frontend) · Cloudflare R2 (almacenamiento y backups)

---

## 1. Contexto y objetivos

### 1.1 Problema

Los organismos p param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) blica publican cifras en ficheros Excel que son actualizados manualmente por analistas. Este modelo genera:

- **Retraso en la publicación** (decenas de minutos o horas entre el guardado del fichero y la disponibilidad del dato).
- **Pérdida de trazabilidad**: no existe registro fiable de *quién* cambió *qué* y *cuándo*.
- **Puntos de conflicto**: varios analistas editando copias divergentes del mismo fichero.
- **Superficie de exposici param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n**: ficheros circulando entre equipos por canales no governados.
- **Auditoría imposible**: las actualizaciones no son reproducibles ni atribuibles.

### 1.2 Objetivo general

Construir un sistema que **detecte automáticamente** los cambios guardados en un fichero Excel en el equipo del analista, **calcule únicamente el parche diferencial** de esos cambios, lo **transmita de forma cifrada** a un backend bajo **verificación constante de identidad**, lo **archive de forma inmutable** antes de propagarlo, y lo **redistribuya en tiempo real** a todos los dashboards web autenticados.

### 1.3 Objetivos específicos

| ID | Objetivo |
|----|----------|
| OBJ-1 | Detectar el guardado del fichero Excel en el cliente sin intervenci param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n del usuario e ignorando ficheros temporales o irrelevantes. |
| OBJ-2 | Transmitir **solo el delta** (parche), minimizando exposición de datos y ancho de banda. |
| OBJ-3 | Garantizar integridad y confidencialidad del dato en tránsito (doble capa: TLS + AES-256 a nivel aplicación). |
| OBJ-4 | Mantener una **copia inmutable** del estado de datos antes de cualquier redistribución, con retención y capacidad de replay. |
| OBJ-5 | Reflejar el cambio en el dashboard en **tiempo real** (p95 < 2 s) sin recarga manual. |
| OBJ-6 | Ofrecer **trazabilidad total**: quién, qué, cuándo, desde dónde, con resultado. |
| OBJ-7 | Resistir **suplantación de agente**, replay, manipulación en tránsito, acceso no autorizado y exfiltración. |
| OBJ-8 | Permitir **replay** completo del histórico para reconstrucción forense y auditoría. |

### 1.4 Actors

| Actor | Descripción |
|-------|-------------|
| **Analista** | Usuario final que edita el fichero Excel en su puesto. No interactúa directamente con el sistema más allá de guardar. |
| **Supervisor de datos** | Usuario autenticado del dashboard con rol `viewer` o `editor`. |
| **Administrador de la plataforma** | Gestiona agentes, claves, RBAC y replay. |
| **Vigilante Local (agente)** | Ejecutable compilado (PyInstaller) que se ejecuta en el puesto del analista. |
| **Backend FastAPI** | Servicio que valida, descifra, archiva y redistribuye. |
| **Cloudflare R2** | Almacenamiento S3-compatible de historiales inmutables. |
| **Dashboard React** | SPA servida desde Cloudflare Pages, consumida por navegador. |

---

## 2. Enfoque Zero Trust

### 2.1 Principios aplicados

| # | Principio | Traducción concreta en este sistema |
|---|-----------|--------------------------------------|
| P1 | **Nunca confiar, verificar siempre** | Ningún request se acepta sin verificación explícita de identidad (agente, usuario) y autorización. No se confía en la red, ni en el header, ni en el payload. |
| P2 | **Red de confianza cero** | El agente opera desde la red del usuario (potencialmente no segmentada o filtrada). Cada salto (agente param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) API, API param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) R2, API param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) navegador) se autentica y cifra de forma independiente. |
| P3 | **Mínimo privilegio** | El agente solo puede enviar parches; el visor solo lee; R2 solo admite `PutObject` con tamaño acotado; los roles se separan. |
| P4 | **Defensa en profundidad** | Cifrado en tránsito (TLS) + cifrado en reposo (AES-256) + cifrado a nivel aplicación + control de acceso + auditoría + rate limiting + WAF. |
| P5 | **Superficie de ataque mínima** | El agente expone un único endpoint de salida (egress) a allowlist; no abre puertos de escucha; el dashboard no expone la API Key. |
| P6 | **Asumir la red comprometida** | Aunque un atacante controle la red local o el TLS del cliente, el payload sigue siendo inútil sin la clave y la validación del backend. |
| P7 | **Trazabilidad total** | Cada acción (registro, parche, respaldo, diffusión, login, replay) deja un evento de auditoría inmutable. |

### 2.2 Aplicación a cada pieza

#### 2.2.1 Verificación del agente (Vigilante Local)
- El agente se **registra** en el backend con una **API Key gubernamental** emitida por el administrador (nunca hardcodeada en el `.exe`).
- Cada `heartbeat` y cada `PATCH` incluyen la API Key (cabecera `Authorization: Bearer`) + **huella del binario** (SHA-256) + **ID de agente**.
- El backend verifica: (a) Key activa y no revocada, (b) hash del binario coincide con el firmado/autorizado (anti-tamper), (c) versión de esquema soportada, (d) User-Agent y versión de agente coherentes con el registro.
- Un agente no registrado o revocado recibe `401/403` inmediatamente y se auto-deshabilita localmente.
- **Anti-replay del agente**: cada request lleva `X-Agent-Nonce` + `X-Agent-Timestamp`; el backend rechaza repeticiones dentro de una ventana (±5 min).

#### 2.2.2 API Key + rotación
- Formato: `<env>.<id_agente>.<secreto>` — el `id_agente` permite revocar individual sin rotación global.
- **Cifrada en reposo** con DPAPI / Windows Credential Manager en el cliente; en el backend almacenada como **hash** (Argon2id) — nunca en claro.
- **Rotación**: cada **90 días**; y de forma inmediata ante sospecha. Ventana de **solapamiento de 24 h** con doble clave válida para no cortar la operación. La clave antigua se revoca a la fuerza tras la ventana.
- La rotación de la API Key **no** requiere reempaquetar el `.exe`.

#### 2.2.3 Autenticación/autorización de usuarios del dashboard
- **OIDC** contra el IdP gubernamental (issuerAllowed). Access token JWT corto (**15 min**) + refresh token rotativo (**7 días**). El dashboard **nunca** almacena la API Key del agente.
- Autorización por **RBAC** evaluado en el backend por cada mensaje WSS y cada endpoint (no solo en el frontend).

#### 2.2.4 RBAC
| Rol | Lectura dashboard | Envío de cambios | Replay | Gestión agentes/claves | Ver auditoría |
|-----|-------------------|------------------|--------|--------------------------|---------------|
| `viewer` | ✅ | ❌ | ❌ | ❌ | Solo sus eventos |
| `editor` | ✅ | ✅ (vía API) | ❌ | ❌ | Sus eventos |
| `auditor` | ✅ (solo lectura + auditoría) | ❌ | ❌ | ❌ | ✅ todo |
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ todo |

Principio de mínimo privilegio: por defecto todo usuario es `viewer`; los roles superiores se otorgan explícitamente y se auditan.

#### 2.2.5 Mínimo privilegio en R2
- El backend accede a R2 con una **Service Account Token** de alcance mínimo: solo el bucket de sync, solo `s3:PutObject` y `s3:GetObject` en prefijos concretos. **Nunca** `DeleteObject` (inmutabilidad), nunca acceso a otros buckets.
- **Object Lock / versionado** habilitado: los respaldos son *write-once-read-many*; nadie puede sobrescribir ni borrar.
- R2 no es accesible públicamente (0 endpoints públicos). Toda lectura de datos pasa por el backend, tras autorización.
- **Riesgo:** el token de servicio vive en el backend; se rota trimestralmente y seCache en gestor de secretos (§9).

#### 2.2.6 Cero confianza en el cliente
- El navegador **nunca** recibe la API Key ni la clave simétrica de cifrado de datos.
- El dashboard no confía en validaciones hechas en el cliente para autorización; el backend revalida.
- Los estados de UI derivados del servidor se consideran no confiables para decisiones de negocio.

#### 2.2.7 Identidad de servicio
- El agente tiene **identidad propia** (no la del usuario), auditada por separado. Un agente compromise no puedeossier acciones de un usuario en el dashboard.
- Todas las acciones del agente quedan atribuidas a un `agent_id` + `actor_usuario` (derivado de la máquina/sesión, no directamente del fichero), ambas en el log.

---

## 3. Arquitectura de alto nivel

### 3.1 Diagrama de flujo

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  ESTACIÓN DE TRABAJO DEL ANALISTA  (red no segmentada - no confiable)          │
│                                                                               │
│   ┌─────────────┐        save (Ctrl+S) / cierre                            │
│   │  Microsoft   │ ─────────────────────────────────────────────┐             │
│   │  Excel 2016+ │                                              ▼             │
│   └─────────────┘                                    ┌──────────────────────┐ │
│                                                       │  VIGILANTE LOCAL     │ │
│                                                       │  (Vigilante.exe)     │ │
│                                                       │  - PyInstaller       │ │
│                                                       │  - Monitorea carpeta │ │
│                                                       │  - Ignora ~$ / .tmp │ │
│                                                       │  - Compara vs hash   │ │
│                                                       │  - Calcula PARCHE   │ │
│                                                       │  - Cifra AES-256    │ │
│                                                       └──────┬───────────────┘ │
│                                                              │                 │
│                                              API Key + parche cifrado        │
│                                              (HTTPS/TLS 1.3, egress          │
│                                               allowlist)                    │
└──────────────────────────────────────────────────────────┼─────────────────┘
                                                           │
                                                           ▼
                        ┌──────────────────────────────────────────────────┐
                        │  BACKEND — FastAPI  (perímetro de confianza,     │
                        │  mTLS + WAF + rate limit)                        │
                        │                                                  │
                        │  1. Valida API Key / agente / anti-replay       │
                        │  2. Descifra AES-256 (clave de tenant)          │
                        │  3. Idempotencia (id_operación, cursor)          │
                        │  4. ESCRIBE respaldo inmutable en R2  ◄── PERSIST │
                        │  5. Actualiza estado / versión                   │
                        │  6. EMITE por WebSocket Seguro (WSS)            │
                        └───────────┬──────────────────────────┬───────────┘
                                    │                          │
                                    ▼ (s3 PutObject)          ▼ (wss push)
                        ┌───────────────────────┐   ┌──────────────────────────┐
                        │  CLOUDFLARE R2        │   │  DASHBOARD REACT        │
                        │  (bucket inmutable,    │   │  (Cloudflare Pages)     │
                        │   versionado, Object   │   │  - OIDC login           │
                        │   Lock, retenc. 365 d) │   │  - WSS subscribe        │
                        │  Historial + replay    │   │  - Gráficos/contadores  │
                        │  Solo vía backend      │   │  reactivos SIN recargar  │
                        └───────────────────────┘   └──────────────────────────┘
```

### 3.2 Componentes y responsabilidades

| Componente | Tecnología | Responsabilidad | NO-responsabilidad |
|------------|------------|-----------------|---------------------|
| Vigilante Local | Python→PyInstaller `.exe` | Detección de cambios, diff, cifrado, envío, heartbeat | Almacenar datos persistently, exponer puertos |
| Backend | FastAPI + ASGI | Validación, descifrado, idempotencia, persistencia R2, fan-out WSS, auditoría | Leer el Excel directamente, conocer rutas locales |
| Almacenamiento | Cloudflare R2 | Respaldo inmutable, versionado, replay | Aceptar escritura desde fuera del backend |
| Frontend | React + CF Pages | Autenticación, suscripción WSS, render de datos | Confiar en API Key, decidir autorización |

---

## 4. Alcance / No-alcance

### 4.1 En alcance (In scope)
- Vigilante local que monitorea **un conjunto configurable de ficheros/carpetas Excel** en el puesto.
- Detección de guardado, filtrado de temporales, cálculo de **parche diferencial por celda**.
- Cifrado AES-256 del parche y transporte por HTTPS/TLS.
- Registro, heartbeat, subida de parche y consulta/replay en FastAPI.
- Respaldo inmutable por operación en Cloudflare R2 + versionado + retención.
- Distribución en tiempo real a dashboards por WebSocket Seguro (WSS).
- Dashboard React con gráficos y contadores reactivos.
- Autenticación OIDC, RBAC, auditoría, rate limiting, gestión/rotación de claves.

### 4.2 Fuera de alcance (Out of scope — explícito)
- **Edición bidireccional**: el sistema NO escribe de vuelta al fichero Excel del analista (one-way Excel→Web en esta versión).
- **Resolución de conflictos de edición concurrente** entre múltiples analistas sobre el mismo fichero (se detecta y se registra, pero la estrategia de merge es futura).
- **Escritura fuera de Excel**: no se soportan CSV/ODS/Google Sheets en esta iteración.
- **macOS/Linux**: el agente es solo Windows (Excel 2016+ Windows). Ver OD-08.
- **Apps móviles nativas** del dashboard.
- **Pipeline de ML/analítica avanzada** sobre los datos más allá de graficar.
- **Multi-región activa-activa** del backend.
- **Firma calificada (eIDAS QES)** de documentos: solo firma de código del ejecutable.
- **Cifrado extremo a extremo puro donde el backend nunca ve el dato** (el backend sí descifra para poder retransmitir; ver OD-01).

---

## 5. Requisitos funcionales (EARS)

> Sintaxis **EARS** (Easy Approach to Requirements Syntax). Patrones usados: `CUANDO … ENTONCES`, `SI … ENTONCES`, `MIENTRAS …`, `EL SISTEMA DEBE …`. El actor se explicita entre paréntesis.

### RF-01 — Monitoreo y Cifrado Local (texto original literal)

> **RF-01 — Monitoreo y Cifrado Local:** CUANDO el usuario guarde el archivo Excel, EL SISTEMA (ejecutable local) detectará el cambio ignorando temporales, calculará solo las diferencias de datos (parche) y lo encriptará utilizando AES-256.

**Desglose (conserva la letra del RF original):**

- **RF-01.a.** CUANDO el usuario guarde el archivo Excel, ENTONCES EL SISTEMA (ejecutable local) detectará el evento de guardado mediante monitoreo del sistema de archivos sobre las rutas configuradas.
- **RF-01.b.** CUANDO se detecte un evento de guardado, ENTONCES EL SISTEMA (ejecutable local) **ignorará** los archivos temporales (`.tmp`, `~$*`, `.~lock*`, `.asd`, etc.) y no generará parche por ellos.
- **RF-01.c.** CUANDO se detecte un cambio real de datos, ENTONCES EL SISTEMA (ejecutable local) calculará **solo las diferencias** respecto al último estado aplicado, produciendo un **parche** con las celdas/columnas modificadas, no el fichero completo.
- **RF-01.d.** CUANDO el parche haya sido calculado, ENTONCES EL SISTEMA (ejecutable local) lo **encriptará** utilizando **AES-256** antes de cualquier transmisión.
- **RF-01.e.** MIENTRAS el ejecutable local esté en ejecución, EL SISTEMA mantendrá una copia en memoria del último hash aplicado por documento para el cálculo diferencial.
- **RF-01.f.** SI el hash del fichero en disco difiere del último hash aplicado, ENTONCES EL SISTEMA (ejecutable local) disparará el cálculo del parche; en caso contrario, no transmits nada.
- **RF-01.g.** SI el fichero supera el tamaño máximo permitido, ENTONCES EL SISTEMA (ejecutable local) registrará el evento, lo notificará y **no** intentará transmitir un parche.

### RF-02 — Transmisión Segura (texto original literal)

> **RF-02 — Transmisión Segura:** SI el ejecutable local detecta cambios, ENTONCES EL SISTEMA enviará el payload encriptado al endpoint de FastAPI validándose mediante una API Key gubernamental y conexión HTTPS.

**Desglose:**

- **RF-02.a.** SI el ejecutable local detecta cambios, ENTONCES EL SISTEMA enviará el payload **encriptado** (AES-256, RFC 3394 key wrap en transporte) al endpoint de FastAPI.
- **RF-02.b.** SI el agente se comunica con el backend, ENTONCES EL SISTEMA validará la identidad mediante una **API Key gubernamental** (cabecera `Authorization: Bearer`).
- **RF-02.c.** SI el agente se comunica con el backend, ENTONCES EL SISTEMA usará **conexión HTTPS** con TLS 1.3 (mínimo TLS 1.2) y verificación de certificado (sin `verify=false`).
- **RF-02.d.** CUANDO el agente envíe un payload, ENTONCES EL SISTEMA incluirá `X-Agent-Id`, `X-Agent-Timestamp`, `X-Agent-Nonce` y la huella `X-Agent-Bin-SHA256` para verificación y anti-replay.
- **RF-02.e.** SI la API Key es inválida, está revocada o expirada, ENTONCES EL SISTEMA (backend) rechazará el payload con `401/403` y lo registrará como evento de seguridad.
- **RF-02.f.** SI el nonce ya fue usado dentro de la ventana temporal, ENTONCES EL SISTEMA (backend) rechazará el request con `409` por intento de replay.

### RF-03 — Almacenamiento Inmutable (texto original literal)

> **RF-03 — Almacenamiento Inmutable:** CUANDO FastAPI reciba y valide un payload exitoso, EL SISTEMA guardará una copia de respaldo del estado de los datos en un bucket seguro de Cloudflare R2 antes de retransmitir.

**Desglose:**

- **RF-03.a.** CUANDO FastAPI reciba y valide un payload exitoso, ENTONCES EL SISTEMA guardará una **copia de respaldo del estado de los datos** en el bucket seguro de Cloudflare R2 **antes de retransmitir**.
- **RF-03.b.** CUANDO el respaldo se escriba en R2, ENTONCES EL SISTEMA aplicará **inmutabilidad** (Object Lock / versionado, sin `DeleteObject`) de modo que el respaldo no pueda sobrescribirse ni borrarse.
- **RF-03.c.** CUANDO se persista el estado, ENTONCES EL SISTEMA asociará cada respaldo a un `id_operación`, `id_documento`, `id_tenant`, timestamp y versión de esquema.
- **RF-03.d.** SI la escritura en R2 falla, ENTONCES EL SISTEMA **no** retransmitirá el cambio (falla el proceso de forma segura) y devolverá error `503` al agente para reintento.
- **RF-03.e.** EL SISTEMA DEBE retener los respaldos según la política de retención vigente (§6, RNF) y soportar su replay posterior.

### RF-04 — Distribución en Tiempo Real (texto original literal)

> **RF-04 — Distribución en Tiempo Real:** CUANDO FastAPI termine de guardar el respaldo, EL SISTEMA emitirá los datos actualizados a todos los clientes web autenticados a través de WebSockets Seguros (WSS).

**Desglose:**

- **RF-04.a.** CUANDO FastAPI termine de guardar el respaldo, ENTONCES EL SISTEMA emitirá los datos actualizados a **todos los clientes web autenticados** autorizados a ver ese documento.
- **RF-04.b.** CUANDO se emita a los clientes web, ENTONCES EL SISTEMA utilize **WebSockets Seguros (WSS)** sobre TLS, autenticados con el token de sesión del usuario.
- **RF-04.c.** SI un cliente web no está autenticado o no tiene rol para el documento, ENTONCES EL SISTEMA no le enviará el mensaje (filtrado por autorización, no por oscuridad del cliente).
- **RF-04.d.** CUANDO se envíe un mensaje, ENTONCES EL SISTEMA incluirá un **número de versión** y un **cursor de sincronización** para que el cliente pueda detectar y re-sincronizar huecos.
- **RF-04.e.** SI un cliente pierde la conexión, ENTONCES EL SISTEMA le permitirá recuperar el estado missed mediante `GET /documents/{id}/state?since=<cursor>`.

### RF-05 — Interfaz Reactiva (texto original literal)

> **RF-05 — Interfaz Reactiva:** MIENTRAS el dashboard web (React) reciba transmisiones por WSS, EL SISTEMA actualizará los gráficos y contadores en tiempo real sin requerir que el usuario recargue la página.

**Desglose:**

- **RF-05.a.** MIENTRAS el dashboard web (React) reciba transmisiones por WSS, EL SISTEMA actualizará los **gráficos y contadores** en tiempo real **sin requerir que el usuario recargue la página**.
- **RF-05.b.** CUANDO el dashboard reciba un mensaje `data.updated`, ENTONCES EL SISTEMA (frontend) actualizará de forma reactiva (state/store) los componentes afectados.
- **RF-05.c.** SI el frontend detecta un hueco de versiones (cursor desalineado), ENTONCES EL SISTEMA disparará una re-sincronización completa desde el cursor.
- **RF-05.d.** MIENTRAS la conexión WSS esté caída, EL SISTEMA (frontend) mostrará un indicador de estado degradado y reconectará con backoff exponencial.
- **RF-05.e.** EL SISTEMA DEBE decoupling la lógica de presentación del transporte (capa WebSocket encapsulada) para permitir test unitario del frontend sin backend.

---

## 6. Requisitos no funcionales (RNF)

Valores concretos, verificables.

### RNF-01 — Cifrado en tránsito
- TLS **1.3** obligatorio para toda comunicación (agente→API, API→navegador, API→R2). TLS 1.2 solo con cipher-suites aprobados (ECDHE + AEAD).
- Verificación estricta de certificado y hostname; **prohibido** `verify=False` / `--insecure`.
- Redirección **obligatoria** de `http://` a `https://` (HSTS: `max-age=31536000; includeSubDomains; preload`).
- mTLS opcional entre agente y API para documentos de mayor criticidad (ver OD-05).

### RNF-02 — Cifrado en reposo y en aplicación
- Payload del parche cifrado con **AES-256-GCM** (CSE) a nivel aplicación (no solo TLS).
- Respaldos en R2 cifrados en reposo con cifrado administrado por el proveedor (SSE) **y**, para el backup de application-level, con la clave de tenant ya aplicada antes de subir (doble capa).
- Cada tenant tiene una **clave de datos** distinta (AES-256), envuelta por una **clave maestra (KEK)** en un gestor de secretos.
- **GCM vs CBC+HMAC:** se elige **AES-256-GCM** porque (a) cifra y autentica en una sola operación (AEAD), lo que elimina la clase de ataques de *encrypt-then-MAC* mal implementado; (b) es hardware-accelerated (AES-NI) con alto rendimiento; (c) reduce Implementación y superficie de error. CBC+HMAC exige dos claves separadas, IV no reutilizable y orden correcto de composición → más propenso a fallos y más difícil de revisar. *La decisión está sujeta a validación del usuario (ver OD-02 si el marco gubernamental exige FIPS-approved en modo CBC).*

### RNF-03 — Gestión y rotación de claves
- **Rotación de la clave de datos de tenant**: cada **180 días**, o inmediatamente ante compromiso.
- **Rotación de la API Key del agente**: cada **90 días** con ventana de solapamiento de **24 h**.
- **Rotación de la Service Account de R2**: cada **90 días**.
- **KEK (clave maestra)**: rotación anual; el re-unwrap de las claves de tenant sin re-cifrar el histórico (envelope encryption).
- Las versiones de clave se versionan (`kid`); el descifrado usa la `kid` del sobre; tras la ventana de retención, la clave se destruye de forma segura.
- **Nunca** se registran claves ni payloads en claro en logs (regla de redacción en el pipeline de logging).

### RNF-04 — Rendimiento (latencia)
- **Objetivo clave: p95 < 2 s** desde el guardado del Excel hasta el refresco del gráfico en el dashboard.
  - Presupuesto de latencia (objetivo, no medido todavía):
    - Detección + diff + cifrado en el agente: **≤ 300 ms**.
    - Upload + validación + descifrado + persistencia R2 en backend: **≤ 700 ms**.
    - Fan-out WSS + render en navegador: **≤ 1000 ms**.
  - p99 **< 4 s** (tolerancia a picos).
- Tiempo de cold start del agente: **≤ 3 s**.
- Cálculo del parche debe escalar a ficheros de hasta el máximo permitido sin degradar el objetivo (ver RNF-08).

### RNF-05 — Disponibilidad y resiliencia
- Backend FastAPI: **99,9 % de disponibilidad** mensual objetivo (SLO).
- Reconexión WSS en cliente con **backoff exponencial** (base 1 s, factor 2, jitter, tope 60 s) y re-sincronización por cursor.
- Reintento de upload desde el agente: exponencial, hasta **5 intentos**, luego deja el parche en cola local cifrado.
- Estado sin pérdida: un parche confirmado por el backend NO se pierde aunque el cliente se desconecte (fuente de verdad = R2 + cursor del backend).

### RNF-06 — Observabilidad y auditoría (quién cambió qué y cuándo)
- **Registro de auditoría append-only** (append-only log) con **encadenamiento por hash** (cada entrada incluye el hash de la anterior) para detectar alteración.
- Eventos mínimos registrados: `agent.registered`, `agent.heartbeat`, `patch.received`, `patch.rejected`, `backup.persisted`, `data.broadcast`, `user.login`, `user.denied`, `replay.executed`, `key.rotated`.
- Cada evento: `timestamp` (UTC, ISO-8601), `actor_type` (agent/user/system), `actor_id`, `tenant_id`, `documento_id`, `id_operación`, `version`, `ip_origen`, `user_agent`, `resultado` (ok/denied/error), `detalle`.
- **Retención de auditoría: 7 años** (alineado a normativa gubernamental), en almacenamiento inmutable (R2 con Object Lock).
- Correlación: un `id_operación`/`request_id` conecta agente → backend → R2 → WSS → cliente (se propaga como header + campo en mensaje).
- Alertas: 5xx spikes, tasa de 401/403 (posible ataque), agent offline, backlog de parches.

### RNF-07 — Trazabilidad (reconstrucción)
- Es posible reconstruir el estado de un documento en cualquier instante pasado desde los respaldos inmutables de R2.
- Cursor de sincronización monótono e **globally unique** (por tenant) para.position exactamente qué operación falta.
- Cada operación es **idempotente** (mismo `id_operación` → mismo resultado), lo que permite reintentos seguros.

### RNF-08 — Recuperación ante desastres (DR)
- **RPO (Recovery Point Objective)**: **≤ 5 min** de pérdida de datos operativos (por el respaldo inmutable de cada operación aceptada).
- **RTO (Recovery Time Objective)**: **≤ 1 h** para restaurar el servicio de sincronización; **≤ 4 h** para reconstrucción completa desde backups si es desastre regional.
- R2: versionado + Object Lock + replicación (cross-region si el presupuesto lo permite, ver OD-09).
- **Backups del backend** (config, metadatos) también inmutables; procedure de restore ensayado trimestralmente.

### RNF-09 — Compatibilidad
- **Windows** 10 / 11 (x64); Windows Server 2019+ si se despliega como servicio.
- **Microsoft Excel 2016 o superior** (formatos `.xlsx`, `.xlsm`). `.xls` legado: fuera de alcance.
- Navegadores: **últimas 2 versiones** de Chrome, Edge y Firefox ( evergreen).
- El agente no requiere privilegios de administrador más allá de los necesarios para registro en servicio y acceso a las carpetas configuradas (mínimo privilegio).

### RNF-10 — Tamaño máximo (archivo y parche)
- **Tamaño máximo de fichero Excel**: **100 MB**.
- **Tamaño máximo de un parche comprimido+cifrado por request**: **5 MB**; si se supera, el backend devuelve `413`.
- **Máximo de operaciones (cambios de celda) por parche**: **10 000**.
- **Máximo de filas/columnas** por documento: **1 000 000 filas × 16 384 columnas** (límite físico de Excel; se admite subconjunto operativo de hasta **200 000 filas** para SLO, ver OD-07).
- Si el diff supera los límites, el agente **degrada con seguridad**: registra, notifica y pospone (no truncar silenciosamente).

### RNF-11 — Seguridad del ejecutable
- El `.exe` se compila con PyInstaller en modo **one-file, stripped**, sin incluir secretos ni el API Key.
- **Firma de código Authenticode** con certificado de entidad gubernamental (OV/EV). El cliente verifica la firma antes de ejecutar (SmartScreen/AppLocker); el backend verifica el hash firmado.
- Endurecimiento: sin `--debug`, sin símbolos de depuración, UPX opcional evaluado por riesgo, y verificación de integridad (self-check del hash).
- El agente no abre puertos de escucha; solo salida (egress) hacia la allowlist del backend.
- Registro en Windows como servicio / tarea programada con privilegios mínimos.

### RNF-12 — Rate limiting y anti-abuso (DoS)
- **Por agente (upload)**: ≤ **60 requests/min**, burst **10**; por parche ≤ **5 MB**; por segundo ≤ **2**.
- **Registro/heartbeat**: heartbeat cada **30 s**;>3/min se considera anómalo.
- **Por IP (login/dashboard API)**: ≤ **10/min** login, burst 3; bloqueo progresivo por intentos fallidos (lockout tras **5**).
- **WebSocket**: máx **500 conexiones concurrentes por tenant**; ping/pong cada **30 s**; cierre por inactividad tras **10 min**.
- Rate limiting en FastAPI (Redis/middleware) y, complementariamente, en el WAF/Edge.

### RNF-13 — Gestión de secretos
- **El secreto NO viaja dentro del ejecutable** (requisito de diseño, ver §9). Se provisiona post-instalación.
- Backend: secretos en gestor (Cloudflare Secrets / Vault), nunca en repo ni variables hardcodeadas en imagen; `.env` solo en local con plantilla.
- R2: Service Account Token de mínimo privilegio, rotado (ver §2.2.5).
- Datos de depuración: secretos redactados (`[REDACTED]`) en todos los logs.

### RNF-14 — Idempotencia y consistencia
- Toda operación lleva `id_operación` (UUIDv7, generado en el agente). Reintentar el mismo `id_operación` no crea respaldos ni emisiones duplicadas; devuelve el resultado original.
- Detección de conflicto de versión: si el backend detecta salto de versión inesperado, responde `409` y el agente re-sincroniza.

### RNF-15 — Localización y formatos
- Interfaz del dashboard en español (es-ES) como mínimo; prepared para i18n.
- Fechas/horas en UTC internamente, mostradas en la zona del usuario.
- Separadores y formatos numéricos localised conforme a locale del navegador.

---

## 7. Modelo de datos

### 7.1 Estructura del parche (Patch)

```jsonc
{
  "esquema_version": "1.0",              // versionado del esquema de parche (§7.4)
  "id_operacion": "018f...-uuidv7",       // idempotencia + correlación
  "tenant_id": "TEN-001",
  "id_documento": "DOC-9f3a",             // hash del path relativo, no la ruta absoluta
  "version_base": 41,                     // versión sobre la que se calculó el diff
  "timestamp": "2026-10-03T09:15:32.114Z",// UTC ISO-8601
  "hash_archivo_anterior": "sha256:...",  // para verificación de cadena
  "hash_archivo_nuevo": "sha256:...",
  "cambios": [                            // parche diferencial
    {
      "id_fila": 128,                      // índice de fila (1-indexado) o clave de negocio
      "columna": "D",                      // letra de columna o índice
      "celda": "D128",
      "valor_anterior": "1234",            // (opcional) depende de config de auditoría
      "valor_nuevo": "1299",
      "tipo": "numero",                    // numero | texto | fecha | booleano | formula_result
      "hash": "sha256:... del valor_nuevo",
      "timestamp": "2026-10-03T09:15:30.001Z"
    }
    // ... hasta 10 000 cambios (§RNF-10)
  ],
  "resumen": { "cambios": 1, "insertados": 0, "eliminados": 0 },
  "firma": "..."                           // firma del payload (opcional, ver OD-03)
}
```

Campos clave:
- `id_documento`: identificador estable derivado del **hash del path relativo** dentro de un tenant (evita exponer rutas absolutas → anti path-traversal y anti-fuga de metadatos).
- `id_operacion` (UUIDv7): **idempotencia** y correlación extremo a extremo.
- `hash`: permite verificar integridad celda a celda y detectar corrupción.
- `valor_anterior`/`valor_nuevo`: parche legible y auditable (su inclusión total está sujeta a política de minimización, ver OD-04).

### 7.2 Metadatos de sincronización (por documento, mantenidos por el backend)

```jsonc
{
  "tenant_id": "TEN-001",
  "id_documento": "DOC-9f3a",
  "version_actual": 42,                     // versión monótona del estado
  "ultimo_hash_aplicado": "sha256:...",     // último hash de fichero aplicado (para diff siguiente)
  "cursor_sincronizacion": "cur_0000000042",// cursor monótono por tenant (posiciona exactamente la op)
  "id_operacion_ultima": "018f...",
  "ts_ultima_actualizacion": "2026-10-03T09:15:33Z",
  "estado": "consistente"                   // consistente | desfasado | conflicto
}
```

- **`ultimo_hash_aplicado`**: el agente lo solicita/compara; el backend lo usa para validar coherencia.
- **`cursor_sincronizacion`**: único y monotónico por tenant; se envía al cliente para detectar huecos y re-sincronizar (`since=cursor`).
- **Idempotencia**: registro de `id_operación` → resultado aplicado (durante la ventana de retención). Reintento = misma respuesta.

### 7.3 Estructura del respaldo en R2 (objeto inmutable)

```
s3://<bucket-sync>/tenant=<TEN-001>/doc=<DOC-9f3a>/op=<id_operacion>/version=<v>/payload.<ext>
```
- Clave determinista por operación + versionado (ninguna sobrescritura).
- Metadatos del objeto: `tenant_id`, `id_documento`, `id_operacion`, `version`, `esquema_version`, `checksum`, `emitido_en`.
- Cifrado en reposo por SSE del proveedor + el payload ya viene cifrado a nivel aplicación.

### 7.4 Versionado del esquema de parche
- Campo `esquema_version` con formato `MAYOR.MENOR` (ej. `1.0`).
- **MAYOR**: cambios incompatibles (renombrado/eliminación de campos, cambio de tipo) → el agente y backend deben coincidir.
- **MENOR**: campos nuevos opcionales o aclaraciones → compatible hacia atrás.
- El **backend valida** que `esquema_version` esté en su rango soportado; si no, responde `422` y registra incompatibilidad.
- Política de soporte: se soportan las **2 últimas versiones MAYOR** durante al menos **6 meses** tras una salida.
- El dashboard consume un mensaje normalizado por el backend, desacoplado del esquema de parche del agente.

---

## 8. Modelo de seguridad y amenazas

| # | Amenaza | Vector / Impacto | Mitigación | RF/RNF |
|---|---------|------------------|------------|--------|
| T-01 | **Replay de parches** | Reenviar un parche válido para re-aplicar cambios antiguos / conmutar estado | `id_operación` idempotente + `X-Agent-Nonce`/`Timestamp` con ventana ±5 min + nonce store + versión monotónica; reenvío → respuesta idempotente sin efecto, o `409` | RF-02.f, RNF-14 |
| T-02 | **Manipulación del payload en tránsito** | Alterar valores del parche entre agente y API | Doble cifrado: TLS 1.3 + AES-256-GCM (AEAD, Nonce único, AAD vinculante) + hash por celda + verificación de integridad; cualquier alteración rompe el tag GCM → rechazo | RF-01.d, RF-02.c, RNF-01, RNF-02 |
| T-03 | **Suplantación de agente (API Key filtrada)** | Actor usa una API Key robada para inyectar parches falsos | API Key por-agente + hash Argon2id en reposo + rotación 90 d + revocación inmediata + verificación de huella del binario + auditoría por `agent_id` + mTLS opcional + allowlist de egress | RF-02.b/e, RNF-03, RNF-11, §2.2.1 |
| T-04 | **Acceso no autorizado al dashboard** | Navegador anónimo o con rol insuficiente lee datos | OIDC + JWT corto + RBAC evaluado **en backend** por endpoint y por mensaje WSS; cliente no decide autorización; WAF + rate limit + lockout | RF-04.c, §2.2.3/2.2.4, RNF-12 |
| T-05 | **Lectura no autenticada en R2** | Acceso directo al bucket (URL pública, token filtrado) | Bucket privado (0 endpoints públicos), acceso solo vía backend con Service Account de mínimo privilegio (sin Delete), todos los buckets ajenos bloqueados | §2.2.5, RNF-13 |
| T-06 | **Escalada de privilegios** | `viewer` intenta enviar cambios, replay o gestionar claves | RBAC estricto por endpoint (allowlist de rol→acción); rechazos 403 auditados; separación viewer/editor/auditor/admin | RF-04.c, §2.2.4, RNF-06 |
| T-07 | **DoS por flood de parches** | Agente (o atacante con su Key) inunda el backend/R2 | Rate limiting por agente/IP (60/min, burst 10; 2/s), tope 5 MB y 10 000 cambios por parche, quotas por tenant, WAF, circuit breaker; colas con backpressure | RF-01.g, RNF-10, RNF-12 |
| T-08 | **MITM en el lado local** | Interceptar en la red del analista (red segmentada) | Egress TLS 1.3 pinneado (opcional a CA), verificación de cert; payload además cifrado a nivel aplicación (inútil sin clave); anti-downgrade (HSTS); allowlist de destinos | RF-02.c, RNF-01, RNF-02 |
| T-09 | **Fórmulas/macros maliciosas de Excel** | El fichero contiene macros maliciosas o fórmulas peligrosas (inyección de fórmula) | El agente trata el Excel como **datos**, no lo ejecuta: no habilita macros, no evalúa fórmulas; solo lee valores; sanitiza valores de texto (neutraliza `=`, `+`, `-`, `@` al inicio cuando se renderizan en el dashboard); no ejecuta nada del fichero | RNF-09, §2.2.6 |
| T-10 | **Path traversal** | `id_documento` o ruta manipulable revela/sobrescribe ficheros fuera de la permitido | `id_documento` = hash del path relativo (no ruta absoluta); el agente restringe el monitoreo a un **allowlist de carpetas**; el backend nunca acepta rutas; R2 usa claves por tenant; validación de entrada | RF-01.a, §7.1 |
| T-11 | **Exfiltración fuera del perímetro** | Datos sensibles salen por un canal no monitored | Todo egress pasa por el allowlist del backend + TLS; sin puertos de escucha en el agente; cifrado en reposo; DLP/alertas por volumen anómalo; auditoría de todo parche (quién/qué) | RNF-01, RNF-06, §2.2.7 |
| T-12 | **Rogue Agent** (agente comprometido/malicioso que emite parches válidos pero erróneos) | Inyecta datos falsos aunque la Key sea legítima | Un agente solo puede escribir en los **documentos que tiene asignados** (scope por agente); verificación de hash/firma; validación de esquema y rangos; auditoría inmutable + reconciliación con respaldo anterior; alerta por desviación estadística | RF-01.f, RNF-07, §2.2.7 |
| T-13 | **Manipulación del ejecutable (anti-tamper)** | Binario parcheado para exfiltrar clave o inyectar código | Firma Authenticode; hash firmado esperado en backend; el secreto no va embebido; auto-verificación de integridad; SmartScreen/AppLocker | RNF-11, §2.2.1 |
| T-14 | **Suplantación de identidad de usuario en dashboard** | Robo de token / XSS | JWT corto + refresh rotativo + CSP estricta + sanitización (mitiga T-09 en render) + revocación en logout | RNF-03, §2.2.3 |

---

## 9. Gestión de claves y secretos

### 9.1 Modo de cifrado simétrico: **AES-256-GCM (AEAD)** — decisión y justificación

- **Elección:** AES-256 en modo **GCM** ( Galois/Counter Mode, con etiqueta de autenticación de 128 bits), Nonce (IV) de **96 bits aleatorio y único por operación**, y **AAD (Datos Autenticados Adicionales)** que vincula `tenant_id + id_documento + id_operación`.
- **Justificación (frente a CBC+HMAC):**
  1. **AEAD en una sola operación:** cifra y autentica simultáneamente. Elimina la clase de errores de *encrypt-then-MAC* mal implementado (orden de composición, claves separadas, reutilización de IV), que ha sido la causa habitual de vulnerabilidades en implantaciones governamentales.
  2. **Rendimiento:** AES-NI acelera AES-GCM por hardware, con un coste de autenticaci param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n marginal frente al objetivo de 2 s.
  3. **Menor superficie de error y de auditoría:** una única primitiva, un único modo de fallo (tag mismatch) y una única etiqueta que verificar.
  4. **Est param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) ndar gubernamental:** AES-GCM es v param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) lido bajo FIPS 140-3 y es el modo recomendado por SP 800-38D para nuevos dise param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) os.
  5. **Trade-offs asumidos:** GCM exige Nonce  param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) nico por clave (se garantiza con Nonce aleatorio de 96 bits + l param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) mite de uso por clave) y no ofrece confidencialidad de longitud. Se mitiga con el AAD y con el versionado de claves (`kid`), rotando la clave de tenant antes del riesgo de colisi param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n.
- **Reserva (OD-02):** si el marco de certificación exige un modo restringido (p. ej. GCM con datos clasificados o desactivación de GCM por política), la alternativa sería **AES-256-CBC + HMAC-SHA-256 en *encrypt-then-MAC*** con claves separadas; la implementación queda parametrizable para permitir ambos modos.

### 9.2 Dónde vive la clave simétrica

- **Clave de datos por tenant (DEK):** AES-256, una por `tenant_id`. Es la clave que cifra y descifra los parches.
- **Clave maestra (KEK):** AES-256_wrap / RSA-OAEP, custodiada en el **gestor de secretos** (Cloudflare Secrets o HashiCorp Vault). Nunca en la base de datos de aplicación ni en el repositorio.
- **Residencia por componente:**
  - **Agente local:** la DEK **no se embebe en el `.exe`**. Se provisiona en el registro (ver §9.4) y se almacena cifrada con **DPAPI** (CurrentUser) o en el **Windows Credential Manager**, protegida por el perfil del usuario del analista. Si el equipo lo permite, se libera solo dentro del proceso, en memoria, y se borra al detener el servicio.
  - **Backend FastAPI:** la DEK se resuelve en memoria bajo demanda desde el gestor de secretos, cacheada con TTL de **5 min**, y **nunca** se escribe en disco ni en logs.
  - **Dashboard React:** **nunca** recibe la DEK. Solo recibe datos ya descifrados y autorizados (ver OD-01).
- **AAD vinculante:** cada operación cifra con AAD = `tenant_id | id_documento | id_operacion | version`, de modo que un parche no puede reproducirse bajo otro documento, tenant u operación sin romper la autenticación.

### 9.3 Rotación de la clave de datos (envelope encryption)

1. Se genera una **DEK nueva** (`kid_n+1`) bajo la misma KEK.
2. Se actualiza el registro del tenant para que use `kid_n+1` en las **nuevas** operaciones.
3. Los respaldos históricos **no se re-cifran eagerly**: permanecen bajo `kid_n` y se descifran usando el `kid` registrado en el sobre/metadatos del objeto R2.
4. **Re-cifrado perezoso (lazy re-encryption):** cuando un objeto histórico con `kid_n` es accedido (replay, auditoría), se puede re-cifrar bajo `kid_n+1` en segundo plano ("write-once" → nueva versión con Object Lock), reduciendo coste.
5. Al cabo del **período de retención**, la `kid_n` se marca para destrucción segura. Si una política lo exige (defensa contra compromiso a posteriori), se puede aplicar *crypto-shredding*: eliminar la DEK hace inservible cualquier copia que dependa de ella.
6. **Cadena de confianza:** KEK anual → DEK semestral → versionado (`kid`). Toda rotación emite evento `key.rotated` en auditoría (§RNF-06).

### 9.4 Por qué el secreto NO viaja dentro del ejecutable

El `.exe` se distribuye a trav param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) s de workstation; cualquier secreto embebido queda recuperable por an param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) lisis de cadenas o ingenier param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) a inversa del binario, y el ejecutable se actualiza y cachea en discos, lo que multiplica la exposici param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n. Por tanto:

- El `.exe` **no contiene** API Key, DEK ni credenciales de R2.
- Tras la instalación, el agente se **registra** contra el backend con una **credencial de aprovisionamiento de un solo uso** (emitida por el administrador, TTL **15 min**, de un solo uso). El backend responde con la API Key del agente cifrada con la DEK de bootstrap, y la API Key se almacena en el Credential Manager del equipo.
- La **DEK por tenant** se entrega en el mismo canales, descifrada en el backend y guardada con DPAPI en el cliente.
- Si se pierde o se compromete una instalación, se **revoca** la API Key de ese `agent_id` (sin rotación global) y se emite una nueva.

### 9.5 Gestión de secretos (resumen)

| Secreto | Dónde vive | Cómo se protege | Rotación |
|---------|-------------|------------------|----------|
| DEK (tenant) | Gestor de secretos + memoria backend; DPAPI/CredMan en cliente | Envelope encryption bajo KEK; nunca en repo ni en logs | 180 d |
| KEK | Gestor de secretos | Control de acceso estricto,HSM/KMS si disponible | Anual |
| API Key agente | Credential Manager/DPAPI en cliente; hash Argon2id en backend | No va en el `.exe`; por-agente, revocable | 90 d (solape 24 h) |
| Token de servicio R2 | Gestor de secretos | Scope mínimo, sin Delete | 90 d |
| Credencial OIDC (dashboard) | Gestor / IdP | Secretos del cliente, rotación del secreto cliente |según IdP |
| Credencial de aprovisionamiento | Emitida por admin, un solo uso, TTL 15 min | Un solo uso, expira, auditada | n/a |

**Regla transversal (RNF-13):** ningún secreto, clave ni payload en claro aparece en logs, trazas, métricas ni repositorio; el pipeline de logging aplica redacción.

---

## 10. Contrato de API

- **Base:** `https://<api-host>/api/v1`
- **Autenticación agente:** `Authorization: Bearer <API_KEY>` + cabeceras `X-Agent-Id`, `X-Agent-Timestamp`, `X-Agent-Nonce`, `X-Agent-Bin-SHA256`, `X-Request-Id`, `X-Esquema-Version`.
- **Autenticación dashboard:** `Authorization: Bearer <JWT OIDC>` (15 min) + refresh endpoint.
- **Content type:** `application/json` (el campo `payload` viaja Base64 con el ciphertext AES-256-GCM).

### 10.1 REST — Agente

#### `POST /agents/register`
- **Request:** `{ "bin_sha256": "...", "version": "1.0.0", "hostname": "...", "tipo": "vigilante" }`
- **Response 201:** `{ "agent_id": "...", "api_key": "...", "kek_wrapped_dek": {...}, "config": { "documentos": [ { "id_documento": "...", "scope": ["..."] } ] } }`
- **Errores:** `400` (payload inválido), `401` (credencial de aprovisionamiento inválida/expirada), `409` (binario ya registrado), `429` (rate limit).
- **Nota:** entrega la DEK cifrada al cliente y la allowlist de documentos; la API Key solo se devuelve en el alta.

#### `POST /agents/heartbeat`
- **Request:** `{ "agent_id": "...", "estado": "activo", "documentos_monitoreados": N, "version": "1.0.0" }`
- **Response 200:** `{ "ok": true, "ts_servidor": "...", "siguiente_heartbeat_s": 30 }`
- **Errores:** `401` (Key inválida/revocada), `403` (agente revocado), `429`.
- **Frecuencia:** cada **30 s**; el backend marca el agente offline si no reporta en **90 s**.

#### `DELETE /agents/{agent_id}` (admin)
- **Response 204.** Revoca la API Key (soft revoke) y registra `agent.revoked`. Requiere rol `admin`.

### 10.2 REST — Parches y estado

#### `POST /documents/{id_documento}/patches`
- **Request (cuerpo lógico antes de cifrar):** objeto Patch de §7.1 → se serializa a JSON canónico, se cifra con AES-256-GCM y se envía como `{ "payload": "<base64>", "kid": "..." }` con el sobre `{ "nonce": "<b64 12B>", "aad_alg": "AESGCM", "kid": "..." }` en cabecera `X-Enc`.
- **Response 200/201:**
  ```json
  {
    "id_operacion": "018f...",
    "estado": "aplicado",
    "version": 42,
    "cursor": "cur_0000000042",
    "backup": { "bucket": "...", "clave": "tenant=.../op=.../version=42/payload.bin", "inmutable": true },
    "idempotente": false
  }
  ```
- **Errores:** `400` (inválido), `401`/`403` (Key/permisos), `409` (conflicto de versión / replay de nonce), `413` (payload > 5 MB o > 10 000 cambios), `422` (`esquema_version` no soportada), `429` (rate limit), `503` (fallo R2 → no retransmite).
- **Orden interno garantizado (RF-03):** validar → descifrar → **persistir en R2** → aplicar estado → emitir WSS. Si R2 falla, `503` y no se emite.

#### `GET /documents/{id_documento}/state?since=<cursor>`
- **Response 200:** `{ "id_documento": "...", "version_actual": 42, "cursor": "cur_...42", "cambios_desde_cursor": [ { "id_operacion": "...", "cambios": [...] } ], "estado": "consistente" }`
- **Uso:** re-sincronización del cliente tras hueco de WSS o desconexión (RF-04.e, RF-05.c).
- **Errores:** `401`, `403`, `404` (documento no existe o fuera de scope), `422` (cursor inválido).

#### `POST /documents/{id_documento}/replay` (admin/auditor)
- **Request:** `{ "desde_cursor": "cur_0000000000", "hasta_cursor": "cur_0000000042" }`
- **Response 202:** `{ "replay_id": "...", "documentos": 0, "en_progreso": true }` (proceso asíncrono, idempotente por rango).
- **Errores:** `401`, `403` (no admin/auditor), `422` (rango inválido).

#### `GET /documents` / `GET /documents/{id_documento}`
- Lista de documentos visibles para el usuario autenticado, o detalle del documento. `401`/`403`/`404`.

#### `GET /audit/events` (auditor/admin)
- **Request:** `?desde=<ts>&documento=<id>&actor=<id>&limit=`
- **Response 200:** lista de eventos de auditoría (§RNF-06), paginada.

### 10.3 Salud y estado

#### `GET /health/live`
- **200** si el proceso está vivo. No requiere autenticación.

#### `GET /health/ready`
- **200** si las dependencias (R2, gestor de secretos, Redis) están disponibles; `503` si no. Para balanceadores/Edge.

#### `GET /agents` (admin)
- **200:** lista de agentes con estado, `last_seen`, versión, huella del binario.

### 10.4 WebSocket Seguro (WSS) — contrato de mensajes

- **Endpoint:** `wss://<api-host>/ws/v1/stream?cursor=<cursor_opcional>` (handshake autenticado con JWT en query o en cabecera `Sec-WebSocket-Protocol`; conexión TLS).
- **Conexión:** ping del servidor cada **30 s**; cierre por inactividad tras **10 min**; reconexión del cliente con backoff exponencial.

**Mensaje de datos — evento `data.updated`:**
```jsonc
{
  "event": "data.updated",                 // nombre del evento
  "id_operacion": "018f...",               // correlación extremo a extremo
  "documento": {
    "id_documento": "DOC-9f3a",
    "tenant_id": "TEN-001",
    "version": 42,                          // versión monótona
    "cursor": "cur_0000000042",             // cursor de sincronización
    "ts_actualizacion": "2026-10-03T09:15:33Z"
  },
  "cambios": [                              // solo cambios (parche), nunca fichero completo
    { "celda": "D128", "columna": "D", "id_fila": 128, "valor_nuevo": "1299", "tipo": "numero", "hash": "sha256:..." }
  ],
  "resumen": { "graficos": { "serie_ventas": 1299 }, "contadores": { "celdas_modificadas": 1 } }
}
```

**Mensaje de control — evento `ack`:** el cliente confirma recepción.
```jsonc
{ "event": "ack", "id_operacion": "018f...", "version": 42 }
```

**Mensaje de error — evento `error`:** huecos/validación en el stream.
```jsonc
{ "event": "error", "code": "CURSOR_GAP", "cursor_esperado": "cur_0000000042", "cursor_recibido": "cur_0000000040", "accion": "resync" }
```

- **Autorizaci param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n por conexi param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n:** al abrir el WSS el backend filtra por rol y scope  param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) nicamente los documentos que el cliente puede recibir. Un cliente no autorizado nunca recibe el mensaje (RF-04.c).
- **Detección de huecos:** el frontend compara el `cursor/version` recibido con su último aplicado; si detecta salto, emite `error` y llama a `GET /state?since=` (RF-05.c).

### 10.5 Códigos de estado HTTP comunes
`200 OK` · `201 Created` · `202 Accepted` (procesamiento asíncrono) · `204 No Content` · `400 Bad Request` · `401 Unauthorized` (falta/ inválida Key o JWT) · `403 Forbidden` (rol/permiso insuficiente, agente revocado) · `404 Not Found` · `409 Conflict` (conflicto de versión, replay, operación idempotente en curso) · `413 Payload Too Large` · `422 Unprocessable Entity` (esquema/validación) · `429 Too Many Requests` (rate limit) · `500 Internal Server Error` · `503 Service Unavailable` (dependencia caída, p. ej. R2 — no se retransmite).

---

## 11. Criterios de aceptación (Given / When / Then)

Cada criterio es verificable por test automatizado (unitario, integración o E2E).

### RF-01 — Monitoreo y Cifrado Local
- **CA-01.1 (detección):** *Given* un fichero Excel en una carpeta monitoreada, *When* el usuario lo guarda con un cambio real, *Then* el agente detecta el guardado y genera un parche en ≤ 300 ms.
- **CA-01.2 (ignora temporales):** *Given* ficheros `~$libro.xlsx`, `.tmp`, `.~lock.xlsx`, *When* cambian en disco, *Then* el agente **no** genera ningún parche ni request.
- **CA-01.3 (solo diferencias):** *Given* un libro de 10 000 celdas con 1 celda modificada, *When* se guarda, *Then* el parche contiene exactamente 1 cambio y **no** el libro completo.
- **CA-01.4 (AES-256):** *Given* un parche calculado, *When* el agente lo transmite, *Then* el payload va cifrado con AES-256-GCM (Nonce único, AAD vinculante) y el backend solo lo acepta si el tag AEAD valida.
- **CA-01.5 (idempotencia del diff):** *Given* un parche ya aplicado cuyo hash de fichero no cambió, *When* el agente re-evalúa, *Then* no transmite nada.
- **CA-01.6 (límite de tamaño):** *Given* un parche que supera 5 MB o 10 000 cambios, *When* se genera, *Then* el agente registra la incidencia, notifica y pospone sin truncar silenciosamente.

### RF-02 — Transmisión Segura
- **CA-02.1 (API Key válida):** *Given* un agente con API Key activa, *When* envía un parche, *Then* el backend lo acepta (`2xx`).
- **CA-02.2 (API Key inválida/revocada):** *Given* una API Key inválida o revocada, *When* se envía un parche, *Then* el backend responde `401`/`403` y registra el evento de seguridad; el agente se auto-deshabilita.
- **CA-02.3 (HTTPS/TLS):** *Given* la comunicación agente→API, *When* se inspecciona el transporte, *Then* se usa TLS 1.3 y un `http://` es redirigido/rechazado.
- **CA-02.4 (anti-replay):** *Given* un request válido ya recibido con el mismo `nonce`/`timestamp`, *When* se reenvía dentro de la ventana, *Then* el backend responde `409` y no aplica el cambio dos veces.
- **CA-02.5 (manipulación detectada):** *Given* un payload con un bit alterado, *When* llega al backend, *Then* el descifrado GCM falla, se devuelve error y se registra sin revelar el dato.

### RF-03 — Almacenamiento Inmutable
- **CA-03.1 (respaldo antes de emitir):** *Given* un parche válido, *When* el backend lo procesa, *Then* existe un objeto en R2 **antes** de que se emita el primer mensaje WSS.
- **CA-03.2 (inmutabilidad):** *Given* un respaldo persistido, *When* se intenta sobrescribir o borrar el objeto, *Then* la operación es rechazada (Object Lock / sin permiso de borrado).
- **CA-03.3 (metadatos):** *Given* un respaldo, *When* se inspecciona, *Then* contiene `tenant_id`, `id_documento`, `id_operacion`, `version`, `esquema_version` y checksum.
- **CA-03.4 (fallo de R2):** *Given* que R2 no está disponible, *When* llega un parche válido, *Then* el backend responde `503`, **no** emite por WSS y no marca el estado como aplicado.
- **CA-03.5 (retención/replay):** *Given* respaldos históricos, *When* se solicita replay, *Then* se reconstruye el estado en el instante indicado.

### RF-04 — Distribución en Tiempo Real
- **CA-04.1 (WSS a autenticados):** *Given* dos clientes autenticados con acceso al documento, *When* FastAPI termina de guardar el respaldo, *Then* ambos reciben `data.updated` por WSS.
- **CA-04.2 (no se filtra a no-autorizados):** *Given* un cliente autenticado sin rol para el documento, *When* ocurre un cambio, *Then* no recibe el mensaje.
- **CA-04.3 (WSS seguro):** *Given* el stream, *When* se inspecciona, *Then* la conexión es `wss://` (TLS) y autenticada.
- **CA-04.4 (orden/versionado):** *Given* cambios sucesivos, *When* llegan al cliente, *Then* llevan `version`/`cursor` monótonos y el cliente detecta cualquier hueco.
- **CA-04.5 (recuperación de huecos):** *Given* un cliente que se desconectó, *When* vuelve con su último cursor, *Then* recupera el estado perdido vía `GET /state?since=`.

### RF-05 — Interfaz Reactiva
- **CA-05.1 (sin recarga):** *Given* un dashboard abierto, *When* llega un `data.updated`, *Then* gráficos y contadores se actualizan **sin** que el usuario recargue la página.
- **CA-05.2 (reactividad):** *Given* un mensaje con cambios, *When* React lo recibe, *Then* el store y los componentes afectados se actualizan de forma reactiva.
- **CA-05.3 (resync por hueco):** *Given* un salto de cursor, *When* el frontend lo detecta, *Then** dispara re-sincronización completa** desde el cursor y la vista queda consistente.
- **CA-05.4 (degradación visible):** *Given* una caída de WSS, *When* ocurre, *Then* se muestra un indicador degradado y el cliente reconecta con backoff exponencial.
- **CA-05.5 (testabilidad):** *Given* la capa WebSocket encapsulada, *When* se ejecuta un test unitario, *Then* se puede simular la recepción de mensajes sin backend real.

---

## 12. Métricas y límites (valores concretos)

| Métrica | Límite / Objetivo | Notas |
|---------|--------------------|-------|
| Latencia guardado→gráfico (p95) | **< 2 s** | Objetivo clave RNF-04 |
| Latencia guardado→gráfico (p99) | **< 4 s** | Tolerancia a picos |
| Detección + diff + cifrado (agente) | ≤ 300 ms | Por parche |
| Upload + validar + R2 (backend) | ≤ 700 ms | Sin contar fan-out |
| Fan-out WSS + render | ≤ 1000 ms | |
| Cold start del agente | ≤ 3 s | |
| Tamaño máx. fichero Excel | 100 MB | RNF-10 |
| Tamaño máx. parche (request) | 5 MB | `413` si se supera |
| Máx. cambios por parche | 10 000 | `413` si se supera |
| Máx. filas operativas | 200 000 | Subconjunto con SLO (ver OD-07) |
| Rotación API Key agente | 90 días (solape 24 h) | RNF-03 |
| Rotación DEK (tenant) | 180 días | RNF-03 |
| Rotación token servicio R2 | 90 días | RNF-03 |
| Rate limit agente (upload) | 60 req/min, burst 10; 2 req/s | RNF-12 |
| Rate limit login | 10/min, burst 3; lockout tras 5 fallos | RNF-12 |
| Heartbeat agente | 30 s (offline a los 90 s) | |
| Conexiones WSS por tenant | máx. 500 | |
| Ping WSS / cierre inactividad | 30 s / 10 min | |
| Ventana anti-replay (timestamp) | ± 5 min | |
| Vida de credencial de aprovisionamiento | 15 min, un solo uso | §9.4 |
| Retención de respaldos | 365 días (versionado + Object Lock) | RNF-08 |
| Retención de auditoría | 7 años (inmutable) | RNF-06 |
| RPO | ≤ 5 min | RNF-08 |
| RTO | ≤ 1 h (sync) / ≤ 4 h (desastre regional) | RNF-08 |
| Disponibilidad objetivo | 99,9 % mensual | RNF-05 |
| Navegadores | últimas 2 versiones Chrome/Edge/Firefox | RNF-09 |
| Excel | 2016+ (`.xlsx`, `.xlsm`) | RNF-09 |

---

## 13. Riesgos técnicos y decisiones abiertas

### 13.1 Riesgos técnicos

| # | Riesgo | Impacto | Mitigación / Plan |
|---|--------|---------|-------------------|
| RK-1 | **Detección de guardado poco fiable en Excel** (eventos de filesystem, locks, OneDrive/co-autoría) | Falsos positivos/negativos → parches incorrectos | Polling de hash con debounce como respaldo; whitelist de extensiones; pruebas con Excel real; documentar comportamiento con co-autoría |
| RK-2 | **Cálculo de diff costoso** en libros grandes | Exceder el objetivo de 2 s | Índice por hash de fila, comparación incremental, limitar a 200 k filas, medir pronto |
| RK-3 | **Falsos positivos por formato/estilo** (solo cambió el formato) | Ruido en el parche | Comparar solo **valores**, no estilos; normalizar (fechas, números) |
| RK-4 | **Pérdida/duplicado por concorrencia** (múltiples agentes, reintentos) | Estado inconsistente | Idempotencia por `id_operacion`, versión monótona, transacciones, cursor único |
| RK-5 | **Conflicto de edición concurrente** (dos analistas) | Divergencia semántica | Detectar y registrar (`409`); merge real diferido (fuera de alcance) |
| RK-6 | **Coste y l param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) mites de R2** (muchos objetos peque param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) os por operaci param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n) | Coste y rendimiento | Agrupar (batch) operaciones, lifecycle para retenciones, monitorear costes |
| RK-7 | **Fan-out WSS a muchos clientes** | Carga de CPU/memoria del backend | Publicación por documento, backpressure, escalado horizontal, pruebas de carga |
| RK-8 | **Exfiltración vía el agente** (binario comprometido) | Fuga de datos | Clave por tenant, scope por documento, auditoría, allowlist de egress, hash de binario |
| RK-9 | **Compatibilidad PyInstaller/AV** | Falsos positivos de antivirus que bloquean el agente | Firmar el binario, optimización de build, documentar excepciones |
| RK-10 | **Requisito de inmutabilidad en R2 vs coste de Object Lock** | Coste/funcionalidad | Validar soporte de Object Lock en R2 y pol param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) tica de retenci param($m) [char][Convert]::ToInt32($m.Groups[1].Value, 16) n (OD-09) |

### 13.2 Decisiones abiertas (requieren validación del usuario)

| ID | Decisión abierta | Opciones | Recomendación por defecto |
|----|-------------------|----------|---------------------------|
| OD-01 | **Alcance del cifrado extremo a extremo (E2EE)** | (A) El backend descifra para retransmitir a dashboards · (B) E2EE puro donde el backend solo retransmita ciphertext y solo el navegador con clave descifra | **(A)** por defecto (coherente con RF-03/RF-04); (B) es más puro pero exige distribuir clave a clientes y limita la retransmisión |
| OD-02 | **Modo de cifrado simétrico** | (A) **AES-256-GCM** (AEAD) · (B) AES-256-CBC + HMAC (encrypt-then-MAC) | **(A) AES-256-GCM**; (B) solo si la certificación exige restringir GCM |
| OD-03 | **Firma del payload por el agente** | (A) Firma digital completa por operación · (B) Solo HMAC con clave del agente · (C) Ninguna (integridad vía GCM) | **(B) HMAC** como refuerzo sobre GCM (defensa en profundidad) sin coste de PKI por parche |
| OD-04 | **Minimización de datos en el parche** | (A) Incluir `valor_anterior` (auditoría completa) · (B) Solo `valor_nuevo` + hash del anterior · (C) Configurable por columna | **(C)** configurable por columna, por defecto `valor_anterior` solo para columnas sensibles |
| OD-05 | **mTLS agente↔API** | (A) Activar mTLS con certificado por agente · (B) Solo TLS de servidor (API Key) | **(B)** por defecto; (A) recommended si hay PKI disponible |
| OD-06 | **Proveedor de identidad del dashboard** | (A) OIDCJa casco corporativo (Keycloak/Azure AD) · (B) IdP gubernamental específico | **(A)** genérico Keycloak/OIDC; el issuer concreto es una decisión de despliegue |
| OD-07 | **Volumen operativo esperado** | (A) Pocos documentos (< 50) y < 50 k filas · (B) Muchos documentos y hasta 200 k filas | **(B)**, fijando el SLO operativo en **200 000 filas/documento** |
| OD-08 | **Sistemas operativos del agente** | (A) Solo Windows · (B) Windows + macOS | **(A) Solo Windows** (Excel 2016+ Windows) en esta iteración |
| OD-09 | **Política de R2: Object Lock / replicación** | (A) Object Lock COMPLIANCE 365 d · (B) GOVERNANCE 365 d + cross-region | **(A)** para inmutabilidad fuerte; avaliar cross-region según presupuesto |
| OD-10 | **Granularidad de roles** | (A) 4 roles (viewer/editor/auditor/admin) · (B) RBAB más fino por documento | **(A)** por defecto; (B) si hay sensibilidad por documento |
| OD-11 | **Frecuencia/uso del replay** | (A) Replay a demanda (admin) · (B) Replay programado continuo | **(A) a demanda** |
| OD-12 | **Autenticación del servicio de gestión de secretos** | (A) Cloudflare Secrets · (B) HashiCorp Vault · (C) KMS/HSM del Estado | **(C) KMS/HSM** si existe; (A) como opción ligera |

---

## 14. Trazabilidad (matriz RF ↔ RNF ↔ amenaza ↔ criterio de aceptación)

| RF | RNF asociados | Amenazas mitigadas | Criterios de aceptación |
|----|---------------|--------------------|------------------------|
| RF-01 | RNF-02 (AES-256), RNF-04 (perf), RNF-09 (Excel), RNF-10 (tamaño), RNF-11 (firma .exe) | T-09 (macros), T-10 (path traversal), T-13 (anti-tamper) | CA-01.1 … CA-01.6 |
| RF-02 | RNF-01 (TLS), RNF-02 (app-crypto), RNF-03 (rotación Key), RNF-12 (rate limit), RNF-13 (secretos) | T-02 (manipulación), T-03 (suplantación), T-08 (MITM), T-14 | CA-02.1 … CA-02.5 |
| RF-03 | RNF-02 (reposo), RNF-07 (trazabilidad), RNF-08 (DR/RPO), RNF-14 (idempotencia) | T-04 (acceso), T-05 (R2 no autenticado), T-11 (exfiltración) | CA-03.1 … CA-03.5 |
| RF-04 | RNF-01 (WSS), RNF-05 (disponibilidad), RNF-07 (cursor), RNF-12 (WSS rate) | T-04 (no autorizado), T-06 (escalada) | CA-04.1 … CA-04.5 |
| RF-05 | RNF-04 (latencia 2 s), RNF-05 (reconexión), RNF-09 (navegadores) | — (superficie de UI; apoya T-09 vía sanitización) | CA-05.1 … CA-05.5 |

---

## Anexo A — Glosario

| Término | Significado |
|---------|-------------|
| **EARS** | Easy Approach to Requirements Syntax — sintaxis normalizada de requisitos. |
| **Parche (patch)** | Conjunto de diferencias (cambios de celda) respecto al estado anterior, no el fichero completo. |
| **Cursor de sincronización** | Identificador monotónico que posiciona exactamente qué operación se ha aplicado. |
| **Idempotencia** | Reaplicar la misma `id_operacion` no produce efecto adicional. |
| **Envelope encryption** | Cifrar datos con una clave de datos (DEK) y cifrar esa DEK con una clave maestra (KEK). |
| **AEAD / GCM** | Modo de cifrado autenticado Galois/Counter Mode. |
| **AAD** | Associated Authenticated Data — datos autenticados no cifrados que vinculan el mensaje a un contexto. |
| **DPAPI** | Windows Data Protection API — protección de secretos a nivel usuario/equipo. |
| **Object Lock** | Bloqueo de objeto en almacenamiento S3-compatible para inmutabilidad (WORM). |
| **id_documento** | Identificador estable = hash del path relativo del Excel dentro de un tenant. |
| **RPO / RTO** | Recovery Point Objective / Recovery Time Objective. |
| **WSS** | WebSocket Secure (WebSocket sobre TLS). |
| **mTLS** | Mutual TLS (certificación mutua). |
