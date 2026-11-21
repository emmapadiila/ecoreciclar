# EcoConecta 360 — PostgreSQL e integración FastAPI

EcoConecta conecta el chatbot de WhatsApp, el panel operativo y PostgreSQL. Para vincular un teléfono y probar mensajes, fotografías y confirmaciones, sigue la [guía de OpenWA paso a paso](docs/whatsapp-openwa.md).

## Documentación

- [Estructura base del frontend](frontend/README.md).
- [Modelo: 18 tablas, columnas, restricciones e índices](docs/modelo-datos.md).
- [Diagrama ER Mermaid](docs/diagrama-er.md).
- [Arquitectura, contrato API, permisos y decisiones de integración](docs/arquitectura.md).
- [Evidencias y checklist de aceptación](docs/evidencias.md).
- [Entrega, archivos, pendientes y responsables](docs/entrega.md).

## 1. Requisitos

- Git; Docker Engine/Desktop en ejecución con Compose v2.24+ o v5, modo Linux containers.
- Python 3.12 recomendado (versión de la imagen); pruebas locales también ejecutadas en 3.14.
- Puertos locales 5432 y 8000 disponibles; conexión a los registros de Docker y PyPI para la primera instalación.
- Ejecutar los comandos desde la raíz del repositorio. No se requieren credenciales Meta/IA para estas pruebas locales.

## 2. Instalación desde cero

Clonar la URL real del equipo, entrar al repositorio y crear una rama de trabajo. No se inventa una URL ni se requiere borrar un checkout existente.

### Linux / macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/init_env.py
docker compose up -d --wait db
docker compose ps
docker compose exec -T db pg_isready -U ecoconecta -d ecoconecta
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m scripts.seed
python -m scripts.provision_runtime
docker compose --profile app up -d --build --wait api
```

### Windows (PowerShell)

Instalar Docker Desktop con WSL2 y activar contenedores Linux. No es necesario cambiar la política de ejecución de PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/init_env.py
docker compose up -d --wait db
docker compose ps
docker compose exec -T db pg_isready -U ecoconecta -d ecoconecta
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m scripts.seed
.\.venv\Scripts\python.exe -m scripts.provision_runtime
docker compose --profile app up -d --build --wait api
```

En Windows, en los siguientes comandos `python` significa `.\.venv\Scripts\python.exe`. La ruta Windows se documenta pero **no se ha probado en hardware Windows**.

`init_env.py` crea un archivo privado con contraseñas aleatorias; no sobrescribe uno existente ni imprime secretos. Alternativa: copiar `.env.example` a `.env` y completar los valores manualmente. No dejar `REEMPLAZAR`. Si cambias usuario, base o puerto, actualiza también ambas URLs. En Windows restringir ACL del archivo al usuario de desarrollo (chmod no sustituye ACL de NTFS).

API: <http://127.0.0.1:8000/docs>. Salud: <http://127.0.0.1:8000/health>. El healthcheck verifica una consulta real a PostgreSQL. El resto de rutas requiere token salvo login. No hay CORS abierto: el panel debe utilizar un proxy de desarrollo al mismo origen o configurar con Breiner una lista explícita de orígenes.

## Frontend y API

El frontend se puede ejecutar junto a la API mediante el perfil `app`:

```bash
docker compose --profile app up -d --build --wait api web
```

- Frontend: <http://127.0.0.1:5173>
- API: <http://127.0.0.1:8000>
- Las llamadas `/api/*` del frontend pasan por Nginx/Vite a FastAPI.
- Login real: `POST /auth/token`; el JWT se conserva solo en `sessionStorage`.

Para desarrollo sin Docker, inicia FastAPI en `8000` y Vite en `5173`; `vite.config.ts` hace el proxy `/api`.
En plataforma separada, define `VITE_API_URL=https://api.dominio.com` al compilar y agrega ese origen exacto a `CORS_ORIGINS`. En el despliegue detrás de un dominio común se recomienda mantener `/api` y no exponer PostgreSQL.

### Variables

| Variable | Uso |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER` | Base y propietario de migraciones; defaults `ecoconecta` |
| `POSTGRES_PASSWORD` | Secreto bootstrap local; obligatorio para iniciar PostgreSQL |
| `POSTGRES_PORT` | Puerto **127.0.0.1**, por defecto 5432 |
| `ADMINER_PORT` | Interfaz web opcional, solo **127.0.0.1**, por defecto 8080 |
| `DATABASE_URL` | URL SQLAlchemy `postgresql+psycopg://...`; herramientas administrativas locales |
| `TEST_DATABASE_URL` | Base exclusiva terminada en `_test`; las pruebas vacían sus tablas |
| `AUTH_SECRET` | Firma JWT HS256; mínimo 32 caracteres aleatorios |
| `TOKEN_MINUTES` | Expiración de sesión; default 30 |
| `DB_APP_USER`, `DB_APP_PASSWORD` | Rol limitado del servicio Docker API; provisionado por script, sin DDL/DELETE/TRUNCATE |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | Conexión interna de API; Compose la construye sin interpolar URL |

Las variables del proceso prevalecen sobre `.env`. `DATABASE_URL` prevalece sobre PG*. En las URLs locales, codificar caracteres reservados de contraseñas; el generador usa hexadecimal para evitar ese problema. No mostrar `docker compose config` completo en evidencia: puede incluir secretos; usar `docker compose config --quiet`.

La imagen de PostgreSQL solo aplica las variables iniciales cuando el volumen está vacío. Cambiar `.env` **no cambia** la contraseña de una base ya creada. La API usa un rol diferente del propietario. El script de provisión no rota contraseñas existentes y debe ejecutarse otra vez después de migraciones que incorporen tablas/secuencias nuevas.

## Ver las tablas desde el navegador

Se incluye [Adminer 6.3.0](https://hub.docker.com/_/adminer), una interfaz de administración PostgreSQL, como servicio opcional. No es el panel de coordinadores y no sustituye los permisos de FastAPI.

```bash
docker compose --profile tools up -d --wait adminer
```

Si tu Docker Engine usa el contexto `default`, ejecutar `docker --context default compose --profile tools up -d --wait adminer`.

Abrir <http://127.0.0.1:8080/?pgsql=db&username=ecoconecta&db=ecoconecta> e iniciar sesión:

| Campo | Valor por defecto |
|---|---|
| Sistema | PostgreSQL |
| Servidor | `db` (nombre interno Docker, **no** localhost) |
| Usuario | `ecoconecta` (`POSTGRES_USER`) |
| Contraseña | Valor local de `POSTGRES_PASSWORD` en `.env` |
| Base de datos | `ecoconecta` (`POSTGRES_DB`) |

Si modificaste variables, usar sus valores reales. Elegir el esquema `public`, pulsar una tabla (por ejemplo `solicitudes` o `colectivos`) y después **Seleccionar datos / Select data**. Se puede revisar estructura, relaciones y consultas SQL. Para ver los cierres y EcoPuntos ficticios, seleccionar la base `ecoconecta_test`; la principal conserva reglas DEMO sin aprobar.

La contraseña no se inserta en la URL ni se guarda en Compose. El acceso administrativo permite modificar y borrar: para explorar, usar **Seleccionar datos**, no las acciones de eliminación. Cambios de estructura deben seguir pasando por Alembic y operaciones de negocio por la API. No publicar este servicio en Internet ni entregar la cuenta de propietario a residentes/coordinadores. Adminer solo escucha en loopback y no se inicia con el perfil habitual de la API.

Para detener únicamente la interfaz, sin detener ni borrar la base:

```bash
docker compose --profile tools stop adminer
```

Si el puerto 8080 está ocupado, definir `ADMINER_PORT=8081` en `.env`, repetir el arranque y abrir el puerto nuevo.

## 3. Migraciones: una única fuente de verdad

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Las revisiones 0001 (DDL congelado), 0002 (reglas transaccionales) y 0003 (historial protegido) funcionan desde una base vacía. No existe `create_all`. El SQL junto a cada revisión forma parte de Alembic, no es un segundo esquema. No editar revisiones ya compartidas: generar una revisión nueva:

```bash
python -m alembic revision --autogenerate -m "descripcion del cambio"
```

Revisar el SQL y añadir a mano cambios en triggers: Alembic compara metadata/tablas/índices, no todas las funciones PL/pgSQL. Breiner debe reutilizar `backend.models.Base` y estas migraciones. Si aparece código externo, usar el [plan de conciliación](docs/arquitectura.md), no crear tablas duplicadas. `downgrade base` destruye las tablas; solo usar en una base vacía desechable, nunca como operación de respaldo.

## 4. Datos ficticios y dos flujos completos

```bash
python -m scripts.seed
python -m scripts.seed
```

El SQL exigido está en `database/seed_demo.sql`. Crea cinco usuarios DEMO, dos colectivos, dos integrantes, cuatro materiales, dos reglas **no aprobadas** y dos solicitudes programadas (`DEMO-ECO-REC`, `DEMO-ECO-ORG`). No contiene teléfonos ni domicilios reales. Identificadores `DEMO-WA-*` no son identidades verificadas de Meta. Las cuentas no tienen contraseña inicial. No enviar sus notificaciones: están marcadas como ficticias en el contenido.

No ejecutar el seed en una base con residentes reales. Los `ON CONFLICT` no sobrescriben registros existentes. No se acreditan puntos al cargar el seed ni se aprueban equivalencias automáticamente.

Para completar ambos flujos sin contaminar la base de desarrollo:

```bash
python -m scripts.create_test_db
python -m scripts.demo_complete
python -m scripts.demo_complete
```

El segundo comando migra `TEST_DATABASE_URL`, carga el seed, aprueba reglas **ficticias** como administrador DEMO y cierra ambas solicitudes en una transacción. Confirma 5 kg en cada flujo: 50 puntos reciclables y 25 orgánicos. No son valores oficiales. Al repetirlo no vuelve a acreditar. Si has alterado manualmente la vigencia de las reglas, usar una nueva base `_test` vacía; el script no cambia reglas aplicadas ni corrige silenciosamente datos históricos.

### Probar la API manualmente

```bash
python -m scripts.set_password
```

Elegir un correo DEMO existente, por ejemplo `residente.reciclaje@example.invalid`; establecer una contraseña local sin pasarla por línea de comandos. Repetir con `coordinador.reciclaje@example.invalid` para el panel. Login JSON en `POST /auth/token`; copiar el token en **Authorize** en Swagger. `GET /materiales` devuelve IDs reales; no asumir IDs fuera de una base vacía.

1. Residente: `POST /solicitudes`, con dirección ficticia y materiales confirmados del mismo flujo.
2. Coordinador de ese colectivo: `POST /solicitudes/{id}/asignacion` con `recolector_id`.
3. `POST /solicitudes/{id}/programacion` con `{"programada_en":"2030-01-15T09:00:00-05:00"}`.
4. `POST /solicitudes/{id}/cierre` con `{"peso_real_kg":"5.00"}`.
5. Consultar historial y saldo. En desarrollo con seed sin aprobación, el paso 4 devuelve **409 y revierte todo**, deliberadamente. Para validar puntos usar la base de demostración separada o una aprobación real documentada por el equipo.

No existe endpoint que permita a un residente aprobar reglas, habilitar su piloto, elegir el usuario actor o indicar otro colectivo para saltarse el enrutamiento.

## 5. Pruebas automatizadas

```bash
python -m scripts.create_test_db
python -m pytest -q
```

Las pruebas se ejecutan contra PostgreSQL real, no SQLite. Aplican Alembic y hacen TRUNCATE solo en la base `_test`, que debe ser distinta de `DATABASE_URL`; borran los datos de prueba al finalizar cada caso. No ejecutarlas sobre datos que necesites conservar. Cubren ambos flujos, persistencia, identidad WhatsApp, reintentos concurrentes, permisos, integridad, programación, peso, cierre concurrente, vigencia, rollback y puntos inmutables.

La suite deja la base de pruebas vacía; ejecutar después `demo_complete` para dejar ambos casos cerrados disponibles para inspección. Los tests de API usan TestClient con autenticación JWT real; la evidencia también distingue las comprobaciones del servidor HTTP Docker.

Comprobación adicional de ambos flujos usando el rol SQL limitado (crea dos solicitudes DEMO adicionales en `_test`):

```bash
python -m scripts.demo_complete
python -m scripts.provision_runtime --test
python -m scripts.smoke_runtime
```

## 6. Persistencia, backup y restauración

El volumen nombrado `postgres_data` persiste tras reiniciar/recrear el contenedor. `docker compose down` conserva el volumen; **no usar `down -v` sobre datos importantes**. `backups/` y `*.dump` están excluidos de Git.

Verificación automatizada (pausar escrituras mientras se comparan hashes):

```bash
python -m scripts.demo_complete
python -m scripts.verify_operations --database ecoconecta_test --restart
```

El script reinicia `db`, compara conteos/hashes de las 18 tablas y secuencias, crea un dump y lo restaura en una **base nueva** `ecoconecta_restore_<fecha>_<aleatorio>_test`. Verifica también la revisión Alembic. Conserva dump, informe local y base restaurada para inspección; no borra ninguna base. Usar `--context default` si corresponde al contexto Docker de tu máquina. Sin `--restart`, solo valida backup/restore. El reinicio afecta las conexiones de todos los servicios que usan ese contenedor; programarlo en una ventana de mantenimiento.

Respaldo manual, usando nombre de archivo nuevo para no sobrescribir uno anterior:

```bash
docker compose exec -T db pg_dump -U ecoconecta -d ecoconecta -Fc --no-owner --no-acl -f /tmp/ecoconecta_manual.dump
docker compose cp db:/tmp/ecoconecta_manual.dump ./ecoconecta_manual.dump
```

Restauración en una base **nueva**, sin `--clean` ni reemplazo de producción:

```bash
docker compose exec -T db createdb -U ecoconecta --template=template0 ecoconecta_manual_restore_test
docker compose cp ./ecoconecta_manual.dump db:/tmp/ecoconecta_manual_restore.dump
docker compose exec -T db pg_restore -U ecoconecta -d ecoconecta_manual_restore_test --no-owner --no-acl --exit-on-error /tmp/ecoconecta_manual_restore.dump
docker compose exec -T db psql -U ecoconecta -d ecoconecta_manual_restore_test -c "SELECT version_num FROM alembic_version; SELECT count(*) FROM solicitudes;"
```

Adaptar `-U`/`-d` si cambiaste los defaults. Si el destino ya existe, escoger otro nombre; no borrarlo para forzar el comando. Para recuperación real, validar integridad, conectar la API al destino y ejecutar un smoke test antes de conmutar tráfico. Los dumps contienen datos privados: cifrar y custodiar fuera de Git, controlar acceso y acordar retención/RPO/RTO. El backup no incluye roles/passwords (por `--no-owner --no-acl`); volver a provisionar el rol runtime tras restaurar.

## 7. Despliegue con Docker

El Compose entregado es de desarrollo, con API y PostgreSQL publicados solo en loopback. La comunicación API→DB utiliza la red `database` interna; DB tiene además `development` para que Docker pueda publicar el puerto local. API tiene `outbound` para futuras integraciones externas. No se montan fuentes, secretos ni respaldos dentro de la imagen.

Para un servidor del piloto:

1. Provisionar entorno separado y secretos únicos fuera de Git. No cargar seed ni reutilizar credenciales DEMO.
2. Construir la imagen; respaldar antes de actualizar; ejecutar Alembic como propietario en un paso administrativo. No ejecutar migraciones simultáneamente desde varias réplicas.
3. Provisionar rol runtime limitado y asignarlo a API. El propietario/bootstrap se reserva para migraciones, backups y administración. El rol runtime tiene lectura/operaciones necesarias y UPDATE de `id` para bloqueos de filas; **no** DDL, TRUNCATE, DELETE ni aprobación de reglas. No entregar credenciales SQL a residentes/coordinadores.
4. Retirar el mapeo de puerto de DB y su red `development` cuando no se necesite acceso local administrativo. Mantener la red interna. Añadir proxy TLS frente a la API, limitar intentos de login en el proxy y configurar CORS solo para el dominio autorizado.
5. Aprobar participantes y equivalencias con la Fundación, mediante operador autorizado. No hay panel administrativo aún; no editar saldos ni históricos manualmente.
6. Manuel integra verificación de firma Meta, remitente, IDs idempotentes, permisos de fotos y worker de outbox con reintentos. No exponer el helper de identidad como webhook sin esa verificación.
7. Monitorizar healthchecks, backups restaurables, espacio de disco y entregas fallidas. Revisar imágenes/dependencias fijadas antes de publicar. No hay despliegue público ejecutado en esta entrega.

## 8. Resolución de problemas

| Síntoma | Causa y solución |
|---|---|
| Docker no conecta / socket Desktop ausente | Iniciar Docker; `docker context ls`; si Engine vive en default, usar `docker --context default compose ...` sin cambiar configuración global |
| Permiso denegado en socket | Habilitar acceso Docker del usuario mediante el administrador; no hacer el socket escribible para todos |
| `connection refused` a 5432 | Ver `docker compose ps`; puerto debe mostrar `127.0.0.1:5432->5432/tcp`; una red solo interna no publica puertos en el entorno probado |
| Puerto ya ocupado | Cambiar POSTGRES_PORT y ambas URLs antes de arrancar; no detener un servicio ajeno |
| Error de contraseña | Revisar URL codificada, rol y variables del proceso; cambiar `.env` no rota contraseñas del volumen existente |
| API no inicia con rol runtime | Ejecutar migraciones y `scripts.provision_runtime`, luego recrear servicio API para recargar variables |
| `AUTH_SECRET` corto | Generar secreto aleatorio de 32+ caracteres; no pegar uno público del README |
| `409` al cerrar | Verificar programación, miembro activo y regla aprobada/vigente; todo el intento se revierte |
| `404` desde otro coordinador | Aislamiento intencional: no revelar la existencia de solicitudes ajenas |
| Alembic informa diferencias | Crear/revisar una migración, no usar `create_all` ni modificar tablas fuera de Alembic |
| Tests sin TEST_DATABASE_URL | Completar `.env`, crear base separada `_test`; no usar la base de trabajo |
| Seed falla por datos previos incompatibles | No forzar ON CONFLICT para sobreescribirlos; usar base DEMO vacía o conciliación con Breiner |
| Restore encuentra tablas existentes | Crear un destino nuevo vacío; no usar `--clean` contra la base principal |

## 9. Preparar pull request

Revisar [entrega](docs/entrega.md) y los archivos nuevos. `git check-ignore .env` debe confirmar exclusión. No añadir `.env`, dumps, datos de residentes ni tokens; no adjuntar logs que contengan parámetros SQL. Ejecutar tests y `alembic check`, revisar `git diff --check`, y abrir PR en el remoto del equipo. El checkout local inicialmente no tenía commits; el remoto configurado es `https://github.com/emmapadiila/ecoreciclar.git`. No se ha publicado un PR ni se ha inventado coordinación con Breiner.

---

## Instrucciones del frontend local

# EcoConecta 360

Frontend de demostración para conectar a la comunidad de Villas de San Pablo con los colectivos de recolección de residuos orgánicos y reciclables.

## Requisitos

- [Node.js](https://nodejs.org/) 20 o superior (recomendado: una versión LTS), que incluye npm.
- Una terminal y un navegador web.

Comprueba que Node.js y npm están instalados:

```bash
node --version
npm --version
```

## Instalación y servidor de desarrollo

1. Abre una terminal en la carpeta del proyecto:

   ```bash
   cd /home/yuno/Hackaton
   ```

   Si descargaste el proyecto en otra ubicación, utiliza la ruta correspondiente.

2. Instala las dependencias:

   ```bash
   npm install
   ```

3. Inicia el servidor del frontend:

   ```bash
   npm run dev
   ```

4. Abre la dirección que indique la terminal, normalmente [http://localhost:5173](http://localhost:5173). Si el puerto está ocupado, Vite mostrará otro.

Para detener el servidor, pulsa **Ctrl+C** en la terminal. Para iniciarlo de nuevo, ejecuta `npm run dev` desde la carpeta del proyecto; no necesitas repetir `npm install` salvo que cambien las dependencias.

El servidor escucha también en la red local. Si lo abres desde otro dispositivo, usa la dirección de red que Vite muestra en la terminal y asegúrate de que ambos dispositivos estén en la misma red.

## Explorar la demostración

Desde la página principal puedes crear y consultar solicitudes o entrar al acceso del equipo y elegir un perfil de demostración. Los datos ficticios se guardan en el navegador y se pueden restaurar desde la configuración de la aplicación.

El selector de perfiles y las verificaciones son simulados: **no introduzcas datos personales reales**. No constituyen autenticación ni protección de datos para producción.

## Compilación

Para generar los archivos de producción y comprobar la compilación:

```bash
npm run build
```

El resultado se guarda en `dist/`. Para probarlo localmente:

```bash
npm run preview
```

Abre la dirección que indique la terminal. El servidor de vista previa es para comprobación local, no para producción.

## Integraciones futuras

Por ahora no es necesario instalar FastAPI ni configurar WhatsApp, IA o PostgreSQL para ejecutar la demostración. Cuando el backend esté disponible, se podrá configurar `VITE_API_URL` usando `.env.example` como referencia. Las variables `VITE_` son visibles en el frontend y no deben contener secretos.

Consulta [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) para conocer el alcance y el contrato de API propuesto.
