"""Seed de un snapshot de demostración (cold start del dashboard).

Inserta o actualiza (upsert idempotente) una fila válida en
``app.snapshot_current`` con ``doc_id='sifcop-resumen'`` para que
``GET /api/v1/dashboard/snapshot`` deje de responder 503 y el dashboard tenga
datos que pintar. NO publica nada por Redis ni toca la clave ``seq:sala-central``,
por lo que el cold start no responde 409.

Uso (desde ``backend/``)::

    python -m scripts.seed_demo_snapshot

Es idempotente: re-ejecutarlo actualiza la misma fila. ``DATABASE_URL`` se lee
del entorno (nunca se hardcodea, RNF-13).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.tables import snapshot_current
from app.services.db import dispose_engine, get_session

DOC_ID = "sifcop-resumen"


def _document(event_id: str) -> dict:
    """Documento de demostración con la forma exacta del contrato de snapshot."""
    return {
        "schema_version": "1.0.0",
        "event_id": event_id,
        "data_date": date.today().isoformat(),
        "tz": "America/Argentina/Buenos_Aires",
        "sheet_modified_at": datetime.now(timezone.utc).isoformat(),
        "doc_id": DOC_ID,
        "content_sha256": "a" * 64,
        "payload": {
            "kpis": {
                "total_consultas_sifcop": {"label": "Consultas SIFCOP", "value": 184732},
                "personas_capturadas": {"label": "Personas capturadas", "value": 342},
                "vehiculos_secuestrados": {"label": "Vehículos secuestrados", "value": 128},
                "armas_secuestradas": {"label": "Armas secuestradas", "value": 57},
            },
            "regional": [
                {"unidad_id": "capital", "intervenciones": 64210, "variacion_abs": 1200, "variacion_pct": 1.9, "rank": 1},
                {"unidad_id": "sur", "intervenciones": 38900, "variacion_abs": 450, "variacion_pct": 1.2, "rank": 2},
                {"unidad_id": "este", "intervenciones": 32150, "variacion_abs": -300, "variacion_pct": -0.9, "rank": 3},
                {"unidad_id": "oeste", "intervenciones": 27840, "variacion_abs": 220, "variacion_pct": 0.8, "rank": 4},
                {"unidad_id": "norte", "intervenciones": 21632, "variacion_abs": 80, "variacion_pct": 0.4, "rank": 5},
            ],
            "turnos": [
                {"turno_id": "MAÑANA", "inicio_min": 360, "fin_min": 840, "label": "Mañana", "intervenciones": 76500, "variacion_abs": 900, "variacion_pct": 1.2, "estado": "cerrada"},
                {"turno_id": "TARDE", "inicio_min": 840, "fin_min": 1320, "label": "Tarde", "intervenciones": 68200, "variacion_abs": -400, "variacion_pct": -0.6, "estado": "en_curso"},
                {"turno_id": "NOCHE", "inicio_min": 1320, "fin_min": 2160, "label": "Noche", "intervenciones": 40032, "variacion_abs": 300, "variacion_pct": 0.8, "estado": "pendiente"},
            ],
            "ranking": {
                "top_n": 5,
                "dependencias": [
                    {"puesto": 1, "dependencia_id": "dep-1", "comisaria": "Comisaría 1ra Capital", "intervenciones": 8420, "variacion_abs": 320, "variacion_pct": 3.9, "puesto_previo": 2},
                    {"puesto": 2, "dependencia_id": "dep-2", "comisaria": "Comisaría 2da Capital", "intervenciones": 7910, "variacion_abs": -120, "variacion_pct": -1.5, "puesto_previo": 1},
                    {"puesto": 3, "dependencia_id": "dep-3", "comisaria": "Comisaría Sur", "intervenciones": 6450, "variacion_abs": 210, "variacion_pct": 3.4, "puesto_previo": 3},
                    {"puesto": 4, "dependencia_id": "dep-4", "comisaria": "Comisaría Este", "intervenciones": 5230, "variacion_abs": 60, "variacion_pct": 1.2, "puesto_previo": 5},
                    {"puesto": 5, "dependencia_id": "dep-5", "comisaria": "Comisaría Oeste", "intervenciones": 4890, "variacion_abs": -30, "variacion_pct": -0.6, "puesto_previo": 4},
                ],
            },
        },
    }


async def _run() -> int:
    event_id = uuid.uuid4()
    document = _document(str(event_id))
    data_date = date.today()
    now = datetime.now(timezone.utc)

    session = await get_session()
    try:
        stmt = pg_insert(snapshot_current).values(
            doc_id=DOC_ID,
            event_id=event_id,
            agent_id=None,
            payload=document,
            data_date=data_date,
            seq=1,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[snapshot_current.c.doc_id],
            set_={
                "event_id": event_id,
                "agent_id": None,
                "payload": document,
                "data_date": data_date,
                "seq": 1,
                "updated_at": now,
            },
        )
        await session.execute(stmt)
        await session.commit()
        print(
            f"Snapshot demo sembrado: doc_id={DOC_ID} event_id={event_id} "
            f"data_date={data_date} seq=1."
        )
        return 0
    finally:
        await session.close()
        await dispose_engine()


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
