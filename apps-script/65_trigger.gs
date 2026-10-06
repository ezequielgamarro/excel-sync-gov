/**
 * TRIGGER-001 — Trigger instalable y coalescencia (F6, T38; RF-01.a/b).
 *
 * `handleOnEdit`/`handleOnChange` son los manejadores **instalables** (no los
 * simples `onEdit(e)` del contenedor, que no permiten llamadas externas). Cada
 * ejecución:
 *
 *  1. descarta ediciones de hojas no vigiladas (no-ops);
 *  2. publica una solicitud y adquiere un **lock de script**;
 *  3. coalesce la ráfaga esperando ~750 ms y drena solicitudes que lleguen
 *     durante el procesamiento (un solo envío por ráfaga sobre el estado más
 *     reciente);
 *  4. delega en `sendCurrentState_` (hash + firma + envío) y registra el log de
 *     ejecución.
 *
 * `installTriggers()` crea los triggers `onEdit`, `onChange` y el temporal de
 * reintento/reconciliación (cada minuto).
 */

/** Manejador instalable `onEdit`. */
function handleOnEdit(e) {
  if (e && e.range) {
    var sheetName = e.range.getSheet().getName();
    if (!isWatchedSheet_(sheetName)) {
      logRun_('onEdit', 'ignored_sheet', { sheet: sheetName });
      return;
    }
  }
  scheduleProcessing_('onEdit');
}

/** Manejador instalable `onChange`. */
function handleOnChange(e) {
  if (e && e.changeType === 'EDIT') {
    // Las ediciones reales las cubre onEdit; onChange aporta cambios de
    // estructura/inserción. Se procesa igual y el hash descarta no-ops.
    logRun_('onChange', 'received', { change_type: String(e.changeType) });
  }
  scheduleProcessing_('onChange');
}

/** ¿La hoja participa en el mapeo 1:1? */
function isWatchedSheet_(name) {
  var keys = Object.keys(CONFIG.SHEETS);
  for (var i = 0; i < keys.length; i++) {
    if (CONFIG.SHEETS[keys[i]] === name) return true;
  }
  return false;
}

/** Coalesce la ráfaga y drena hasta 5 ciclos con el lock de script. */
function scheduleProcessing_(trigger) {
  var cache = CacheService.getScriptCache();
  cache.put('PENDING_COALESCE', '1', 30);
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) {
    // Otra ejecución coalesce esta solicitud; sale sin perder el cambio.
    logRun_(trigger, 'coalesced_lock', {});
    return;
  }
  try {
    var cycles = 0;
    do {
      cache.remove('PENDING_COALESCE');
      sleepMs_(CONFIG.COALESCE_MS);
      sendCurrentState_(trigger);
      cycles++;
    } while (cache.get('PENDING_COALESCE') && cycles < 5);
  } finally {
    lock.releaseLock();
  }
}

/** Instala (idempotente) los triggers instalables del origen. */
function installTriggers() {
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var handlers = [CONFIG.HANDLERS.onEdit, CONFIG.HANDLERS.onChange, CONFIG.HANDLERS.retry];
  var existing = ScriptApp.getProjectTriggers();
  for (var i = 0; i < existing.length; i++) {
    if (handlers.indexOf(existing[i].getHandlerFunction()) >= 0) {
      ScriptApp.deleteTrigger(existing[i]);
    }
  }
  ScriptApp.newTrigger(CONFIG.HANDLERS.onEdit).forSpreadsheet(spreadsheet).onEdit().create();
  ScriptApp.newTrigger(CONFIG.HANDLERS.onChange).forSpreadsheet(spreadsheet).onChange().create();
  ScriptApp.newTrigger(CONFIG.HANDLERS.retry).timeBased().everyMinutes(1).create();
  logRun_('install', 'success', { triggers: handlers.join(',') });
}

/** Elimina los triggers gestionados por este script. */
function uninstallTriggers() {
  var handlers = [CONFIG.HANDLERS.onEdit, CONFIG.HANDLERS.onChange, CONFIG.HANDLERS.retry];
  var existing = ScriptApp.getProjectTriggers();
  for (var i = 0; i < existing.length; i++) {
    if (handlers.indexOf(existing[i].getHandlerFunction()) >= 0) {
      ScriptApp.deleteTrigger(existing[i]);
    }
  }
  logRun_('uninstall', 'success', {});
}
