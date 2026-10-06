/**
 * CONFIG-001 — Configuración estática del Apps Script (F6, T38–T44).
 *
 * Constantes NO secretas: layout canónico del documento (mapeo 1:1 hojas→series,
 * OD-15, spec §1.6/§7), tiempos de coalescencia/backoff y catálogos cerrados.
 * Ningún secreto vive aquí: el material HMAC reside en `Script Properties`
 * (T42, §9.4). El endpoint allowlisted y las credenciales se leen de propiedades.
 */

var CONFIG = {
  // Coalescencia de ráfagas (RF-01.a/b): ~750 ms.
  COALESCE_MS: 750,

  // Backoff exponencial del webhook (RF-01.i): 2/4/8/16/32/60 s, jitter ±20 %.
  BACKOFF_SECONDS: [2, 4, 8, 16, 32, 60],
  JITTER_RATIO: 0.2,

  // Ventana de solape de rotación del secreto (T42, §9.3): 24 h.
  OVERLAP_HOURS: 24,

  // Versión del contrato/sobre usada como `X-Webhook-Version` y en la cadena
  // canónica (§9.2).
  SCHEMA_VERSION: '1.0.0',

  // Zona horaria canónica del dato (OD-01, §13).
  TZ: 'America/Argentina/Buenos_Aires',

  // Mapeo 1:1 hojas→series (OD-15).
  SHEETS: {
    kpis: 'Resumen',
    regional: 'Regional',
    turnos: 'Turnos',
    ranking: 'Ranking',
    consultas: 'CONSULTAS'
  },

  // Allowlist de CABECERAS por hoja. Un encabezado fuera de esta lista rompe la
  // ejecución cerrada (OOS-06, T39): no se "adivinan" columnas.
  HEADERS: {
    kpis: [
      'kpi_id', 'label', 'value', 'baseline_value', 'delta_abs', 'delta_pct',
      'direction', 'comparison', 'as_of', 'has_reference'
    ],
    regional: [
      'unidad_id', 'label', 'intervenciones', 'variacion_abs', 'variacion_pct',
      'rank'
    ],
    turnos: [
      'turno_id', 'inicio_min', 'fin_min', 'label', 'intervenciones',
      'variacion_abs', 'variacion_pct', 'estado'
    ],
    ranking: [
      'puesto', 'dependencia_id', 'comisaria', 'intervenciones',
      'variacion_abs', 'variacion_pct', 'puesto_previo'
    ],
    consultas: [
      'fecha consulta', 'hora consulta', 'turno', 'jerarquía', 'personal policial',
      'jefatura regional', 'dependencias', 'tipo consulta', 'identificación',
      'tipo de arma/vehículo', 'resultado', 'causas penales', 'registro/legajo',
      'autoridad judicial', 'sistema utilizado', 'trámite devuelto', 'hora resp',
      'personal que informa', 'cargo', 'operativos preventivos'
    ]
  },

  // Cabeceras obligatorias por hoja (el resto son opcionales y se completan con
  // los valores por defecto del catálogo).
  REQUIRED: {
    kpis: ['kpi_id', 'value'],
    regional: ['unidad_id', 'intervenciones'],
    turnos: ['turno_id', 'intervenciones'],
    ranking: ['puesto', 'dependencia_id', 'comisaria', 'intervenciones'],
    consultas: ['fecha consulta']
  },

  // Mapeo de las 20 columnas de la hoja «CONSULTAS» (display → campo canónico).
  CONSULTA_FIELD_MAP: {
    'fecha consulta': 'fecha_consulta',
    'hora consulta': 'hora_consulta',
    'turno': 'turno',
    'jerarquía': 'jerarquia',
    'jerarquia': 'jerarquia',
    'personal policial': 'personal_policial',
    'jefatura regional': 'jefatura_regional',
    'dependencias': 'dependencias',
    'tipo consulta': 'tipo_consulta',
    'identificación': 'identificacion',
    'identificacion': 'identificacion',
    'tipo de arma/vehículo': 'tipo_arma_vehiculo',
    'tipo de arma/vehiculo': 'tipo_arma_vehiculo',
    'resultado': 'resultado',
    'causas penales': 'causas_penales',
    'registro/legajo': 'registro_legajo',
    'autoridad judicial': 'autoridad_judicial',
    'sistema utilizado': 'sistema_utilizado',
    'trámite devuelto': 'tramite_devuelto',
    'tramite devuelto': 'tramite_devuelto',
    'hora resp': 'hora_resp',
    'personal que informa': 'personal_que_informa',
    'cargo': 'cargo',
    'operativos preventivos': 'operativos_preventivos'
  },

  // Catálogo cerrado de 4 KPIs (§7.3, §13).
  KPIS: [
    { id: 'total_consultas_sifcop', label: 'Total Consultas SIFCOP' },
    { id: 'personas_capturadas', label: 'Personas Capturadas' },
    { id: 'vehiculos_secuestrados', label: 'Vehículos Secuestrados' },
    { id: 'armas_secuestradas', label: 'Armas Secuestradas' }
  ],

  // Catálogo cerrado de 5 unidades regionales (§7.5, §13).
  UNITS: [
    { id: 'capital', label: 'Capital' },
    { id: 'sur', label: 'Sur' },
    { id: 'este', label: 'Este' },
    { id: 'oeste', label: 'Oeste' },
    { id: 'norte', label: 'Norte' }
  ],

  // Catálogo cerrado de 3 turnos operativos (§7.4, §13).
  TURNOS: [
    { id: 'MAÑANA', inicio: 360, fin: 840, label: 'MAÑANA (06-14)' },
    { id: 'TARDE', inicio: 840, fin: 1320, label: 'TARDE (14-22)' },
    { id: 'NOCHE', inicio: 1320, fin: 360, label: 'NOCHE (22-06)' }
  ],

  RANKING_MAX_ROWS: 5,

  // Claves de fachada expuestas como funciones públicas (T38/T45).
  HANDLERS: {
    onEdit: 'handleOnEdit',
    onChange: 'handleOnChange',
    retry: 'retryPendingSend'
  },

  // Propiedades de script usadas (nombres; NUNCA se registran valores sensibles).
  PROPS: {
    webhookId: 'WEBHOOK_ID',
    docId: 'WEBHOOK_DOC_ID',
    keyId: 'WEBHOOK_KEY_ID',
    secret: 'WEBHOOK_SECRET',
    keyIdPrevious: 'WEBHOOK_KEY_ID_PREVIOUS',
    secretPrevious: 'WEBHOOK_SECRET_PREVIOUS',
    overlapUntil: 'WEBHOOK_OVERLAP_UNTIL',
    endpoint: 'WEBHOOK_ENDPOINT',
    allowedHosts: 'ALLOWED_ENDPOINT_HOSTS',
    version: 'WEBHOOK_VERSION',
    lastHash: 'LAST_SUCCESS_HASH',
    lastSentAt: 'LAST_SUCCESS_AT',
    lastEventId: 'LAST_SENT_EVENT_ID',
    retriesExhausted: 'RETRIES_EXHAUSTED',
    pending: 'PENDING_SEND',
    blocked: 'WEBHOOK_BLOCKED',
    lastError: 'LAST_ERROR',
    lastReceived: 'LAST_LOCAL_RECEIVED_AT'
  }
};
