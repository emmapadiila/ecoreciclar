# Frontend de EcoConecta 360

Estructura base para el panel React de coordinación del piloto.

| Carpeta | Contenido |
| --- | --- |
| `src/pages/` | Pantallas del panel, como el acceso y las solicitudes. |
| `src/components/` | Elementos de interfaz reutilizables. |
| `src/api/` | Cliente HTTP y llamadas a FastAPI. |

El [contrato de la API](../docs/arquitectura.md) documenta las rutas, los roles y la autenticación. Para el desarrollo local, el panel podrá acceder a FastAPI mediante un proxy del mismo origen hacia `http://127.0.0.1:8000`.
