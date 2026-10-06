"""Ticket WSS y endpoint WebSocket ``/ws/dashboard`` (spec §10.3, T29).

Flujo (§10.3):

1. ``POST /api/v1/auth/ws-ticket`` (capacidad ``dash.view.live``) → emite un
   ticket de **un solo uso** (TTL 60 s) que encarna ``sub`` + capacidades +
   ``room_id``.
2. ``wss://…/ws/dashboard?ticket=tkt_…`` → redime el ticket (un solo uso),
   valida ``dash.view.live``, envía ``hello`` (con ``last_seq`` y
   ``heartbeat_interval_s``), se suscribe a ``room:{room_id}`` y reenvía
   ``indicators.snapshot`` + ``heartbeat`` (15 s).

Mensajes servidor→cliente: ``hello``, ``indicators.snapshot``, ``heartbeat``,
``error``. Mensajes cliente→servidor: solo ``ping`` (keepalive) y ``ack``
(métrica de entrega, ignorable); **sin datos de negocio** (P6).

Códigos de cierre (§10.3):

- ``4001`` heartbeat/keepalive expirado.
- ``4003`` capacidad revocada / no autorizado.
- ``4401`` ticket inválido/expirado/ya usado.
- ``4403`` rol/capacidades cambiaron desde la apertura (reservado, hook F5).
- ``1008`` violación de política (límite de conexiones por sala/global).
"""

from __future__ import annotations

import asyncio
import json
import time as _time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from starlette.responses import JSONResponse

from app.config import get_settings
from app.core.logging import get_correlation_id
from app.core.metrics import WSS_CONNECTIONS
from app.services.audit import record_audit
from app.services.bus import SCHEMA_VERSION, get_bus
from app.services.capacity import (
    CAP_DASH_VIEW_LIVE,
    OperatorIdentity,
    get_operator,
    require_capacity,
)
from app.services.revocation import get_reauth_registry
from app.services.ticket import get_ticket_store

# Códigos de cierre (§10.3).
CLOSE_NORMAL = 1000
CLOSE_POLICY = 1008
CLOSE_HEARTBEAT_EXPIRED = 4001
CLOSE_CAPACITY_REVOKED = 4003
CLOSE_TICKET_INVALID = 4401
CLOSE_ROLE_CHANGED = 4403

router = APIRouter(tags=["WebSocket"])  # /ws/dashboard (raíz, según OpenAPI)
auth_router = APIRouter(prefix="/auth", tags=["Auth"])  # /api/v1/auth/ws-ticket


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@auth_router.post("/ws-ticket")
async def create_ws_ticket(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
) -> JSONResponse:
    """Emite un ticket WSS de un solo uso (TTL 60 s) tras comprobar la capacidad."""
    require_capacity(CAP_DASH_VIEW_LIVE, operator)
    settings = get_settings()
    room_id = settings.default_room_id
    ticket = await get_ticket_store().issue(
        sub=operator.sub,
        roles=operator.roles,
        capabilities=operator.capabilities,
        room_id=room_id,
    )
    await record_audit(
        actor=operator.sub,
        action="ws.ticket.issued",
        resource=room_id,
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
    )
    return JSONResponse(
        status_code=200,
        content={"ticket": ticket, "expires_in": settings.ws_ticket_ttl_seconds},
    )


@dataclass
class _ConnState:
    """Estado compartido de una conexión WSS (actividad del cliente, cierre, seq)."""

    last_client_activity: float = 0.0
    closed: bool = False
    last_seq: int = 0

    def __post_init__(self) -> None:
        self.last_client_activity = _time.monotonic()


class _ConnectionLimiter:
    """Límite de conexiones WSS (RNF-12.d): 50 por sala, 200 globales.

    En F4 es un contador **por proceso** (no distribuido); el límite distribuido
    real se impone en el edge/WAF (F5). Exceder → cierre ``1008``.
    """

    def __init__(self, per_room: int = 50, global_: int = 200) -> None:
        self._per_room = per_room
        self._global = global_
        self._rooms: dict[str, int] = {}
        self._total = 0
        self._lock = asyncio.Lock()

    async def acquire(self, room_id: str) -> bool:
        async with self._lock:
            if self._total >= self._global:
                return False
            if self._rooms.get(room_id, 0) >= self._per_room:
                return False
            self._total += 1
            self._rooms[room_id] = self._rooms.get(room_id, 0) + 1
            return True

    async def release(self, room_id: str) -> None:
        async with self._lock:
            self._total = max(0, self._total - 1)
            current = self._rooms.get(room_id, 0)
            if current <= 1:
                self._rooms.pop(room_id, None)
            else:
                self._rooms[room_id] = current - 1


_limiter = _ConnectionLimiter(
    per_room=get_settings().ws_max_connections_per_room,
    global_=get_settings().ws_max_connections_global,
)


async def _receive_loop(websocket: WebSocket, state: _ConnState) -> None:
    """Lee mensajes del cliente (solo ping/ack; sin datos de negocio)."""
    while not state.closed:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            state.closed = True
            return
        state.last_client_activity = _time.monotonic()
        try:
            msg = json.loads(raw)
        except ValueError:
            # Mensaje no JSON: se ignora (el cliente es no confiable, P6).
            continue
        if not isinstance(msg, dict):
            continue
        # ``ping``/``ack`` se ignoran aquí (la actividad ya quedó registrada).
        # Cualquier otro tipo es inofensivo: el WSS es solo *push* (RNF-12.c).


async def _forward_loop(websocket: WebSocket, room_id: str, state: _ConnState) -> None:
    """Reenvía los mensajes de ``room:{room_id}`` al cliente."""
    bus = get_bus()
    async for message in bus.subscribe(room_id):
        if state.closed:
            return
        if isinstance(message, dict) and "seq" in message:
            state.last_seq = int(message["seq"])
        await websocket.send_json(message)


async def _heartbeat_loop(
    websocket: WebSocket,
    state: _ConnState,
    interval: int,
    timeout: int,
    *,
    sub: str,
) -> None:
    """Envía ``heartbeat`` cada 15 s y cierra ``4001`` si el cliente calla 45 s.

    En cada ciclo (≤ 30 s, RNF-03.e) **re-verifica** el rol/capacidad del ``sub``
    contra la lista de revocación: si perdió ``dash.view.live`` → cierre ``4003``;
    si los roles cambiaron pero el acceso sigue autorizado → ``4403``.
    """
    registry = get_reauth_registry()
    while not state.closed:
        await asyncio.sleep(interval)
        if state.closed:
            return
        if _time.monotonic() - state.last_client_activity > timeout:
            state.closed = True
            await websocket.close(code=CLOSE_HEARTBEAT_EXPIRED)
            return
        verdict = await registry.recheck(sub, CAP_DASH_VIEW_LIVE)
        if verdict == "revoked":
            state.closed = True
            await websocket.close(code=CLOSE_CAPACITY_REVOKED)
            return
        if verdict == "role_changed":
            state.closed = True
            await websocket.close(code=CLOSE_ROLE_CHANGED)
            return
        await websocket.send_json(
            {
                "type": "heartbeat",
                "server_ts": _now_iso(),
                "seq_hint": state.last_seq,
            }
        )


@router.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket) -> None:
    """Canal de distribución en tiempo real (fan-out por sala)."""
    settings = get_settings()
    store = get_ticket_store()

    # Se acepta el socket primero para poder enviar códigos de cierre WSS (§10.3).
    await websocket.accept()

    ticket = websocket.query_params.get("ticket", "")
    ticket_payload = await store.redeem(ticket) if ticket else None
    if ticket_payload is None:
        await websocket.close(code=CLOSE_TICKET_INVALID)
        return

    capabilities = {str(c) for c in (ticket_payload.get("capabilities") or [])}
    if CAP_DASH_VIEW_LIVE not in capabilities:
        await websocket.close(code=CLOSE_CAPACITY_REVOKED)
        return

    room_id = str(ticket_payload.get("room_id") or settings.default_room_id)
    sub = str(ticket_payload.get("sub") or "")

    if not await _limiter.acquire(room_id):
        await websocket.close(code=CLOSE_POLICY)
        return

    # Registra las capacidades observadas para la re-verificación periódica (T37).
    await get_reauth_registry().register(sub, frozenset(capabilities))

    await record_audit(
        actor=sub,
        action="ws.connected",
        resource=room_id,
        result="success",
    )

    last_seq = await get_bus().get_last_seq(room_id)
    await websocket.send_json(
        {
            "type": "hello",
            "room_id": room_id,
            "schema_version": SCHEMA_VERSION,
            "server_ts": _now_iso(),
            "last_seq": last_seq or 0,
            "heartbeat_interval_s": settings.ws_heartbeat_interval_s,
        }
    )

    state = _ConnState()
    WSS_CONNECTIONS.labels(room_id=room_id).inc()
    try:
        tasks = [
            asyncio.create_task(_receive_loop(websocket, state)),
            asyncio.create_task(
                _forward_loop(websocket, room_id, state)
            ),
            asyncio.create_task(
                _heartbeat_loop(
                    websocket,
                    state,
                    settings.ws_heartbeat_interval_s,
                    settings.ws_client_timeout_s,
                    sub=sub,
                )
            ),
        ]
        _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    finally:
        WSS_CONNECTIONS.labels(room_id=room_id).dec()
        await _limiter.release(room_id)
        get_reauth_registry().unregister(sub)
        await record_audit(
            actor=sub,
            action="ws.disconnected",
            resource=room_id,
            result="success",
            correlation_id=get_correlation_id(),
        )
