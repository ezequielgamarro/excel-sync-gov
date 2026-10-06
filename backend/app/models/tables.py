"""Tablas SQLAlchemy Core (espejo de las migraciones Alembic, F1).

Las migraciones ``0001_base``–``0009_svc_dashboard`` crean el esquema de forma
idempotente (tablas particionadas por mes en los esquemas ``app`` y ``audit``).
Estos objetos ``Table`` son la proyección Core usada por la capa de persistencia
(F3) para tipar las consultas sin depender de ORM. Se mantienen **alineados**
con ``backend/alembic/versions`` y ``backend/docs/schema.md``.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.sqltypes import LargeBinary

APP_SCHEMA = "app"
AUDIT_SCHEMA = "audit"

app_metadata = MetaData(schema=APP_SCHEMA)
audit_metadata = MetaData(schema=AUDIT_SCHEMA)

# --- app.agent_registry -------------------------------------------------------
# Retirado en T27 (pivote a Google Sheets + Apps Script): la identidad del origen
# es ``webhook_registry``. No se proyecta ni se usa desde la aplicación.

# --- app.keyring --------------------------------------------------------------
keyring = Table(
    "keyring",
    app_metadata,
    Column("key_id", Text, primary_key=True),
    Column("fecha", Date, nullable=False),
    Column("estado", Text, nullable=False),
    Column("kek_ref", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("rotated_at", DateTime(timezone=True)),
)

# --- app.webhook_registry -----------------------------------------------------
# Registro de orígenes webhook (Google Sheets): identidad estable, estado,
# revocación individual y metadata de origen (migración 0007, spec §7.9, §9.4).
webhook_registry = Table(
    "webhook_registry",
    app_metadata,
    Column("webhook_id", Uuid, primary_key=True),
    Column("doc_id", Text, nullable=False),
    Column("room_id", Text, nullable=False),
    Column("estado", Text, nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("last_seen_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# --- app.webhook_secret -------------------------------------------------------
# Versiones del secreto de firma del webhook. **Solo metadata** (``key_id``,
# estado y ventana de aceptación); el material vive en el secret manager
# (migración 0007, spec §9.2–§9.3, RNF-02.e).
webhook_secret = Table(
    "webhook_secret",
    app_metadata,
    Column("key_id", Text, primary_key=True),
    Column("webhook_id", Uuid, nullable=False),
    Column("estado", Text, nullable=False),
    Column("not_before", DateTime(timezone=True), nullable=False),
    Column("not_after", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("rotated_at", DateTime(timezone=True)),
)

# --- app.role_capability -----------------------------------------------------
role_capability = Table(
    "role_capability",
    app_metadata,
    Column("role", Text, primary_key=True),
    Column("capability", Text, primary_key=True),
    Column("granted", Boolean, nullable=False, default=True),
)

# --- app.user_account ---------------------------------------------------------
# Usuarios locales (authn nativa, sin IdP): credenciales con hash Argon2id,
# estado activo/deshabilitado, bloqueo por intentos y trazabilidad de login
# (migración 0012, spec §2.2.2, RNF-03.a/i, T34).
user_account = Table(
    "user_account",
    app_metadata,
    Column("user_id", Uuid, primary_key=True),
    Column("sub", Text, nullable=False),
    Column("username", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("estado", Text, nullable=False, default="activo"),
    Column("failed_attempts", Integer, nullable=False, default=0),
    Column("locked_until", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True)),
    Column("last_login_at", DateTime(timezone=True)),
    Column("disabled_at", DateTime(timezone=True)),
)

# --- app.user_role ------------------------------------------------------------
# Mapeo usuario→rol (contenedor de capacidades; §2.2.3). La capacidad efectiva se
# deriva vía ``app.role_capability``.
user_role = Table(
    "user_role",
    app_metadata,
    Column("user_id", Uuid, primary_key=True),
    Column("role", Text, primary_key=True),
    Column("granted_at", DateTime(timezone=True), nullable=False),
)

# --- app.refresh_token --------------------------------------------------------
# Refresh tokens rotativos con detección de reutilización (cadena). Solo se
# almacena el identificador opaco (no el token en claro de sesión) y su estado.
refresh_token = Table(
    "refresh_token",
    app_metadata,
    Column("token_id", Text, primary_key=True),
    Column("chain_id", Text, nullable=False),
    Column("sub", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("issued_at", DateTime(timezone=True), nullable=False),
    Column("rotated_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
)

# --- app.ingest_event ---------------------------------------------------------
# Cabecera inmutable del webhook (migración 0002): la identidad del origen es
# ``webhook_id`` (FK lógica a ``app.webhook_registry``), no un agente.
# ``event_id`` es la clave de idempotencia (UUIDv7) y se materializa como
# ``UNIQUE (event_id, received_at)`` por el particionado mensual.
ingest_event = Table(
    "ingest_event",
    app_metadata,
    Column("event_id", Uuid, nullable=False),
    Column("doc_id", Text, nullable=False),
    Column("webhook_id", Uuid, nullable=False),
    Column("content_sha256", Text, nullable=False),
    Column("payload_ciphertext", LargeBinary, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", Text),
)

# --- app.snapshot_current -----------------------------------------------------
snapshot_current = Table(
    "snapshot_current",
    app_metadata,
    Column("doc_id", Text, primary_key=True),
    Column("event_id", Uuid, nullable=False),
    Column("agent_id", Uuid),
    Column("payload", JSONB, nullable=False),
    Column("data_date", Date, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# --- app.agg_hourly / app.agg_daily -------------------------------------------
agg_hourly = Table(
    "agg_hourly",
    app_metadata,
    Column("bucket", DateTime(timezone=True), primary_key=True),
    Column("kpi_id", Text, primary_key=True),
    Column("unidad_id", Text, primary_key=True, default=""),
    Column("turno_id", Text, primary_key=True, default=""),
    Column("value", BigInteger, nullable=False),
    Column("baseline_value", BigInteger),
)

agg_daily = Table(
    "agg_daily",
    app_metadata,
    Column("bucket", Date, primary_key=True),
    Column("kpi_id", Text, primary_key=True),
    Column("unidad_id", Text, primary_key=True, default=""),
    Column("turno_id", Text, primary_key=True, default=""),
    Column("value", BigInteger, nullable=False),
    Column("baseline_value", BigInteger),
)

# --- app.consulta_event -------------------------------------------------------
# Detalle normalizado de la hoja «CONSULTAS» de la planilla oficial de la
# Jefatura (20 columnas exactas). Es la fuente de verdad granular para las
# agrupaciones del dashboard por ``resultado``, ``causas_penales``,
# ``jefatura_regional`` y ``turno``. Particionado mensual por ``fecha_consulta``
# (retención 60 meses) y con los campos técnicos de trazabilidad del evento de
# origen (``event_id``/``doc_id``/``seq``/``received_at``/``correlation_id``).
CONSULTA_COLUMNS: tuple[str, ...] = (
    "fecha_consulta",
    "hora_consulta",
    "turno",
    "jerarquia",
    "personal_policial",
    "jefatura_regional",
    "dependencias",
    "tipo_consulta",
    "identificacion",
    "tipo_arma_vehiculo",
    "resultado",
    "causas_penales",
    "registro_legajo",
    "autoridad_judicial",
    "sistema_utilizado",
    "tramite_devuelto",
    "hora_resp",
    "personal_que_informa",
    "cargo",
    "operativos_preventivos",
)

#: Columnas de texto libres de la hoja CONSULTAS (todas salvo ``fecha_consulta``).
CONSULTA_TEXT_COLUMNS: tuple[str, ...] = tuple(
    name for name in CONSULTA_COLUMNS if name != "fecha_consulta"
)

#: Campos técnicos añadidos por el backend a cada fila de consulta.
CONSULTA_TECHNICAL_COLUMNS: tuple[str, ...] = (
    "event_id",
    "doc_id",
    "row_index",
    "seq",
    "received_at",
    "correlation_id",
)

consulta_event = Table(
    "consulta_event",
    app_metadata,
    Column("event_id", Uuid, nullable=False),
    Column("doc_id", Text, nullable=False),
    Column("row_index", Integer, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", Text),
    Column("fecha_consulta", Date, nullable=False),
    Column("hora_consulta", Text),
    Column("turno", Text),
    Column("jerarquia", Text),
    Column("personal_policial", Text),
    Column("jefatura_regional", Text),
    Column("dependencias", Text),
    Column("tipo_consulta", Text),
    Column("identificacion", Text),
    Column("tipo_arma_vehiculo", Text),
    Column("resultado", Text),
    Column("causas_penales", Text),
    Column("registro_legajo", Text),
    Column("autoridad_judicial", Text),
    Column("sistema_utilizado", Text),
    Column("tramite_devuelto", Text),
    Column("hora_resp", Text),
    Column("personal_que_informa", Text),
    Column("cargo", Text),
    Column("operativos_preventivos", Text),
)

# --- app.ranking_snapshot -----------------------------------------------------
ranking_snapshot = Table(
    "ranking_snapshot",
    app_metadata,
    Column("data_date", Date, primary_key=True),
    Column("turno_id", Text, primary_key=True),
    Column("puesto", Integer, primary_key=True),
    Column("dependencia_id", Text, nullable=False),
    Column("comisaria", Text, nullable=False),
    Column("intervenciones", BigInteger, nullable=False),
    Column("variacion_abs", BigInteger),
    Column("variacion_pct", Numeric(8, 2)),
    Column("puesto_previo", Integer),
)

# --- audit.audit_event --------------------------------------------------------
audit_event = Table(
    "audit_event",
    audit_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("actor", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("resource", Text, nullable=False),
    Column("result", Text, nullable=False),
    Column("ip", Text),
    Column("user_agent", Text),
    Column("correlation_id", Text),
    Column("schema_version", Text),
)

# Catálogo canónico (spec §7.5): 5 unidades regionales.
REGIONAL_UNITS: tuple[str, ...] = ("capital", "sur", "este", "oeste", "norte")

# Catálogo canónico (spec §7.4): 3 turnos operativos en orden cronológico.
TURNOS: tuple[str, ...] = ("MAÑANA", "TARDE", "NOCHE")

# Catálogo canónico (spec §7.3): 4 KPIs.
KPIS: tuple[str, ...] = (
    "total_consultas_sifcop",
    "personas_capturadas",
    "vehiculos_secuestrados",
    "armas_secuestradas",
)
