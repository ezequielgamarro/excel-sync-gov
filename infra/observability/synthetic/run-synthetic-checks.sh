#!/usr/bin/env bash
# =============================================================================
# infra/observability/synthetic/run-synthetic-checks.sh — runner de sondeos
# sintéticos por minuto (T77, RNF-06.a / RNF-07.f).
#
# Ejecuta los checks declarados (por defecto los de `checks.yaml`) con `curl`,
# comprueba código HTTP y latencia, y publica el resultado como texto para el
# recolector. Pensado para cron/Cloud Scheduler cada 60 s; Prometheus hace lo
# propio vía blackbox_exporter.
#
# Uso:
#   API_HOST=api.example.gov DASHBOARD_HOST=dashboard.example.gov \
#     infra/observability/synthetic/run-synthetic-checks.sh
# =============================================================================
set -uo pipefail

API_HOST="${API_HOST:-api.example.gov}"
DASHBOARD_HOST="${DASHBOARD_HOST:-dashboard.example.gov}"
TIMEOUT="${TIMEOUT:-10}"

# id|url|expect_status|max_latency_ms (0 = sin umbral)
CHECKS=(
    "api-liveness|https://${API_HOST}/health/live|200|0"
    "api-readiness|https://${API_HOST}/health/ready|200|0"
    "cold-start|https://${API_HOST}/dashboard/snapshot|200|1500"
    "dashboard-shell|https://${DASHBOARD_HOST}/|200|0"
)

failures=0
for check in "${CHECKS[@]}"; do
    IFS='|' read -r id url expect max_ms <<< "${check}"
    result="$(curl -sS -o /dev/null -w '%{http_code} %{time_total}' \
        --max-time "${TIMEOUT}" "${url}" 2>/dev/null)" || result="000 0"
    status="${result%% *}"
    seconds="${result##* }"
    latency_ms="$(awk "BEGIN {printf \"%d\", ${seconds} * 1000}")"

    ok=true
    [ "${status}" = "${expect}" ] || ok=false
    if [ "${max_ms}" != "0" ] && [ "${latency_ms}" -gt "${max_ms}" ]; then ok=false; fi

    if [ "${ok}" = "true" ]; then
        echo "OK   ${id} status=${status} latency_ms=${latency_ms}"
    else
        echo "FAIL ${id} status=${status} latency_ms=${latency_ms} (esperado ${expect}, max ${max_ms} ms)"
        failures=$((failures + 1))
    fi
done

if [ "${failures}" -gt 0 ]; then
    echo "==> ${failures} synthetic check(s) en rojo"
    exit 1
fi
echo "==> Todos los synthetic checks OK"
