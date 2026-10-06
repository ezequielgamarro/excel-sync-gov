# Backend (FastAPI)

El backend es la **frontera de confianza** del sistema: el único componente que verifica identidad e integridad antes de persistir o redistribuir. Expone una API REST (ingesta cifrada, cold start, histórico, salud, métricas, **auth nativa JWT** + admin de usuarios locales) y un canal **WebSocket seguro (WSS)** con fan-out por sala vía Redis pub/sub.

**Stack:** Python 3 · FastAPI · PostgreSQL (historiales, agregados, auditoría append-only, usuarios locales) · Redis (pub/sub, presencia, rate limit) · AES-256-GCM (descifrado de aplicación) · JWT nativo (HS256/RS256) · OpenTelemetry (trazas).

Responsabilidades principales: autenticar al webhook de Apps Script (firma HMAC + anti-replay) y al operador (**login nativo usuario+contraseña → JWT** + capacidades RBAC, sin IdP externo ni MFA), descifrar y validar esquema/rangos, persistir con idempotencia (`event_id` UNIQUE), calcular agregados y variación "vs ayer", emitir auditoría y redistribuir en tiempo real. Se completa en las tareas F2–F5.

## Primer usuario (bootstrap local)

Los endpoints admin de usuarios requieren sesión previa, por lo que el primer operador se crea con el script idempotente `scripts/create_admin.py`. Desde `backend/`:

```bash
python -m scripts.create_admin --username <u> --password <p> [--role platform-admin]
```

`DATABASE_URL` se lee del entorno; la contraseña se valida con la política existente y se guarda como hash Argon2id.

### Corregir el rol de un usuario existente

`create_admin.py` es idempotente: si el usuario ya existe no modifica nada, por lo que no sirve para corregir su rol. Para **reemplazar** los roles de un usuario ya creado usa `scripts.set_user_roles.py`. Desde `backend/`:

```bash
python -m scripts.set_user_roles --username <u> --role supervisor
# o varios roles a la vez:
python -m scripts.set_user_roles --username <u> --roles viewer,supervisor
```

Roles válidos: `viewer`, `supervisor`, `auditor`, `platform-admin`. Ten en cuenta que, por diseño (§2.2.3), `platform-admin` **no** ve el dashboard (no tiene `dash.view.live`): un operador que deba verlo necesita el rol `viewer` o `supervisor`.

## Migraciones (Alembic)

El esquema de PostgreSQL se gestiona con Alembic: [`alembic/README.md`](alembic/README.md) documenta la convención de naming, la estrategia UUIDv7, los esquemas `app`/`audit` y los comandos `upgrade`/`downgrade`. La migración base (`0001_base`, T7) habilita `pgcrypto` y crea los namespaces; las revisiones `0002`–`0009` implementan las tablas (T8–T14) y el rol de servicio `svc_dashboard` con particionado (T15). El modelo completo está en [`docs/schema.md`](docs/schema.md).
