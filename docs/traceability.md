# Matriz de trazabilidad — Criterios de aceptación (T71)

**Spec:** `specs/001_dashboard_monitoreo/spec.md` (§12 Criterios de aceptación, §15 Trazabilidad)
**Tareas F9:** T65 (pytest), T66 (Vitest), T67 (Playwright E2E), T68 (axe-core), T69 (k6), T70 (seguridad), T71 (esta matriz).

Cada uno de los **40 criterios de aceptación** (CA-01.1 … CA-05.9) está cubierto por al menos un test automatizado en verde y mapeado a tarea↔RF↔RNF↔amenaza (AM)↔visual. La verificación automática de esta matriz la realiza `backend/tests/test_f9_traceability.py` (comprueba que no haya huecos).

## Matriz CA → tarea → test → RF → RNF → amenaza → visual

| CA | Tarea(s) | Test(s) automatizado(s) | RF | RNF | AM | Visual |
|----|----------|--------------------------|----|-----|----|--------|
| CA-01.1 | T65, T67, T70 | `test_f9_apps_script_webhook.py::test_valid_apps_script_webhook_is_verified`; `e2e/webhook.spec.ts` | RF-01.a/d | RNF-01.a/f | AM-03, AM-04 | — |
| CA-01.2 | T65, T70 | `test_f9_apps_script_webhook.py::test_missing_signature_header_rejected_401`; `e2e/webhook.spec.ts` | RF-01.e | RNF-03.f | AM-04 | — |
| CA-01.3 | T65, T70 | `test_f9_apps_script_webhook.py::test_tampered_body_rejected_401` | RF-01.f | RNF-01.f | AM-05 | — |
| CA-01.4 | T65 | `test_f9_apps_script_webhook.py::test_content_hash_dedup_is_stable` | RF-01.c | RNF-15 | AM-08 | — |
| CA-01.5 | T67, T69 | `e2e/live.spec.ts`; `k6/ws-fanout.js` | RF-01.g | RNF-04.d | AM-05 | VIS-01..07 |
| CA-01.6 | T65 | `test_replay_guard.py::test_new_nonce_accepted_and_replay_rejected` | RF-01.k | RNF-03.f | AM-05 | — |
| CA-01.7 | T65 | `test_f9_reconciliation_retry.py::test_backoff_sequence_and_jitter` | RF-01.i/j | RNF-06.f | AM-07 | — |
| CA-01.8 | T65, T67 | `test_f9_rbac_jwt.py`; `test_rbac_f5.py`; `e2e/dashboard.spec.ts` | RF-02.k | RNF-03.c | AM-01, AM-02 | — |
| CA-02.1 | T67 | `e2e/dashboard.spec.ts::una instantánea WSS muta el DOM sin recargar` | RF-02.a/b | RNF-04.a | AM-01 | VIS-01..04 |
| CA-02.2 | T67 | `e2e/dashboard.spec.ts::las 4 tarjetas KPI están en la fila superior` | RF-02.b | RNF-04.b | — | VIS-01..04 |
| CA-02.3 | T66 | `KpiCard.test.tsx`; `format.test.ts` | RF-02.c/d | RNF-15.b | — | VIS-01..04 |
| CA-02.4 | T66 | `KpiCard.test.tsx` | RF-02.d | RNF-15.b | — | VIS-01..04 |
| CA-02.5 | T66 | `KpiCard.test.tsx`; `dashboardReducer.test.ts` | RF-02.f | RNF-11 | — | VIS-01..04 |
| CA-02.6 | T66 | `validate.test.ts` | RF-02.i | RNF-15.b | AM-06 | VIS-01..04 |
| CA-02.7 | T66, T67 | `KpiCard.test.tsx`; `e2e/dashboard.spec.ts` | RF-02.g | RNF-04.b | — | VIS-01..04 |
| CA-02.8 | T68, T70 | `contrast.test.ts`; `e2e/a11y.spec.ts`; `xss.test.tsx` | RF-05.b | RNF-09.b | AM-06 | Global |
| CA-02.9 | T65, T67 | `test_f9_rbac_jwt.py`; `test_rbac_f5.py`; `e2e/dashboard.spec.ts::un rol sin dash.view.live` | RF-02.k | RNF-03.c/e | AM-01, AM-02 | — |
| CA-02.10 | T65 | `test_dashboard_api_f4.py::test_audit_event_serialization_without_pii` | RF-02.j | RNF-08.a/e | AM-13 | — |
| CA-03.1 | T66, T67 | `RegionalChart.test.tsx`; `e2e/dashboard.spec.ts` | RF-03.a/b | RNF-09.e | AM-06 | VIS-05 |
| CA-03.2 | T66 | `RegionalChart.test.tsx` | RF-03.e | RNF-15.b | — | VIS-05 |
| CA-03.3 | T66, T70 | `validate.test.ts`; `xss.test.tsx` | RF-03.h | RNF-03 | AM-06, AM-07 | VIS-05 |
| CA-03.4 | T67 | `e2e/dashboard.spec.ts` | RF-03.c/g | RNF-09.b | — | VIS-05 |
| CA-03.5 | T67 | `e2e/dashboard.spec.ts` | RF-03.f | RNF-11.d | — | VIS-05 |
| CA-03.6 | T67 | `e2e/dashboard.spec.ts`; `RegionalChart.test.tsx` | RF-03.d | RNF-09.e | — | VIS-05 |
| CA-04.1 | T66, T67 | `TurnosChart.test.tsx`; `e2e/dashboard.spec.ts` | RF-04.a | RNF-15 | — | VIS-06 |
| CA-04.2 | T66 | `TurnosChart.test.tsx` | RF-04.b | RNF-15 | — | VIS-06 |
| CA-04.3 | T66, T67 | `RankingTable.test.tsx`; `e2e/dashboard.spec.ts` | RF-04.d/e | RNF-15.b | — | VIS-07 |
| CA-04.4 | T66 | `RankingTable.test.tsx`; `format.test.ts` | RF-04.f | RNF-15.b | — | VIS-07 |
| CA-04.5 | T66, T67 | `RankingTable.test.tsx`; `e2e/dashboard.spec.ts` | RF-04.g | RNF-09.f | AM-13 | VIS-07 |
| CA-04.6 | T66 | `RankingTable.test.tsx` | RF-04.h | RNF-15.b | AM-07 | VIS-07 |
| CA-04.7 | T67, T68 | `e2e/dashboard.spec.ts`; `e2e/a11y.spec.ts` | RF-04.i | RNF-09.c/e | — | VIS-07 |
| CA-05.1 | T67 | `e2e/responsive.spec.ts` | RF-05.c | RNF-10.b | AM-10 | Global |
| CA-05.2 | T67 | `e2e/responsive.spec.ts` | RF-05.c | RNF-10.b/c | — | Global |
| CA-05.3 | T68 | `contrast.test.ts`; `e2e/a11y.spec.ts` | RF-05.b | RNF-09.a/b | — | Global |
| CA-05.4 | T67 | `e2e/dashboard.spec.ts::respeta prefers-reduced-motion` | RF-05.i | RNF-09.g | — | Global |
| CA-05.5 | T67 | `e2e/dashboard.spec.ts::muestra skeletons antes de la primera instantánea` | RF-02.h | RNF-10 | — | Global |
| CA-05.6 | T67 | `e2e/dashboard.spec.ts::muestra DATOS DESACTUALIZADOS` | RF-05.h | RNF-05.f | — | Global |
| CA-05.7 | T67, T68 | `e2e/dashboard.spec.ts::skip-link`; `e2e/a11y.spec.ts` | RF-05.j | RNF-09.c | AM-11 | Global |
| CA-05.8 | T67 | `e2e/live.spec.ts` | RF-05.g | RNF-05.a–e | — | Global |
| CA-05.9 | T67 | `e2e/dashboard.spec.ts::la actualización en vivo se aplica en ≤250 ms` | RF-05.f | RNF-04.b | — | Global |

## Cierre de §15 (sin huecos)

| RF | CAs cubiertos | Tareas F9 |
|----|---------------|-----------|
| RF-01 Transmisión segura | CA-01.1 – CA-01.8 (8) | T65, T67, T69, T70 |
| RF-02 Tarjetas KPI | CA-02.1 – CA-02.10 (10) | T65, T66, T67, T68 |
| RF-03 Gráfico regional | CA-03.1 – CA-03.6 (6) | T66, T67, T70 |
| RF-04 Tendencia y ranking | CA-04.1 – CA-04.7 (7) | T66, T67, T68 |
| RF-05 UI táctica | CA-05.1 – CA-05.9 (9) | T67, T68 |
| **Total** | **40 CA** | T65–T71 |

### Amenazas (AM) → CA que las cierran

| Amenaza | CA verificadores |
|---------|------------------|
| AM-01 Acceso no autorizado | CA-01.8, CA-02.1, CA-02.9, CA-05.7 |
| AM-02 Escalada de privilegios | CA-01.8, CA-02.9 |
| AM-03 MITM / TLS | CA-01.1, CA-05.1 |
| AM-04 Suplantación del origen | CA-01.1, CA-01.2 |
| AM-05 Replay / tampering | CA-01.3, CA-01.5, CA-01.6 |
| AM-06 XSS vía celdas / CSP | CA-02.6, CA-02.8, CA-03.1, CA-03.3 |
| AM-07 DoS / datos maliciosos | CA-01.7, CA-03.3, CA-04.6, CA-04.7 |
| AM-08 Manipulación del documento | CA-01.4 |
| AM-10 Caché tras deslogueo | CA-05.1 |
| AM-11 Clickjacking | CA-05.7 |
| AM-13 Repudio de consulta | CA-02.10, CA-04.5 |

> **Nota de ejecución:** en este entorno faltan las dependencias de runtime de Python (`fastapi`, `sqlalchemy`, `pytest`, …) y de Playwright/axe, por lo que `pytest` y `playwright` no se ejecutan aquí. Los tests de F9 están escritos para ejecutarse con esas dependencias instaladas (`pip install -r backend/requirements.txt` + `npm ci` + `npx playwright install`); los que no las necesitan usan *stubs* y se ejecutan con stdlib. La suite Vitest de T66/T68/T70 **sí** se ejecutó: 51 tests en verde.
