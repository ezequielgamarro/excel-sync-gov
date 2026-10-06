"""Aísla ``sys.modules`` entre módulos de test.

Varios tests instalan *stubs* (`types.ModuleType`) en ``sys.modules`` para poder
correr sin las dependencias de runtime. Al ejecutar toda la carpeta junta, esos
stubs pisan los módulos reales y rompen a los tests siguientes (errores de
colección y de ejecución). Aquí se aísla cada archivo de test:

1. ``pytest_collectstart`` limpia los módulos "stubeables" antes de importar
   cada archivo, de modo que su import no vea los stubs del archivo anterior.
2. ``pytest_collectreport`` captura el estado de ``sys.modules`` *después* de
   importar cada archivo (que es el estado que ese archivo espera en runtime,
   porque pytest recolecta todos los módulos antes de ejecutar ningún test).
3. ``pytest_runtest_setup`` restaura ese estado al empezar a correr los tests de
   cada archivo, para que los imports diferidos (p. ej. ``record_audit`` en
   ``app/services/replay.py``) resuelvan contra los módulos correctos.

No se tocan numpy/pandas ni otras librerías reales no "stubeables" para no forzar
reimports innecesarios.
"""

from __future__ import annotations

import sys
import types

import pytest

_BASELINE: dict[str, types.ModuleType] = {}

# Raíces que los tests sustituyen por stubs.
_STUBBABLE_ROOTS = frozenset({"app", "fastapi", "starlette", "sqlalchemy", "redis"})

# Estado de ``sys.modules`` capturado tras importar cada archivo de test,
# indexado por el nodeid del módulo (p. ej. ``backend/tests/test_x.py``).
_SNAPSHOTS: dict[str, dict[str, types.ModuleType]] = {}

# Último módulo cuyos tests se están ejecutando (para restaurar una sola vez).
_CURRENT_MODULE: dict[str, str] = {}


def _is_stubbable(name: str) -> bool:
    return name.split(".", 1)[0] in _STUBBABLE_ROOTS


def pytest_configure(config: pytest.Config) -> None:
    _BASELINE.clear()
    _BASELINE.update(sys.modules)


def pytest_collectstart(collector: pytest.Collector) -> None:
    if not isinstance(collector, pytest.Module):
        return
    for name in list(sys.modules):
        if name not in _BASELINE and _is_stubbable(name):
            del sys.modules[name]


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if not report.nodeid.endswith(".py"):
        return
    _SNAPSHOTS[report.nodeid] = {
        name: module for name, module in sys.modules.items() if _is_stubbable(name)
    }


def pytest_runtest_setup(item: pytest.Item) -> None:
    module_id = item.nodeid.split("::", 1)[0]
    if _CURRENT_MODULE.get("module") == module_id:
        return
    _CURRENT_MODULE["module"] = module_id
    snapshot = _SNAPSHOTS.get(module_id)
    if snapshot is None:
        return
    for name in list(sys.modules):
        if _is_stubbable(name) and name not in snapshot:
            del sys.modules[name]
    for name, module in snapshot.items():
        sys.modules[name] = module
