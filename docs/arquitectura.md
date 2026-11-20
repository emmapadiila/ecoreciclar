# EcoConecta 360: documentación de la demostración

## Ejecutar

```bash
npm install
npm run dev
npm run build
```

## Alcance y límites

Esta es una aplicación frontend de demostración. Los datos ficticios se comparten entre pantallas y se guardan en `localStorage` del navegador. Se pueden restaurar desde Configuración. No se deben ingresar datos personales reales. El selector de perfiles no autentica ni autoriza; el filtrado en cliente no protege información. El backend deberá imponer autenticación, autorización por colectivo y verificación de acceso de residentes.

El recorrido implementado crea solicitudes, filtra por colectivo, permite revisión, asignación, programación y cierre con peso positivo. El cierre otorga una regla ficticia de 10 puntos/kg; debe validarse con la Fundación. El cierre duplicado está bloqueado en la interfaz. Indicadores de peso usan únicamente recolecciones confirmadas. Solicitudes, seguimiento, calendario, movimientos y métricas leen el mismo estado local.

WhatsApp, inteligencia artificial real, verificación de identidad real, persistencia PostgreSQL y notificaciones externas **no están integrados**. El asistente y la clasificación por foto son simulaciones. Las herramientas de administración, calendario y reglas trabajan con datos locales y deben conectarse y validarse contra el backend antes de usarse en producción. El perfil Fundación muestra información agregada en indicadores; en un producto real el servidor debe limitar los datos entregados a este perfil.

## Contrato propuesto con FastAPI

Configurar `VITE_API_URL` en el entorno de Vite cuando exista el backend. Las rutas propuestas, aún no conectadas, son:

- `POST /api/solicitudes`
- `GET /api/solicitudes`
- `GET /api/solicitudes/:id`
- `PATCH /api/solicitudes/:id/asignar`
- `PATCH /api/solicitudes/:id/programar`
- `POST /api/solicitudes/:id/confirmar`
- `GET /api/usuarios/me/puntos`
- `GET /api/dashboard/indicadores`

No incluir secretos en variables `VITE_`: son públicas. El servidor debe validar transiciones, pertenencia al colectivo, pesos, puntos, idempotencia, historial y permisos. También debe implementar consentimiento, retención y protección de datos personales.
