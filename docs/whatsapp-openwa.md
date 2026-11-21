# Probar WhatsApp con EcoConecta

## Vincular el teléfono en la instalación local

Abre una terminal en la carpeta de este proyecto que contiene `compose.yaml` y el archivo privado `.env`. El despliegue local usa OpenWA 0.31.0, la sesión `ecoconecta`, FastAPI y el panel de la carpeta `frontend`.

1. Prepara una cuenta de WhatsApp para el bot y otra cuenta desde la que escribir como residente. Anota el número de la primera con indicativo de país.
2. Abre el [panel local de OpenWA](http://localhost:2785). Si pide la clave administrativa, consúltala en tu terminal con `docker compose exec openwa cat /app/data/.api-key`. Úsala en esa pantalla y mantenla privada.
3. En **Sessions**, abre `ecoconecta`. Inicia la sesión si está detenida y muestra el QR. En el teléfono del bot abre **WhatsApp → Dispositivos vinculados → Vincular un dispositivo** y escanéalo. Espera a que OpenWA muestre **ready**. Si caduca el QR, muestra uno nuevo.
4. En los webhooks de esa sesión, abre el que apunta a `http://api:8000/webhooks/openwa` y pulsa la acción de prueba. Debes obtener HTTP 200. Este evento verifica la conexión entre contenedores. El siguiente paso comprueba la entrega en WhatsApp.

## Registrar al residente

1. Desde la segunda cuenta, abre un **chat privado** con el número del bot. Envía `Hola`. Comprueba que la bienvenida y la pregunta por tu nombre aparecen en ese mismo hilo.
2. Envía tu nombre completo. Espera la siguiente pregunta y envía `Hogar`. Envía una dirección de recogida de prueba. Cuando aparezca el resumen, responde `1` para guardar el registro.
3. El registro confirmado se guarda en PostgreSQL y habilita al residente automáticamente. Desde el chat ya puede solicitar una recolección y consultar sus propios datos.
4. Si acabas de instalar el catálogo de demostración y necesitas establecer las contraseñas iniciales, ejecuta `python -m scripts.set_password` en la raíz con el entorno Python activado. El script pregunta por el correo y lee la contraseña de forma privada. Las cuentas del seed para este recorrido son `admin@example.invalid` y `coordinador.reciclaje@example.invalid`. Ejecútalo una vez por cuenta. En una instalación existente usa las credenciales de sus responsables.

## Crear una solicitud y comprobar el reenvío

Envía cada respuesta como mensaje separado y espera la pregunta siguiente.

1. Envía `Hola`, luego `1` para solicitar recolección y `2` para elegir reciclables.
2. Para probar por texto, elige `2` y selecciona **un solo** material reciclable del catálogo que muestra el bot. Para probar una foto, usa las instrucciones de la sección siguiente en este mismo punto.
3. Al ver **Revisa estos materiales**, responde `1` para continuar. Elige `1` para usar la dirección registrada. Envía `Tarde` y luego `omitir` para las observaciones.
4. Lee el resumen. Envía las palabras `confirmar solicitud` y guarda el código `ECO-…` que aparece en el chat.
5. Reenvía ese mismo texto al bot o escríbelo otra vez. Envía `2` desde el menú para consultar tus solicitudes. Debe aparecer una sola solicitud para este ensayo. Un reenvío manual tiene un ID nuevo. La prueba automatizada también entrega dos veces el mismo ID del webhook.
6. En el panel, inicia sesión como **coordinador de reciclaje** y abre **Solicitudes del colectivo**. Localiza el código del chat y abre su detalle. Verifica el material, la dirección y el horario. El administrador habilita usuarios y supervisa resultados. El coordinador consulta el detalle operativo de su colectivo.
7. Para corroborarlo en PostgreSQL, abre `docker compose exec db psql -U ecoconecta -d ecoconecta` (ajusta usuario y base si los personalizaste). Sustituye el número por el de la cuenta residente, solo dígitos, y compara el listado con el del paso anterior.

```sql
SELECT s.codigo, s.origen, s.estado
FROM solicitudes AS s JOIN usuarios AS u ON u.id = s.usuario_id
WHERE u.whatsapp_id = '573000000000' AND s.origen = 'whatsapp'
ORDER BY s.id DESC;
```

## Probar una foto con el reconocedor de Ángel

Puedes enviar una foto directamente al chat, incluso como primer mensaje. El bot resume si detectó residuos orgánicos, aprovechables o ambos. Para crear una solicitud, sigue los pasos del catálogo y confirma el material.

1. Consigue el endpoint de Ángel o arranca su proyecto `Hackaton_reci` con sus dependencias y pesos instalados. En ese proyecto, con su entorno Python activado, puedes arrancar el servicio en un puerto distinto al de EcoConecta con `ECO_LOCAL_MODELS=1 python -m uvicorn api.main:app --host 0.0.0.0 --port 8100`. Usa una red de confianza accesible desde el contenedor `api`. Los requisitos y los nombres de los pesos se describen en la [guía del reconocedor](integracion-ia-residuos.md).
2. En el `.env` de EcoConecta, define `ECO_IA_URL` con la URL completa, por ejemplo `http://IP_PRIVADA_DEL_EQUIPO:8100/api/ia/analizar-residuos`. Sustituye el nombre de ejemplo por la IP alcanzable del equipo que sirve los modelos. Aplica el cambio con `docker compose up -d --no-deps api`.
3. Desde el chat, inicia una solicitud, selecciona reciclables y elige `1` para enviar fotografía. Adjunta una foto nítida de un material del catálogo, como una botella PET, en JPEG, PNG o WebP de hasta 5 MiB. Envíala como **foto**.
4. Espera **Revisa estos materiales** y la lista de coincidencias. OpenWA descarga la imagen y entrega sus bytes en el webhook firmado. EcoConecta valida el formato y llama al adaptador de Ángel. Una sugerencia coincidente demuestra el retorno del resultado al chat. Si recibes la selección manual, verifica la URL, la disponibilidad de los pesos y si la detección coincide con el catálogo.
5. Responde `2` para corregir, selecciona el material correcto del catálogo y verifica la nueva lista. Responde `1` para aceptarla y completa la dirección, el horario y la confirmación final. Comprueba en el panel que figura el material elegido por el residente.

## Instalar en otro equipo

1. Sigue la instalación de PostgreSQL y las dependencias de Python en el [README](../README.md). En una base nueva, aplica las migraciones, carga el catálogo de prueba y ejecuta `python -m scripts.provision_runtime`. Ejecuta también `python -m scripts.provision_runtime --panel` para crear el login del panel con permiso para habilitar residentes.
2. Ejecuta `docker compose --profile openwa up -d --wait openwa`. Entra a OpenWA como se indica arriba y crea una sesión con nombre `ecoconecta`. Copia su **ID**.
3. En **API Keys** crea una clave de rol **operator** restringida a esa sesión. En el archivo privado `.env` configura `WHATSAPP_PROVIDER=openwa`, `OPENWA_URL=http://openwa:2785`, `OPENWA_SESSION_ID` con el ID y `OPENWA_API_KEY` con la clave de operador.
4. Genera el secreto de firma con `python -c "import secrets; print(secrets.token_hex(32))"`. Guarda el valor en `OPENWA_WEBHOOK_SECRET`. En la sesión de OpenWA, crea un webhook con URL `http://api:8000/webhooks/openwa`, evento `message.received` y el mismo valor en **Secret**. Si el gateway valida la URL al crearla, arranca primero la API con el comando del paso 5.
5. Si quieres que el botón público abra el chat del bot, configura `VITE_WHATSAPP_NUMBER` con su número internacional, solo dígitos. Ejecuta `docker compose --profile app --profile openwa up -d --build --wait`. Vuelve al primer apartado para vincular el teléfono. Los webhooks usan la red Docker privada del proyecto y el gateway conecta hacia WhatsApp.
6. Para repetir la verificación automatizada en una base de pruebas con sufijo `_test`, ejecuta `python -m scripts.create_test_db` y `python -m pytest -q`. La suite vacía esa base de pruebas. La prueba `test_openwa_foto_confirmacion_y_panel` usa PostgreSQL y los componentes reales de la aplicación con respuestas HTTP simuladas de OpenWA y del reconocedor.

Contrato del proveedor y autenticación de las entregas. [API oficial de OpenWA](https://github.com/rmyndharis/OpenWA/blob/main/docs/06-api-specification.md) · [Firma del webhook](https://github.com/rmyndharis/OpenWA/blob/main/docs/examples/webhook-signature-verification.md)
