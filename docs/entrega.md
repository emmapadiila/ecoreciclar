# Entrega y preparación de pull request

## Resultado

Se implementó una base única de 18 tablas sobre el checkout vacío, con PostgreSQL 17, migraciones versionadas, API de referencia, controles transaccionales, seed idempotente, pruebas y documentación. Los resultados ejecutados están en [evidencias](evidencias.md); los contratos y diferencias entre propuestas, en [arquitectura](arquitectura.md).

No se eliminó ni sustituyó código de Emma, Breiner o Manuel. No se hizo commit/push ni se publicó un PR. El remoto configurado es `https://github.com/emmapadiila/ecoreciclar.git`, pero consultar sus ramas falló por falta de credenciales. La rama local de trabajo es `feature/infraestructura`; antes de publicar hay que revisar la base remota y conciliar cualquier desarrollo externo. No forzar push ni inventar una historia común con una rama remota no inspeccionada.

## Inventario exacto de archivos de entrega

Todos son nuevos respecto al checkout inicial. Los paquetes `__init__.py` son marcadores, no implementaciones paralelas.

| Archivo | Función |
|---|---|
| [compose.yaml](../compose.yaml) | PostgreSQL 17, volumen, red interna, localhost, healthchecks, perfil API y Adminer opcional |
| [Dockerfile](../Dockerfile) | API Python 3.12 con usuario de sistema no root |
| [.dockerignore](../.dockerignore) | Excluir secretos/datos del contexto de construcción |
| [.env.example](../.env.example) | Variables sin secretos |
| [.gitignore](../.gitignore) | Excluir secretos, venv, backups y uploads |
| [requirements.txt](../requirements.txt) | Dependencias directas fijadas |
| [pytest.ini](../pytest.ini) | Configuración de pruebas |
| [alembic.ini](../alembic.ini) | Ubicación de migraciones |
| [README.md](../README.md) | Instalación Linux/Windows, operación, despliegue y troubleshooting |
| [backend/__init__.py](../backend/__init__.py) | Paquete backend |
| [backend/models.py](../backend/models.py) | Metadata SQLAlchemy única de 18 tablas |
| [backend/db.py](../backend/db.py) | Configuración y sesiones transaccionales |
| [backend/auth.py](../backend/auth.py) | Hashes scrypt y validación JWT |
| [backend/services.py](../backend/services.py) | Enrutamiento, asignación, programación, cierre y recepción idempotente |
| [backend/main.py](../backend/main.py) | FastAPI, validación de entradas y permisos |
| [database/migrations/env.py](../database/migrations/env.py) | Ejecución Alembic y metadata |
| [database/migrations/script.py.mako](../database/migrations/script.py.mako) | Plantilla de revisiones futuras |
| [database/migrations/versions/0001_schema.py](../database/migrations/versions/0001_schema.py) | Revisión inicial versionada |
| [database/migrations/versions/0001_schema.sql](../database/migrations/versions/0001_schema.sql) | DDL congelado con constraints, índices y comentarios |
| [database/migrations/versions/0002_business_rules.py](../database/migrations/versions/0002_business_rules.py) | Revisión de reglas de negocio |
| [database/migrations/versions/0002_business_rules.sql](../database/migrations/versions/0002_business_rules.sql) | Triggers de permisos, auditoría, cierre, vigencia y puntos |
| [database/migrations/versions/0003_audit_inserts.py](../database/migrations/versions/0003_audit_inserts.py) | Rechazo de inserción directa de historial |
| [database/seed_demo.sql](../database/seed_demo.sql) | Catálogo, usuarios y dos flujos programados ficticios |
| [scripts/__init__.py](../scripts/__init__.py) | Paquete de herramientas |
| [scripts/init_env.py](../scripts/init_env.py) | Generación local de secretos, sin sobrescribir archivos |
| [scripts/seed.py](../scripts/seed.py) | Ejecutar SQL DEMO en una transacción |
| [scripts/create_test_db.py](../scripts/create_test_db.py) | Crear base `_test` sin eliminar bases existentes |
| [scripts/demo_complete.py](../scripts/demo_complete.py) | Completar ambos cierres solo en base `_test` |
| [scripts/provision_runtime.py](../scripts/provision_runtime.py) | Rol SQL no propietario y privilegios mínimos de operación |
| [scripts/set_password.py](../scripts/set_password.py) | Credenciales web manuales con entrada oculta |
| [scripts/smoke_runtime.py](../scripts/smoke_runtime.py) | Ambos flujos con rol SQL limitado |
| [scripts/verify_operations.py](../scripts/verify_operations.py) | Reinicio opcional, dump, restore nuevo y comparación de contenido |
| [scripts/render_schema_docs.py](../scripts/render_schema_docs.py) | Diccionario y ER derivados de metadata, sin datos de residentes |
| [tests/conftest.py](../tests/conftest.py) | PostgreSQL real, migraciones y aislamiento de fixtures |
| [tests/test_workflows.py](../tests/test_workflows.py) | 40 casos parametrizados de reglas, API y concurrencia |
| [docs/modelo-datos.md](modelo-datos.md) | Cada tabla/columna/tipo/nulabilidad/PK/FK/índice/default y motivo |
| [docs/diagrama-er.md](diagrama-er.md) | ER Mermaid compatible con GitHub |
| [docs/arquitectura.md](arquitectura.md) | Flujos, API, seguridad y decisiones de conciliación |
| [docs/evidencias.md](evidencias.md) | Comandos, resultados observados y aceptación |
| [docs/entrega.md](entrega.md) | Este inventario y pendientes de equipo |

Elementos locales deliberadamente fuera de Git: `.env` con credenciales aleatorias, `.venv`, caches, volumen Docker, dump/informe de `backups/`. Se conserva la base restaurada de pruebas; no contiene información real. No registrar ni publicar el dump como artefacto público.

## Resumen listo para el PR

**Título:** Infraestructura PostgreSQL 17 y flujos transaccionales EcoConecta 360.

**Cambios:** un esquema conciliado de 18 tablas, Alembic desde cero, SQLAlchemy/FastAPI de referencia, roles runtime, fixtures reproducibles y operación/restauración documentada.

**Verificación:** 40 pruebas PostgreSQL reales aprobadas; dos flujos completados también con rol limitado; mensaje concurrente y cierre concurrente idempotentes; rollback probado; reinicio y backup/restore verificados; API Docker saludable. No se probaron servicios Meta/IA ni producción.

**Revisión solicitada:** Breiner confirma modelos, estados, autenticación y contrato; Manuel integra firma Meta y worker de mensajes/outbox; Emma consume endpoints y valida la presentación local de horas; Ángel mantiene migraciones y operación. No se presume aprobación del equipo ni de la Fundación.

## Pendientes, riesgos y responsables

| Pendiente / riesgo concreto | Estado y siguiente paso | Responsable |
|---|---|---|
| Backend de Breiner no presente | Confirmar el contrato antes de integrar; si llega un esquema existente, migrar/renombrar preservando IDs, nunca crear otro paralelo | Breiner + Ángel |
| Remoto requiere autenticación | Autenticar GitHub, revisar rama base, resolver diferencias, revisar diff y abrir PR sin secretos | Ángel + Emma |
| Participantes y puntos oficiales | Aprobar usuarios y factores reales con la Fundación; los datos/reglas DEMO no sirven como autorización real | Breiner + Emma (validación Fundación) |
| Webhook WhatsApp real | Implementar firma, remitente verificado, correlación de cuenta y pruebas con Meta; no exponer helper interno sin validación | Manuel + Breiner |
| Procesamiento y envíos reales | Worker con bloqueo/transacción para efectos del mensaje, reintentos/outbox, errores y acceso protegido a imágenes | Manuel |
| IA | Persistir sugerencias y revisión humana sin permitir que IA confirme peso/cierre | Manuel + Breiner |
| Panel React | Consumir API con token, mostrar estados y pesos reales, convertir UTC a America/Bogota; confirmar contrato visual | Emma |
| Instalación Windows y reproducción por otra persona | Ejecutar README en Windows y en un entorno limpio del equipo; registrar evidencia adicional | Ángel + Emma |
| Despliegue público | Dominio/TLS, rate-limit, secretos únicos, red DB sin puerto, revisiones de dependencias e imágenes y monitorización | Ángel + Breiner |
| Retención y acceso a fotos/chats | Validar propuesta de 30 días, implementar eliminación de contenido bajo política aprobada; conservar trazabilidad/deduplicación necesaria | Manuel + Ángel + Emma |
| Vigencias de reglas usadas | Definir intervalos finitos aprobados antes de usar; regla usada inmutable, nuevas versiones para el futuro | Ángel + Breiner |
| Reasignación, reprogramación terminal, canjes | Fuera del MVP pedido; diseñar nuevos eventos/debitos y migraciones si se autorizan, no sobrescribir ledger | Breiner + Ángel |
| Backups de producción | Definir custodio, cifrado, retención y RPO/RTO; el ensayo local no sustituye estrategia de recuperación del servidor real | Ángel |

No hay un bloqueo técnico para usar y revisar la implementación local. La publicación remota y las integraciones externas dependen de accesos y decisiones que no estaban disponibles en la conversación.
