# Chatbot conversacional de EcoConecta 360

El módulo usa el FastAPI y PostgreSQL existentes. El transporte identifica al remitente con el WhatsApp verificado, obtiene el usuario y la conversación mediante `register_verified_message()` y llama a `backend.conversacion.procesar_evento`. El módulo devuelve una lista de textos y participa en la transacción del llamador.

## Estados y transiciones

| Estado persistido | Entrada y transición |
| --- | --- |
| `inicio`, `menu` | Reconoce la cuenta. Un registro incompleto abre el alta. Una cuenta registrada puede elegir recolección, solicitudes, puntos, consejos o actualizar dirección. |
| `registro_nombre`, `registro_perfil`, `registro_direccion`, `registro_confirmacion` | Valida nombre, hogar/negocio y dirección. Persiste el perfil tras confirmación. La administración conserva el control de `piloto_habilitado`. |
| `actualizar_direccion`, `actualizar_confirmacion` | Captura y confirma una nueva dirección habitual. |
| `tipo`, `metodo`, `espera_imagen` | Selecciona un tipo preliminar y permite foto o texto. Una persona habilitada también puede empezar con «Tengo …». |
| `materiales`, `revision_material` | Propone coincidencias del catálogo activo. Presenta opciones numeradas ante ambigüedad y exige confirmación humana tanto para texto como para IA. |
| `direccion`, `direccion_nueva`, `horario`, `observaciones` | Usa una dirección registrada o captura otra para esa solicitud. El horario es una preferencia. |
| `confirmacion`, `editar` | Presenta el resumen. Permite editar materiales, dirección, horario u observaciones. Solo la confirmación final guarda solicitudes. |
| Consultas desde `menu` | Devuelve hasta cinco solicitudes recientes del usuario o su saldo real y permanece en el menú. |

`cancelar` descarta el borrador antes del alta de solicitudes. `menú` descarta el borrador y vuelve al inicio o menú según el registro. La cancelación operativa de una solicitud ya guardada corresponde al flujo existente del coordinador.

## PostgreSQL y deduplicación

Se guardan solo datos necesarios en `conversaciones.datos_temporales`. El borrador vence después de 24 horas sin mensajes y se elimina al procesar el siguiente evento, cancelar o finalizar. Para eliminar físicamente los borradores de conversaciones abandonadas hace falta una tarea periódica del responsable de infraestructura. La caducidad del borrador es independiente de la retención de mensajes y notificaciones que administra el transporte.

Al confirmar, el módulo vuelve a consultar materiales activos y aceptados. Divide por categoría, construye DTOs locales compatibles con `create_request()` y llama a ese servicio con `origin="whatsapp"`. Usa un punto de guardado para que un error en cualquiera de los colectivos revierta todo el lote. El servicio elige el colectivo, persiste las solicitudes y genera los códigos reales. El panel recupera esas filas mediante su consulta autorizada existente. Los movimientos de puntos se leen de PostgreSQL y el cierre sigue siendo responsabilidad del coordinador.

La unidad de idempotencia es el `meta_message_id` verificado. El transporte actual bloquea el mensaje y la conversación, comprueba `estado_procesamiento`, encola las respuestas y marca el mensaje procesado en la misma transacción que la creación. Los consumidores alternativos deben mantener ese mismo límite transaccional y rechazar reentregas procesadas antes de invocar el módulo.

## Integración de Manuel

En el punto de composición que mantenga el responsable de FastAPI, registrar el procesador antes de aceptar tráfico. El webhook ya consulta este atributo.

```python
from backend.conversacion import procesar_evento

app.state.procesar_evento = procesar_evento
```

Conservar `_procesar_registrado()`, `procesar_mensaje()` y el transporte de salida actuales. El ensayo de integración usa el endpoint firmado con datos ficticios y sustituye el despacho externo. En la configuración de la aplicación el procesador predeterminado todavía es el stub del transporte.

### Permisos de Ángel

El rol de ejecución actualmente solo tiene permiso de actualización sobre `usuarios.id`. Antes de activar el registro deben concederse los permisos de columna mínimos al rol real de la aplicación desde el proceso de provisión administrado por Ángel.

```sql
GRANT UPDATE (nombre, tipo_generador, direccion) ON usuarios TO ecoconecta_app;
```

Sustituir el rol de ejemplo por el configurado. Mantener los permisos de habilitación del piloto, roles y contraseñas bajo el control existente. Para este módulo no se necesitan tablas ni migraciones.

## Integración de IA

El webhook descarga la fotografía y admite `app.state.analizar_imagen`. El adaptador de Ángel debe aceptar `(datos, mime_type, descripcion="", referencia=None)`. El transporte actual pasa bytes y MIME, y adjunta el diccionario resultante a `MensajeEntrante.analisis_imagen` del mismo evento. El chatbot acepta resultados síncronos con `estado="completado"` y vincula cada sugerencia al catálogo mediante categoría y nombre o material. Una respuesta ausente, inválida o sin coincidencias ofrece clasificación manual. Las pruebas usan diccionarios ficticios.

Configurar un tiempo límite en el adaptador y devolver un resultado con `estado="error"` ante fallos de disponibilidad. Si el adaptador propaga una excepción, el transporte actual solicita un reintento antes de llegar al chatbot. El contrato de error permite ofrecer el camino manual en ese mismo turno.

Si se adopta análisis asíncrono, coordinar antes un contrato que vincule resultado, ID de mensaje de imagen, conversación y versión del borrador. El procesador actual consume únicamente el resultado suministrado junto con el evento de imagen.

## Verificación

Configurar `TEST_DATABASE_URL` para una base desechable terminada en `_test`, distinta de `DATABASE_URL`, y establecer `AUTH_SECRET` local. El fixture de pruebas migra, carga datos ficticios y vacía las tablas entre casos.

```shell
python -m pytest -q tests/test_conversacion.py tests/test_solicitudes_whatsapp.py
python -m pytest -q
git status --short --branch
git diff --check
```
