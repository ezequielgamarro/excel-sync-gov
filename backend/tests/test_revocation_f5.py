"""Tests de la re-verificación de rol y lista de revocación (T37, RNF-03.e).

Lógica pura (sin Redis ni red): ``MemoryRevocationBackend`` + ``ReauthRegistry``
cubren el cierre de WSS ≤ 30 s cuando un ``sub`` pierde el rol o se desactiva.

    py backend/tests/test_revocation_f5.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.revocation import (  # noqa: E402
    MemoryRevocationBackend,
    ReauthRegistry,
)

_LIVE = "dash.view.live"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _registry() -> ReauthRegistry:
    return ReauthRegistry(MemoryRevocationBackend())


def test_active_session_is_ok() -> None:
    registry = _registry()
    _run(registry.register("op-1", frozenset({_LIVE})))
    assert _run(registry.recheck("op-1", _LIVE)) == "ok"


def test_revoked_sub_is_closed() -> None:
    registry = _registry()
    _run(registry.register("op-1", frozenset({_LIVE})))
    _run(registry.mark_revoked("op-1", reason="user_disabled"))
    assert _run(registry.recheck("op-1", _LIVE)) == "revoked"


def test_lost_capability_is_revoked() -> None:
    registry = _registry()
    _run(registry.register("op-1", frozenset({_LIVE})))
    # El backend observa que el sub ya no tiene dash.view.live.
    _run(registry.set_capabilities("op-1", frozenset({"audit.view"})))
    assert _run(registry.recheck("op-1", _LIVE)) == "revoked"


def test_role_change_keeps_session_but_signals_recheck() -> None:
    registry = _registry()
    _run(registry.register("op-1", frozenset({_LIVE, "audit.view"})))
    _run(registry.set_capabilities("op-1", frozenset({_LIVE, "dash.view.history"})))
    # Conserva la capacidad requerida pero cambiaron los roles ⇒ 4403.
    assert _run(registry.recheck("op-1", _LIVE)) == "role_changed"


def test_unknown_session_is_not_blocked() -> None:
    registry = _registry()
    assert _run(registry.recheck("desconocido", _LIVE)) == "ok"


def test_unregister_clears_local_state() -> None:
    registry = _registry()
    _run(registry.register("op-1", frozenset({_LIVE})))
    registry.unregister("op-1")
    # Aunque el backend remoto conserve las capacidades, sin sesión local no se
    # bloquea (no hay WSS que cerrar).
    assert _run(registry.recheck("op-1", _LIVE)) == "ok"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
            else:
                print(f"PASS {name}")
    if failures:
        raise SystemExit(1)
    print("OK")
