# Evidencias de verificación y aceptación

Fecha de ejecución: **2026-11-20**, entorno Linux, proyecto `/home/gongy/ecoreciclar`. Los resultados siguientes son observados, no resultados esperados. Pruebas con datos exclusivamente DEMO. Se omiten credenciales y contenido personal.

## Entorno y límites

- Docker Engine 29.10.0, Compose v5.7.1, contexto `default`. El contexto seleccionado Desktop apuntaba a un socket ausente; se usó `--context default` sin modificarlo globalmente.
- PostgreSQL **17.12** de imagen `postgres:17`, volumen `ecoreciclar_postgres_data`.
- Python local 3.14.10 en `.venv`; imagen API basada en Python 3.12 slim.
- Dependencias directas fijadas en `requirements.txt`; las transitivas no están bloqueadas en un lockfile. No se declara certificación general de versiones futuras.
- Servidor HTTP Docker probado en `127.0.0.1:8000`. Los flujos completos se probaron por ASGI/TestClient contra PostgreSQL real, también con rol SQL limitado.
- No se probaron Windows real, WhatsApp/IA externos, panel React ni despliegue público.

## Comandos y resultados observados

Los comandos Python se ejecutaron como `.venv/bin/python ...` después de configurar el entorno. La instalación de paquetes se hizo mediante el gestor del entorno con las versiones de `requirements.txt`.

| Comando ejecutado | Resultado |
|---|---|
| `docker version` | Falló inicialmente por permiso/contexto; no se marcó como exitoso |
| `docker --context default version` | Cliente y servidor disponibles |
| `docker compose version` | v5.7.1 |
| `/usr/bin/python scripts/init_env.py` | `.env` privado creado con secretos aleatorios, sin imprimirlos |
| `/usr/bin/python -c 'import sqlalchemy, ...'` | Falló: sistema sin paquetes; se seleccionó `.venv/bin/python` |
| `.venv/bin/python -c '... print(len(Base.metadata.tables))'` | 18 tablas |
| `docker --context default compose up -d --wait db` | PostgreSQL saludable |
| `docker --context default compose ps` antes del ajuste | Solo `5432/tcp`, no puerto publicado; se agregó red de desarrollo |
| `docker --context default compose up -d --wait db` después del ajuste | `127.0.0.1:5432->5432/tcp`, healthy |
| `.venv/bin/python -m alembic upgrade head` | Migración desde base vacía exitosa, inicialmente 0002 y después 0003 |
| `.venv/bin/python -m alembic current` | 0002 en primera aplicación; posteriormente se verificó head 0003 |
| `.venv/bin/python -m alembic check` | `No new upgrade operations detected.` |
| `.venv/bin/python -m scripts.seed` (dos veces) | Dos solicitudes programadas, sin duplicados ni puntos; reglas no aprobadas |
| `.venv/bin/python -m scripts.create_test_db` | `ecoconecta_test` creada separadamente |
| `.venv/bin/python -m pytest -q` primera suite | 33 passed; advertencias de dependencias/configuración |
| `.venv/bin/python -m pytest -q` suite ampliada | **40 passed, 1 warning in 5.62s** |
| `.venv/bin/python -m scripts.provision_runtime` | Rol `ecoconecta_app` creado, sin privilegios de propietario |
| `.venv/bin/python -m scripts.demo_complete` | Ambos cierres: 5 kg/50 puntos ficticios reciclable, 5 kg/25 orgánico |
| `.venv/bin/python -m scripts.demo_complete` repetido | Ambos `ya cerrada; no se duplica` |
| `.venv/bin/python -m scripts.verify_operations --context default --database ecoconecta_test --restart` | Reinicio y backup/restore: PASS, 18 tablas, secuencias y revisión Alembic idénticas |
| `docker --context default compose build api` | Imagen construida con dependencias instaladas |
| `docker --context default compose --profile app up -d --wait api` | DB y API healthy |
| `.venv/bin/python -m scripts.provision_runtime --test` | Permisos runtime habilitados en base de prueba |
| `.venv/bin/python -m scripts.smoke_runtime` | Ambos flujos completos PASS bajo rol no superusuario |
| `curl --fail --silent http://127.0.0.1:8000/health` | `{"status":"ok"}`; consulta real PostgreSQL |
| `.venv/bin/python -m compileall -q backend database/migrations scripts tests` | Sin errores de sintaxis |
| Diagnósticos del editor sobre backend/scripts/tests | `No errors found.` |
| `git check-ignore .env backups/example.dump` | Ambos excluidos de Git |
| `docker --context default compose config --quiet` | Configuración válida, sin imprimir secretos |
| `git switch -c feature/infraestructura` | Rama local creada, sin commits |
| `git add --intent-to-add ...` (lista explícita de entrega) | 40 archivos visibles en diff; sin añadir `.env` ni backups |
| `git diff --check` | Sin errores tras limpiar espacios finales del DDL generado; ningún cambio semántico |
| `git diff --stat` | 40 archivos nuevos, inventario completo en entrega |
| `git ls-remote --heads origin` | Falló por falta de credenciales GitHub: `could not read Username`; no se publicaron cambios |

La advertencia remanente de la suite es `DeprecationWarning` en Starlette TestClient por el alias `anyio.abc.BlockingPortal`; no hubo errores de tests. Se corrigió el warning de Alembic agregando `path_separator = os`.

Un primer intento de demo tras la suite encontró reglas expiradas dejadas por un test negativo y devolvió 409 sin confirmar cierre. Se corrigió el aislamiento: cada caso vacía la base `_test` al terminar. La demo se ejecutó luego con éxito, sin modificar reglas históricas ni aprobar reglas de desarrollo.

Comprobación final de desarrollo: revisión `0003`, **2 solicitudes y 0 movimientos de puntos**. DB y API permanecen saludables y publicados exclusivamente en loopback. Las aprobaciones/cierres ficticios están en la base de pruebas, no en la de desarrollo.

## Backup restaurado

- Dump local excluido de Git: `backups/ecoconecta_20261120T170249Z_4d241b05.dump`.
- Informe local privado con hashes/conteos: mismo nombre con extensión `.json`.
- Base restaurada conservada: `ecoconecta_restore_20261120t170249z_4d241b05_test`.
- Comparación de contenido de **todas las 18 tablas**, no solo conteos; también secuencias y `alembic_version`.
- El snapshot se tomó después de los dos cierres DEMO, antes de los escenarios adicionales del smoke runtime.
- No se borraron bases, volúmenes ni respaldos. El dump contiene solo fixtures en esta ejecución, pero la herramienta debe tratar backups futuros como datos privados.

## Cobertura de reglas

| Regla | Evidencia automatizada |
|---|---|
| Dos flujos completos/persistencia | `test_complete_api_flow`, parametrizado por flujo |
| Aislamiento GET, historial, asignación, programación, cierre, estado | `test_cross_collective_access_forbidden` |
| Autenticación, JWT inválido, login, piloto revocado | `test_authentication_and_disabled_pilot` |
| Identidad WhatsApp persistente/contexto reiniciable | `test_message_identity_and_retries` |
| Mensaje concurrente con una fila/identidad | `test_concurrent_message_delivery` |
| No mezcla, no aceptado, categoría otro | `test_invalid_materials_not_routed` |
| Miembro ajeno, inactivo, material no confirmado | `test_invalid_assignment_rolls_back` |
| Fecha/hora/zona y responsable obligatorios | `test_schedule_requires_datetime_timezone`, `test_request_schedule_without_assignment_is_rejected` |
| Peso real positivo/finito, precisión | `test_close_requires_valid_weight` |
| Regla no aprobada/expirada/solapada | `test_unapproved_rule_rolls_back_entire_close`, `test_expired_rule_and_overlap` |
| Rollback cierre+historial+puntos+notificación | Tests de regla no aprobada y `test_direct_close_without_points_fails_at_commit` |
| Dos cierres simultáneos, una acreditación | `test_concurrent_close_credits_once` |
| UNIQUE, FK, WhatsApp nullable, código único | `test_database_integrity_rejects_direct_sql`, `test_nullable_whatsapp_and_code_unique` |
| Historial no falsificable | `test_fabricated_history_is_rejected` y tests de actualización/borrado |
| Puntos prematuros, otro dueño/colectivo, importe falso | `test_forged_points_are_rejected` |
| Ledger/recolección no alterables ni duplicables | `test_duplicate_and_tampered_points_blocked` |
| Piloto rechazado incluso por SQL interno | `test_request_without_pilot_authorization_rejected_in_database` |
| Runtime no propietario, flujos autorizados | `scripts.smoke_runtime` |

## Checklist de aceptación

### Interfaz de exploración añadida posteriormente (2026-11-20)

Se incorporó Adminer 6.3.0 como servicio opcional `adminer`, perfil `tools`, publicado exclusivamente en `127.0.0.1:8080`. No se modificaron tablas, migraciones ni registros.

- `docker --context default compose config --quiet`: configuración válida.
- `docker --context default compose --profile tools up -d --wait adminer`: contenedor healthy; PostgreSQL existente conservado.
- Navegador integrado: formulario PostgreSQL con servidor `db`, usuario/base `ecoconecta` visibles.
- Comprobación HTTP con sesión: login exitoso, listado de tablas y lectura de `DEMO-ECO-REC` y `DEMO-ECO-ORG` desde la tabla `solicitudes`; contraseña leída localmente, sin imprimirla ni incluirla en URL.
- Diagnósticos de Compose/README y `git diff --check`: sin errores.
- No se repitió la suite de negocio de 40 casos: esta incorporación solo cambia infraestructura opcional y documentación. La verificación específica fue de configuración, salud y acceso real de lectura.
- El arranque por tarea del editor no estuvo disponible (`No invocation context`); se ejecutó directamente con Compose.

### Aceptación del modelo y la infraestructura principal

- [x] PostgreSQL 17 inicia y reporta healthy con puerto localhost.
- [x] Alembic aplica desde base vacía; metadata y esquema coinciden.
- [x] Dos colectivos diferenciados, materiales y miembros separados.
- [x] Identidad WhatsApp persistente; reintentos no duplican mensajes.
- [x] Códigos únicos y autorización de piloto.
- [x] Asignación/programación persistidas con fecha, hora, zona y responsable.
- [x] Coordinador no lee/modifica otro colectivo en FastAPI.
- [x] Peso real, historial y puntos solo al cierre, con una transacción y rollback.
- [x] Cierres concurrentes no duplican acreditación.
- [x] Reinicio conserva datos y secuencias.
- [x] Backup restaurado en base nueva con contenido verificado.
- [x] API conectada a PostgreSQL, salud HTTP y operaciones con rol limitado.
- [x] README, diccionario de todas las columnas y ER Mermaid disponibles.
- [ ] Una segunda persona instala siguiendo README sin ayuda (validación de equipo).
- [ ] Instalación nativa Windows probada físicamente.
- [ ] Breiner confirma/adapta el contrato a su backend real.
- [ ] WhatsApp/IA reales, panel React y despliegue público integrados.
- [ ] Fundación autoriza participantes y equivalencias; no basta el seed.
- [ ] PR remoto publicado: requiere autenticación GitHub y revisar la rama base real.
