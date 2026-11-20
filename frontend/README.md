# EcoConecta 360

### WhatsApp y resultados diarios

Configura `VITE_WHATSAPP_NUMBER` en `frontend/.env` con el número oficial en formato internacional, sin `+` ni espacios. Si no se configura, los botones permanecen deshabilitados. El texto precargado se abre en WhatsApp; este enlace no envía mensajes automáticamente. Reinicia Vite después de cambiar la variable. Con Docker Compose, configura la misma variable en el `.env` de la raíz y reconstruye la imagen web (`docker compose --profile app up -d --build web`): Vite incorpora la variable durante la compilación.

`/resultados-diarios` consulta `GET /api/public/resultados-diarios?fecha=AAAA-MM-DD`; el proxy elimina `/api` antes de enviar la petición a FastAPI. Se requieren FastAPI y PostgreSQL en ejecución. Los totales reflejan exclusivamente los datos de la base conectada: si contiene datos de prueba, el reporte también los mostrará. No se emplean datos locales como respaldo si la API falla.

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
   cd frontend
   ```

   Ejecuta este comando desde la raíz del repositorio.

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

### Operación con una cuenta registrada

Desde `/acceso`, el enlace **Acceder con una cuenta registrada** abre
`/acceso-registrado`. Los coordinadores gestionan las solicitudes de su
colectivo y los residentes consultan sus solicitudes y EcoPuntos en
`/operacion`. El selector demo sigue disponible con datos ficticios.

Para la operación real, FastAPI debe estar conectado a la base autorizada,
con Alembic en la revisión `0004` y los permisos del rol de ejecución
actualizados mediante `scripts.provision_runtime`. Configura una contraseña
para cada cuenta existente mediante `scripts.set_password`. Vite redirige
`/api` a FastAPI en `127.0.0.1:8000` durante el desarrollo.

El cierre requiere una regla de EcoPuntos aprobada y vigente. Los avisos de
programación y cierre quedan pendientes de envío en PostgreSQL.

Por ahora no es necesario instalar FastAPI ni configurar WhatsApp, IA o PostgreSQL para ejecutar la demostración. Cuando el backend esté disponible, se podrá configurar `VITE_API_URL` usando `.env.example` como referencia. Las variables `VITE_` son visibles en el frontend y no deben contener secretos.

Consulta [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) para conocer el alcance y el contrato de API propuesto.

## Estructura inicial del repositorio

# Frontend de EcoConecta 360

Estructura base para el panel React de coordinación del piloto.

| Carpeta | Contenido |
| --- | --- |
| `src/pages/` | Pantallas del panel, como el acceso y las solicitudes. |
| `src/components/` | Elementos de interfaz reutilizables. |
| `src/api/` | Cliente HTTP y llamadas a FastAPI. |

El [contrato de la API](../docs/arquitectura.md) documenta las rutas, los roles y la autenticación. Para el desarrollo local, el panel podrá acceder a FastAPI mediante un proxy del mismo origen hacia `http://127.0.0.1:8000`.
