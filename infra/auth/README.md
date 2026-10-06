# Auth nativa JWT — despliegue

El sistema **no** despliega un proveedor de identidad externo ni SSO. La
autenticación es **nativa** del backend FastAPI: login usuario+contraseña contra
el almacén local PostgreSQL (`app.user_account`, hash **Argon2id**), emisión y
verificación de JWT propios (access corto + refresh rotativo) y RBAC por
capacidad. No hay segundo factor ni reautenticación por acción.

## Secretos (gestor de secretos → entorno)

| Secreto | Uso | Rotación |
|---------|-----|----------|
| `JWT_SIGNING_KEY` | Firma HS256 (`JWT_ALGORITHM=RS256` ⇒ clave privada PEM) | 90 días con solape de validación |
| `DATABASE_URL` | Conexión del backend (`svc_dashboard`) | 90 días |
| `WEBHOOK_SECRET` | HMAC del webhook de Apps Script | 90 días, solape 24 h |
| `KEK_MATERIAL` / `DATA_KEY` | Envelope encryption de instantáneas | 90 d / 30 d |

Jamás se versionan, embeben en el bundle ni registran en logs (RNF-13).

## Usuarios locales

- Alta/baja/roles vía `POST/PUT/DELETE /api/v1/admin/users*` con capacidad
  `platform.manage_users` (la baja es lógica: `estado='deshabilitado'`).
- Las contraseñas cumplen la política (`PASSWORD_MIN_LENGTH`,
  `PASSWORD_REQUIRE_COMPLEXITY`); el bloqueo por intentos usa
  `LOGIN_MAX_FAILURES`/`LOGIN_LOCKOUT_*`.
- Al deshabilitar o retirar rol se revoca la sesión y se cierra el WSS en ≤ 30 s.

## Identidad propia

No hay manifiestos de un proveedor externo: el realm, clientes, JWKS o Admin API
de un IdP no forman parte de este despliegue. Toda la identidad se gestiona en el
backend y en PostgreSQL.

## Aprovisionamiento y rotación (T74)

- **Almacén de usuarios**: PostgreSQL gestionado de alta disponibilidad con
  PITR/failover (`../terraform/database.tf`). Las tablas `app_user` y
  `refresh_token` se crean por migraciones (`backend/alembic/`).
- **`JWT_SIGNING_KEY`**: se custodia en Secret Manager con rotación programada a
  90 días (`../terraform/secrets.tf`). La rotación efectiva se ejecuta con
  [`rotate-jwt-signing-key.sh`](rotate-jwt-signing-key.sh): publica la versión
  nueva, reinicia las réplicas en *rolling deploy* y retira la anterior tras la
  ventana de solape. Los access tokens de 15 min acotan la ventana de coexistencia.
- **Backup del almacén local**: la tabla de usuarios (incluidos los hashes
  Argon2id) entra en el backup diario cifrado con retención 35 d / 12 semanas /
  24 meses (`../backup/`, RNF-14.f).
- **Sin valores en el repo**: todos los valores se inyectan en runtime desde el
  gestor de secretos; el repositorio solo contiene plantillas de nombres
  (`.env.example`) y código IaC sin material secreto.
