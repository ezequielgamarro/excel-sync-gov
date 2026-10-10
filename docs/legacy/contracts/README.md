# Contratos (Contracts)

Este directorio contiene la **fuente única de verdad** del contrato de datos y de la API del sistema. Backend, Apps Script (origen Google Sheets) y dashboard se desarrollan en paralelo contra estos contratos, sin acoplarse a la implementación del otro (ver `plan.md`, Fase F0).

## Convención de rutas

```
contracts/
├── messages/                  # JSON Schema de mensajes WSS (sobre "indicators.snapshot")
│   ├── <version>.schema.json  # p. ej. 1.0.0.schema.json (inmutable)
│   └── <version>.example.json # ejemplo válido que CI valida contra el schema
└── openapi.yaml               # Contrato OpenAPI de la API REST + WSS (§10)
```

- **Mensajes:** `contracts/messages/<version>.schema.json`, donde `<version>` es semver (`MAJOR.MINOR.PATCH`). Por ejemplo `1.0.0.schema.json`. Cada versión publicada tiene al menos un ejemplo co-localizado `<version>.example.json`.
- **API:** `contracts/openapi.yaml`, única fuente de los endpoints REST y del canal WSS.

## Versionado del esquema de mensajes

La política de versionado está definida en la **spec §7.8**. Esta sección la concreta en reglas operativas para decidir, ante cada cambio de contrato, si es **MAJOR**, **MINOR** o **PATCH**.

### Clasificación de un cambio (`MAJOR.MINOR.PATCH`)

El criterio rector es la **compatibilidad hacia atrás**: un cambio es *no rompedor* si un cliente anterior sigue procesando los mensajes nuevos (ignorando lo que no conoce) y un productor anterior sigue siendo aceptado por el backend (fail-closed no rechaza).

| Cambio en el schema | Versión | ¿Por qué? |
|---------------------|---------|-----------|
| **Renombrar** un campo | **MAJOR** | El cliente anterior busca la clave canónica antigua y no la encuentra → estado incompleto/roto. Las claves canónicas (KPI/unidad/dependencia) **nunca** se renombran dentro de un major (§7.8). |
| **Eliminar** un campo | **MAJOR** | El cliente anterior espera el campo y lo pierde; datos que se daban dejan de darse. |
| **Cambiar el tipo** de un campo (p. ej. `string` → `number`) | **MAJOR** | El cliente anterior deserializa con el tipo viejo → fallo o corrupción. |
| **Cambiar la unidad / semántica** de un valor (p. ej. KPI de % a absoluto) | **MAJOR** | El significado del dato cambia aunque el tipo sea el mismo → cifras malinterpretadas. |
| **Añadir un campo `required`** (obligatorio) nuevo | **MAJOR** | Un productor anterior que no lo envía es **rechazado** (fail-closed: "campo obligatorio ausente → rechaza el evento completo"), y un cliente anterior carece de un dato que el contrato nuevo declara imprescindible. |
| **Estrechar** una restricción (enum más corto, rango menor, `pattern` nuevo) | **MAJOR** | Documentos antes válidos pasan a ser inválidos → fail-closed rechaza. |
| **Añadir un campo opcional** nuevo (con valor por defecto) | **MINOR** | El cliente anterior **tolera** el campo desconocido (lo ignora) y sigue funcionando; el cliente nuevo **debe** saber trabajar sin ese campo (default). |
| **Ampliar** de forma aditiva (nuevo valor en un enum, nueva clave canónica de KPI/unidad/dependencia) | **MINOR** | Solo añade posibilidades; no invalida lo existente. |
| **Fix editorial** (`label`, `description`, `title`, tooltip, ejemplos) sin alterar estructura ni validación | **PATCH** | Transparente: no cambia forma ni valores aceptados. |

Reglas de tolerancia que sostienen esta clasificación (§7.8):

- **Campos desconocidos:** el cliente los **ignora** y registra en consola como `warn` (no rompen). Esto es lo que permite que un *Minor* sea no rompedor.
- **Campos obligatorios ausentes / tipos inválidos:** el cliente **rechaza el evento completo** (fail-closed), registra y mantiene el último estado válido (no aplica un estado parcial). Esto es lo que hace que un *Major* sea realmente bloqueante.

### Cómo se versiona `contracts/messages/<version>.schema.json`

1. Cada versión publicada es un archivo **inmutable**: `contracts/messages/<version>.schema.json`, donde `<version>` es `MAJOR.MINOR.PATCH` (p. ej. `1.0.0.schema.json`). Un archivo ya publicado **no se edita**: cualquier cambio genera un archivo nuevo con la versión que corresponda según la tabla anterior.
2. **Cambio PATCH** → se publica un archivo nuevo `1.0.x.schema.json` (p. ej. `1.0.1.schema.json`); `schema_version` pasa a `1.0.1`.
3. **Cambio MINOR** → `1.1.0.schema.json`; `schema_version` pasa a `1.1.0`.
4. **Cambio MAJOR** → `2.0.0.schema.json`; `schema_version` pasa a `2.0.0`.
5. **Ventana de soporte:** el backend publica y soporta las **dos últimas minors** del cliente en coexistencia durante los despliegues; la SPA se despliega **antes** que el backend para evitar incompatibilidades (§7.8). Los archivos `*.schema.json` de minors soportadas se conservan en el repo.
6. **Ejemplos en CI:** por cada archivo `1.0.0.schema.json` existe al menos un `1.0.0.example.json` (misma versión) que CI valida contra el schema; todo cambio de contrato actualiza los ejemplos validados (regla de oro #3).
7. **Publicación en runtime:** el backend sirve el JSON Schema en `/schema/messages/{version}` (ver `openapi.yaml`, `GET /schema/messages/{version}`), de modo que un cliente con `schema_version` mayor no soportada recibe `410` (REST) / cierre WSS `4010` y muestra `ACTUALIZACIÓN REQUERIDA`.

## Reglas de oro

1. Los contratos son **estables** dentro de un major; las claves canónicas de KPI/unidad/dependencia se mantienen y solo se **añaden** claves (no se renombran).
2. Ningún secreto, URL interna ni material sensible se incluye en los contratos (RNF-13).
3. Todo cambio de contrato pasa por semver y actualiza los ejemplos validados en CI.
