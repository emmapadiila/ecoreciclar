# WhatsApp de EcoConecta 360

## Conectar el número de prueba

1. En Meta for Developers, abre WhatsApp → Configuración de la API. Selecciona el número de prueba, añade y verifica un destinatario de prueba autorizado y copia el **ID del número emisor** a `WHATSAPP_PHONE_NUMBER_ID`. Inyecta el token de acceso en `WHATSAPP_ACCESS_TOKEN`. El permiso de mensajería es `whatsapp_business_messaging`. Para administrar la WABA, suscripciones y plantillas se usa `whatsapp_business_management`. Comprueba en el panel los permisos concedidos, el activo asignado y la caducidad del token de prueba. [Colección oficial de Meta](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api)
2. Configura `META_APP_SECRET` con el secreto de esa aplicación. Genera un valor aleatorio independiente para `WHATSAPP_VERIFY_TOKEN`. Entrega estos valores únicamente al proceso backend por el gestor de secretos o el entorno privado. La versión fijada en el ejemplo es `v25.0`, publicada el 18 de febrero de 2026 y con soporte anunciado hasta el 29 de julio de 2028. [Versiones de Graph API](https://developers.facebook.com/docs/graph-api/changelog/versions/)
3. Con el esquema actualizado hasta Alembic `0005`, expón el router de la API en HTTPS. En Webhooks configura `https://<dominio>/webhooks/whatsapp`, introduce el mismo verify token, suscribe el campo `messages` y verifica que la aplicación esté suscrita a la WABA del número de prueba. Desactiva los access logs con query strings en el proxy y Uvicorn (`--no-access-log`), y evita trazas HTTP detalladas en el transporte de medios. El GET de verificación contiene el token en la URL. [Configuración y suscripciones](https://www.postman.com/meta/whatsapp-business-platform/collection/wlk6lh4/whatsapp-cloud-api)
4. Desde el teléfono autorizado, escribe «Hola» al número de prueba. Verifica la recepción del menú en el dispositivo y contrasta la fila saliente con los recibos firmados para ese WAMID. Una respuesta HTTP exitosa de Graph acredita aceptación. El recibo `delivered` acredita entrega y `read` acredita lectura. El script `scripts/firma_payload_demo.py` genera eventos sintéticos para desarrollo.

## Ejecutar las notificaciones

Ejecuta `python -m backend.notificaciones_whatsapp` desde la raíz con el mismo entorno de base de datos y Meta que la API. En Compose, el comando equivalente es `docker compose exec -T api python -m backend.notificaciones_whatsapp`. Cada ejecución toma hasta 100 notificaciones elegibles. Programa el comando periódicamente, por ejemplo cada minuto. El webhook intenta despachar sus propias respuestas después de confirmar el procesamiento. El comando periódico también recupera las respuestas pendientes si el proceso cae entre commit y despacho.

Dentro de las 24 horas siguientes al timestamp firmado del último mensaje del usuario se admite texto libre. Fuera de esa ventana, o sin timestamp conocido, se exige una plantilla aprobada para el tipo de notificación. Configura el nombre exacto en `WHATSAPP_TEMPLATE_PROGRAMACION`, `WHATSAPP_TEMPLATE_CIERRE` o `WHATSAPP_TEMPLATE_RESPUESTA`, y su idioma en `WHATSAPP_TEMPLATE_LANGUAGE`. Este adaptador admite plantillas estáticas sin variables. Si falta la configuración, la auditoría registra `requiere_plantilla`. La aprobación y el consentimiento se verifican en la cuenta del piloto. [Política de mensajería de WhatsApp](https://business.whatsapp.com/policy) y [estados de plantillas](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account/message_templates/)

Para revisión de despliegue en Compose se propone pasar esas cuatro variables opcionales al servicio API, configurar la ejecución periódica y suprimir query strings en los registros de acceso. El Compose existente ya pasa las cinco variables obligatorias.

## Auditoría y recuperación

Cada notificación tiene un contador y cada intento genera una fila saliente con `notificacion_id`. La reserva se confirma antes del POST. El identificador de correlación viaja en `biz_opaque_callback_data`, lo que permite reconciliar un recibo que llega antes de la respuesta HTTP. Al aceptar el envío se guarda el WAMID en `meta_message_id`. Una entrega o lectura no retrocede por un recibo anterior.

Los errores de conexión previos a transmitir y HTTP 429 permiten hasta tres intentos totales, con esperas mínimas de 30 y 60 segundos. Un timeout de lectura, una caída tras reservar o una respuesta ambigua dejan la notificación `incierta`. Reconciliar el recibo antes de decidir manualmente un reenvío evita duplicar mensajes. Sin recibo puede ser imposible determinar el resultado. La consulta siguiente permite revisar intentos sin extraer teléfonos ni conversaciones.

```sql
SELECT n.id, n.estado, n.intentos, n.proximo_intento, m.estado_envio, m.error_envio
FROM notificaciones AS n
LEFT JOIN mensajes_whatsapp AS m ON m.notificacion_id = n.id
WHERE n.canal = 'whatsapp'
ORDER BY n.id DESC, m.id DESC;
```

## Contratos del equipo

La aplicación puede inyectar `app.state.procesar_evento(session, usuario, conversacion, evento) -> list[str]` y `app.state.analizar_imagen(datos: bytes, mime: str)`. Son funciones síncronas. El adaptador pasa el resultado de análisis intacto en `evento.analisis_imagen`. La descarga y el análisis tienen lugar fuera de la transacción SQL. Las imágenes permanecen en memoria. Mientras falte el analizador se conserva la respuesta existente sobre fotos. El stub del chatbot usa `responder()`. Los efectos de negocio del chatbot y sus notificaciones se confirman juntos. Ante una excepción se revierte el procesamiento y se devuelve 503 para que Meta repita el webhook firmado.

Las pruebas usan la base PostgreSQL de pruebas ya provisionada y simulan el proveedor HTTP. Para ejecutarlas dentro del entorno virtual:

```sh
python -m pytest tests/test_whatsapp.py -v --tb=short
python -m pytest -q --tb=short
```
