/**
 * READER-001 — Lectura y normalización de la hoja (F6, T39, §7.3–§7.6).
 *
 * Lee con `SpreadsheetApp` en **solo lectura** (nunca escribe: el sistema es
 * unidireccional, §2.2.4/OOS-03), normaliza el documento al payload canónico y
 * valida las **cabeceras contra la allowlist** (mapeo 1:1 hojas→series, OD-15).
 * Ante cualquier desviación **falla cerrado** con un aviso accionable (OOS-06):
 * no se "adivinan" columnas ni se envían datos parciales.
 *
 * Devuelve el payload normalizado y la **rejilla cruda** (valores de pantalla)
 * de las hojas vigiladas; el hash de contenido (T40) se calcula sobre la rejilla
 * para que sea idéntico e interoperable con la reconciliación del backend (T45).
 */

/** Todas las hojas vigiladas, leídas una sola vez. */
function readNormalizedContent_() {
  var keys = ['kpis', 'regional', 'turnos', 'ranking'];
  var matrices = {};
  var grid = {};
  for (var i = 0; i < keys.length; i++) {
    var matrix = readSheetMatrix_(CONFIG.SHEETS[keys[i]]);
    matrices[keys[i]] = matrix;
    grid[CONFIG.SHEETS[keys[i]]] = matrix.values;
  }
  // Hoja «CONSULTAS» (20 columnas oficiales): opcional (compatibilidad), pero
  // si existe se normaliza y entra en el hash de contenido.
  var consultas = [];
  if (sheetExists_(CONFIG.SHEETS.consultas)) {
    var consultaMatrix = readSheetMatrix_(CONFIG.SHEETS.consultas);
    grid[CONFIG.SHEETS.consultas] = consultaMatrix.values;
    consultas = normalizeConsultas_(consultaMatrix);
  }
  return {
    payload: {
      kpis: normalizeKpis_(matrices.kpis),
      regional: normalizeRegional_(matrices.regional),
      turnos: normalizeTurnos_(matrices.turnos),
      ranking: normalizeRanking_(matrices.ranking),
      consultas: consultas
    },
    grid: grid
  };
}

/** ¿Existe la hoja en el documento activo? */
function sheetExists_(sheetName) {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName) !== null;
}

/**
 * Normaliza la hoja «CONSULTAS» (20 columnas exactas) a campos canónicos.
 * Valida cabeceras contra la allowlist y falla cerrado ante desviaciones.
 */
function normalizeConsultas_(matrix) {
  var map = CONFIG.CONSULTA_FIELD_MAP;
  var allowed = CONFIG.HEADERS.consultas;
  var index = {};
  var unknown = [];
  for (var i = 0; i < matrix.headers.length; i++) {
    var name = String(matrix.headers[i]).trim().toLowerCase();
    if (name === '') continue;
    if (allowed.indexOf(name) < 0) {
      unknown.push(String(matrix.headers[i]).trim());
      continue;
    }
    if (index[name] !== undefined) {
      throw new Error('Layout inválido en "' + CONFIG.SHEETS.consultas +
        '": cabecera duplicada "' + name + '".');
    }
    index[name] = i;
  }
  if (unknown.length > 0) {
    throw new Error('Layout inválido en "' + CONFIG.SHEETS.consultas +
      '": cabeceras fuera de allowlist [' + unknown.join(', ') +
      ']. Corrija la hoja o actualice la allowlist.');
  }
  if (index['fecha consulta'] === undefined) {
    throw new Error('Layout inválido en "' + CONFIG.SHEETS.consultas +
      '": falta la cabecera obligatoria "Fecha Consulta".');
  }
  var rows = [];
  var displayHeaders = Object.keys(map);
  for (var r = 0; r < matrix.records.length; r++) {
    var record = matrix.records[r];
    var rawDate = String(cell_(record, index, 'fecha consulta')).trim();
    if (!rawDate) continue;
    var row = { fecha_consulta: normalizeSheetDate_(rawDate) };
    for (var h = 0; h < displayHeaders.length; h++) {
      var header = displayHeaders[h];
      var canonical = map[header];
      if (canonical === 'fecha_consulta') continue;
      row[canonical] = String(cell_(record, index, header)).trim();
    }
    rows.push(row);
  }
  return rows;
}

/** Normaliza ``DD/MM/YYYY`` o ``DD-MM-YYYY`` a ISO ``YYYY-MM-DD``. */
function normalizeSheetDate_(value) {
  var text = String(value).trim();
  var match = text.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
  if (match) {
    return match[3] + '-' + ('0' + match[2]).slice(-2) + '-' + ('0' + match[1]).slice(-2);
  }
  return text;
}

/** Lee una hoja como matriz de valores de pantalla, validando existencia. */
function readSheetMatrix_(sheetName) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    throw new Error('Layout inválido: falta la hoja "' + sheetName + '" (mapeo 1:1 hojas→series).');
  }
  var values = sheet.getDataRange().getDisplayValues();
  if (!values || values.length < 2) {
    throw new Error('Layout inválido: la hoja "' + sheetName + '" no tiene filas de datos.');
  }
  var trimmed = [];
  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var hasValue = row.some(function (cell) { return String(cell).trim() !== ''; });
    if (i === 0 || hasValue) trimmed.push(row);
  }
  return { headers: trimmed[0], records: trimmed.slice(1), values: trimmed };
}

/**
 * Valida las cabeceras contra la allowlist (T39, OOS-06) y devuelve el mapa
 * `cabecera → índice`. Falla cerrado si hay cabeceras desconocidas, duplicadas
 * o falta alguna obligatoria.
 */
function mapHeaders_(sheetKey, headers) {
  var allowed = CONFIG.HEADERS[sheetKey];
  var required = CONFIG.REQUIRED[sheetKey];
  var index = {};
  var unknown = [];
  for (var i = 0; i < headers.length; i++) {
    var name = String(headers[i]).trim().toLowerCase();
    if (name === '') continue;
    if (allowed.indexOf(name) < 0) {
      unknown.push(String(headers[i]).trim());
      continue;
    }
    if (index[name] !== undefined) {
      throw new Error('Layout inválido en "' + CONFIG.SHEETS[sheetKey] +
        '": cabecera duplicada "' + name + '".');
    }
    index[name] = i;
  }
  if (unknown.length > 0) {
    throw new Error('Layout inválido en "' + CONFIG.SHEETS[sheetKey] +
      '": cabeceras fuera de allowlist [' + unknown.join(', ') +
      ']. Corrija la hoja o actualice la allowlist; no se adivinan columnas.');
  }
  var missing = required.filter(function (name) { return index[name] === undefined; });
  if (missing.length > 0) {
    throw new Error('Layout inválido en "' + CONFIG.SHEETS[sheetKey] +
      '": faltan cabeceras obligatorias [' + missing.join(', ') + '].');
  }
  return index;
}

/** Valor de una celda por nombre de cabecera (o cadena vacía). */
function cell_(record, index, name) {
  var position = index[name];
  if (position === undefined || position >= record.length) return '';
  return record[position];
}

/** Normaliza los 4 KPIs (§7.3). */
function normalizeKpis_(matrix) {
  var index = mapHeaders_('kpis', matrix.headers);
  var byId = {};
  var now = isoUtc_(new Date());
  for (var i = 0; i < matrix.records.length; i++) {
    var record = matrix.records[i];
    var kpiId = String(cell_(record, index, 'kpi_id')).trim();
    if (byId[kpiId]) {
      throw new Error('Layout inválido en "' + CONFIG.SHEETS.kpis + '": KPI duplicado "' + kpiId + '".');
    }
    byId[kpiId] = record;
  }
  var kpis = {};
  for (var k = 0; k < CONFIG.KPIS.length; k++) {
    var spec = CONFIG.KPIS[k];
    var data = byId[spec.id];
    if (!data) {
      throw new Error('Layout inválido: falta el KPI "' + spec.id +
        '" en la hoja "' + CONFIG.SHEETS.kpis + '" (se esperan los 4).');
    }
    var value = toInt_(cell_(data, index, 'value'), NaN);
    if (isNaN(value)) {
      throw new Error('Valor inválido del KPI "' + spec.id + '": "value" debe ser entero no negativo.');
    }
    var hasBaseline = String(cell_(data, index, 'baseline_value')).trim() !== '';
    var baseline = toInt_(cell_(data, index, 'baseline_value'), value);
    var explicitRef = toBool_(cell_(data, index, 'has_reference'), hasBaseline);
    var hasReference = explicitRef && hasBaseline;
    var deltaAbs = hasReference ? value - baseline : null;
    var deltaPct = null;
    if (hasReference) {
      deltaPct = baseline === 0 ? null : round2_((deltaAbs / baseline) * 100);
    }
    var direction = String(cell_(data, index, 'direction')).trim().toLowerCase();
    if (['up', 'down', 'flat'].indexOf(direction) < 0) {
      direction = directionOf_(deltaAbs === null ? 0 : deltaAbs);
    }
    var asOf = String(cell_(data, index, 'as_of')).trim() || now;
    kpis[spec.id] = {
      label: String(cell_(data, index, 'label')).trim() || spec.label,
      value: value,
      delta_abs: deltaAbs,
      delta_pct: deltaPct,
      direction: direction,
      comparison: 'ayer_mismo_tramo',
      baseline_value: baseline,
      as_of: asOf,
      has_reference: hasReference
    };
  }
  return kpis;
}

/** Normaliza las 5 unidades regionales en orden canónico (§7.5). */
function normalizeRegional_(matrix) {
  var index = mapHeaders_('regional', matrix.headers);
  var byUnit = {};
  for (var i = 0; i < matrix.records.length; i++) {
    var record = matrix.records[i];
    var unidad = String(cell_(record, index, 'unidad_id')).trim().toLowerCase();
    if (!unitSpec_(unidad)) {
      throw new Error('Unidad regional fuera de allowlist: "' + unidad +
        '" (se esperan: capital, sur, este, oeste, norte).');
    }
    if (byUnit[unidad]) {
      throw new Error('Unidad regional duplicada: "' + unidad + '".');
    }
    byUnit[unidad] = record;
  }
  var normalized = [];
  for (var u = 0; u < CONFIG.UNITS.length; u++) {
    var spec = CONFIG.UNITS[u];
    var data = byUnit[spec.id];
    normalized.push({
      unidad_id: spec.id,
      label: (data && String(cell_(data, index, 'label')).trim()) || spec.label,
      intervenciones: data ? toInt_(cell_(data, index, 'intervenciones'), 0) : 0,
      variacion_abs: data ? toInt_(cell_(data, index, 'variacion_abs'), 0) : 0,
      variacion_pct: data ? round2_(toNumber_(cell_(data, index, 'variacion_pct'), 0)) : 0,
      rank: 1
    });
  }
  return assignRanks_(normalized);
}

/** Normaliza los 3 turnos en orden cronológico (§7.4). */
function normalizeTurnos_(matrix) {
  var index = mapHeaders_('turnos', matrix.headers);
  var byTurno = {};
  for (var i = 0; i < matrix.records.length; i++) {
    var record = matrix.records[i];
    var turno = String(cell_(record, index, 'turno_id')).trim().toUpperCase();
    if (!turnoSpec_(turno)) {
      throw new Error('Turno fuera de allowlist: "' + turno + '" (se esperan: MAÑANA, TARDE, NOCHE).');
    }
    if (byTurno[turno]) {
      throw new Error('Turno duplicado: "' + turno + '".');
    }
    byTurno[turno] = record;
  }
  var normalized = [];
  for (var t = 0; t < CONFIG.TURNOS.length; t++) {
    var spec = CONFIG.TURNOS[t];
    var data = byTurno[spec.id];
    var estado = data ? String(cell_(data, index, 'estado')).trim().toLowerCase() : '';
    if (['pendiente', 'en_curso', 'cerrada'].indexOf(estado) < 0) {
      estado = deriveEstado_(spec);
    }
    normalized.push({
      turno_id: spec.id,
      inicio_min: data ? toInt_(cell_(data, index, 'inicio_min'), spec.inicio) : spec.inicio,
      fin_min: data ? toInt_(cell_(data, index, 'fin_min'), spec.fin) : spec.fin,
      label: (data && String(cell_(data, index, 'label')).trim()) || spec.label,
      intervenciones: data ? toInt_(cell_(data, index, 'intervenciones'), 0) : 0,
      variacion_abs: data ? toInt_(cell_(data, index, 'variacion_abs'), 0) : 0,
      variacion_pct: data ? round2_(toNumber_(cell_(data, index, 'variacion_pct'), 0)) : 0,
      estado: estado
    });
  }
  return normalized;
}

/** Normaliza el ranking Top 5 (§7.6). */
function normalizeRanking_(matrix) {
  var index = mapHeaders_('ranking', matrix.headers);
  if (matrix.records.length > CONFIG.RANKING_MAX_ROWS) {
    throw new Error('Layout inválido: el ranking tiene ' + matrix.records.length +
      ' filas; el máximo es ' + CONFIG.RANKING_MAX_ROWS + '.');
  }
  var deps = [];
  for (var i = 0; i < matrix.records.length; i++) {
    var record = matrix.records[i];
    var dependenciaId = String(cell_(record, index, 'dependencia_id')).trim();
    var comisaria = String(cell_(record, index, 'comisaria')).trim();
    if (!dependenciaId || !comisaria) {
      throw new Error('Ranking inválido: cada fila requiere "dependencia_id" y "comisaria".');
    }
    deps.push({
      dependencia_id: dependenciaId,
      comisaria: comisaria,
      intervenciones: toInt_(cell_(record, index, 'intervenciones'), 0),
      variacion_abs: toInt_(cell_(record, index, 'variacion_abs'), 0),
      variacion_pct: round2_(toNumber_(cell_(record, index, 'variacion_pct'), 0)),
      puesto_previo: toInt_(cell_(record, index, 'puesto_previo'), 0)
    });
  }
  deps.sort(function (a, b) {
    if (b.intervenciones !== a.intervenciones) return b.intervenciones - a.intervenciones;
    return a.comisaria < b.comisaria ? -1 : (a.comisaria > b.comisaria ? 1 : 0);
  });
  for (var p = 0; p < deps.length; p++) {
    deps[p].puesto = p + 1;
    if (!deps[p].puesto_previo || deps[p].puesto_previo < 1 ||
        deps[p].puesto_previo > CONFIG.RANKING_MAX_ROWS) {
      deps[p].puesto_previo = p + 1;
    }
  }
  return { top_n: Math.max(1, Math.min(CONFIG.RANKING_MAX_ROWS, deps.length)), dependencias: deps };
}

/** Asigna `rank` por intervenciones descendente con desempate alfabético. */
function assignRanks_(items) {
  var sorted = items.slice().sort(function (a, b) {
    if (b.intervenciones !== a.intervenciones) return b.intervenciones - a.intervenciones;
    return a.label < b.label ? -1 : (a.label > b.label ? 1 : 0);
  });
  for (var i = 0; i < sorted.length; i++) sorted[i].rank = i + 1;
  return items;
}

/** Especificación canónica de una unidad regional (o `null`). */
function unitSpec_(id) {
  for (var i = 0; i < CONFIG.UNITS.length; i++) {
    if (CONFIG.UNITS[i].id === id) return CONFIG.UNITS[i];
  }
  return null;
}

/** Especificación canónica de un turno (o `null`). */
function turnoSpec_(id) {
  for (var i = 0; i < CONFIG.TURNOS.length; i++) {
    if (CONFIG.TURNOS[i].id === id) return CONFIG.TURNOS[i];
  }
  return null;
}

/** Estado del turno según la hora actual en la zona canónica (§7.4, RF-04.b). */
function deriveEstado_(spec) {
  var now = minuteOfDay_(new Date());
  if (spec.fin > spec.inicio) {
    if (now >= spec.inicio && now < spec.fin) return 'en_curso';
    return now < spec.inicio ? 'pendiente' : 'cerrada';
  }
  if (now >= spec.inicio || now < spec.fin) return 'en_curso';
  return 'pendiente';
}
