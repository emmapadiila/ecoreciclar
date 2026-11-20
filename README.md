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
