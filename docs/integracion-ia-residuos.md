# Integración del reconocedor con EcoConecta 360

## Auditoría

El webhook de `ecoreciclar` ya descarga fotos y consulta `app.state.analizar_imagen` antes de invocar el procesador conversacional. La conversación de Emma acepta los elementos de `residuos` cuando `estado` es `completado` y resuelve el material por nombre o descripción contra el catálogo de PostgreSQL. FastAPI registra ambos componentes en `backend/main.py`. La [guía de OpenWA](whatsapp-openwa.md) detalla la prueba en WhatsApp.

El checkout local de `Hackaton_reci` en `d9f1bc0` implementa `POST /api/ia/analizar-residuos` en `api/main.py`. El análisis combina cajas, clasificación binaria, comprobación de fondo y material contextual en `api/residuos.py` y `api/vision_contextual.py`. El adaptador llama solo a ese endpoint. Toda creación de solicitudes sigue el servicio de negocio de EcoConecta.

| Modelo | Disponibilidad y uso |
| --- | --- |
| YOLOv8n de residuos | `models/ecoconecta_yolo.pt`, 6,45 MB. Propone candidatos. El informe guardado registra 21,58 % mAP@0,50 y 21,78 % de exhaustividad para el detector piloto. |
| MobileNetV2 | `models/ecoconecta_classifier.keras`, 9,67 MB. Clasificación binaria. El informe de entrenamiento registra 88,78 % de exactitud en su conjunto de fotos completas. |
| YOLOv8n contextual | `models/yolov8n.pt`, 6,55 MB. Comprobación adicional de objetos si el archivo existe. |
| CLIP ViT-B/32 contextual | `models/clip_vision_q8.onnx`, 89,12 MB. ONNX Runtime en CPU. Usa vectores de materiales y fondos. Este archivo es obligatorio para la ruta automática. |
| CLIP y OWL-ViT en navegador | Implementaciones del Web Worker de `Hackaton_reci`. Quedan fuera del endpoint consumido por WhatsApp. |
| CNN de entrenamiento | `models/cnn.keras`, 65,15 MB. Existe como candidato de entrenamiento. El clasificador de servidor seleccionado es MobileNetV2. |

El reconocedor usa las dependencias de sus propios `requirements.txt`, `requirements-yolo.txt` y `requirements-contexto.txt`. El adaptador solo usa HTTPX y Pydantic disponibles en EcoConecta. Los indicadores guardados corresponden a configuraciones y conjuntos de evaluación concretos. La precisión del flujo completo en fotografías del piloto sigue por medir.

## Contrato y activación

Configurar en el proceso de FastAPI de EcoConecta:

- `ECO_IA_URL` con la URL completa del endpoint, por ejemplo `http://reconocedor:8000/api/ia/analizar-residuos` en una red privada.
- `ECO_IA_TIMEOUT` en segundos. El valor predeterminado es 15 y el máximo admitido es 60.

El reconocedor debe tener sus pesos locales habilitados con `ECO_LOCAL_MODELS=1` y los artefactos accesibles. Arrancar y calentar el reconocedor antes del ensayo. El primer uso puede tardar más que el límite HTTP. Un plazo vencido libera la espera en el webhook. El cómputo ya iniciado en el proceso remoto puede continuar.

El punto de composición registra ambos componentes de esta forma.

```python
from backend.conversacion import procesar_evento
from backend.ia_residuos import analizar_imagen

app.state.procesar_evento = procesar_evento
app.state.analizar_imagen = analizar_imagen
```

El adaptador síncrono recibe `(datos, mime_type, descripcion="", referencia=None)`. Valida firma de archivo, MIME JPEG/PNG/WebP y tamaño de hasta 10 MiB. El reconocedor valida decodificación y dimensiones de hasta 24 megapíxeles. La petición multipart usa `imagen`, `descripcion` y `referencia`. La respuesta JSON tiene un límite de 128 KiB. La URL se configura en el servidor y la petición se detiene ante redirecciones.

| Campo | Semántica |
| --- | --- |
| `analisis_id` | Identificador del reconocedor o `null` si falla. |
| `estado` | `completado` para resultados válidos, incluso si están vacíos. `error` si falla la validación, el servicio, la inferencia o el plazo. |
| `residuos[]` | `id` de objeto, `nombre`, `material`, `categoria`, `colectivo_sugerido`, `requiere_revision` y `recomendacion`. La confirmación humana es obligatoria. |
| `categoria` | `organico`, `reciclable`, `otro` o `null`. `aprovechable` se normaliza a `reciclable` según el contrato del reconocedor. `no_aprovechable` pasa a `otro`. Una categoría desconocida queda pendiente de clasificación. |
| `advertencias`, `resumen` | Mensajes acotados y conteos calculados a partir de las categorías normalizadas. |

«Plástico de botella» se normaliza a «Botella plástica» para la búsqueda conversacional. Una detección genérica «Botella» con material desconocido conserva esa incertidumbre. El adaptador no emite identificadores del catálogo. Si el resultado no contiene coincidencias aceptadas, el chatbot ofrece selección por texto.

## PostgreSQL y responsables

`scripts/provision_runtime.py` concede al rol configurado mediante `DB_APP_USER` permiso de actualización de `usuarios.nombre`, `tipo_generador` y `direccion`. El valor predeterminado es `ecoconecta_app`. El permiso previo de `usuarios.id` ya existía. Los campos de autorización, rol y credenciales quedan fuera del nuevo permiso. En este diseño el control por usuario corresponde al webhook y su vínculo con la conversación, mientras PostgreSQL restringe columnas.

En un entorno de pruebas autorizado, utilizar `python -m scripts.provision_runtime --test`. Los permisos de la base del piloto deben revisarse y aplicarse por su responsable. El cambio se reproduce desde el provisionamiento y no precisa una migración.

El ensayo con teléfonos comienza con un mensaje de texto y continúa con una foto. Emma conserva la validación del catálogo y la confirmación del residente. El servicio de negocio asigna el colectivo y el panel consulta las solicitudes autorizadas por el mismo endpoint existente.

## Comprobación

Usar un `TEST_DATABASE_URL` aislado con sufijo `_test` y un administrador del clúster de pruebas para el caso de permisos. El test crea y limpia un rol efímero.

```shell
python -m pytest tests/test_ia_residuos.py -v
python -m pytest -q
```

Para repetir la prueba del webhook firmado con inferencia real, definir `ECO_IA_TEST_URL` y `ECO_IA_TEST_PHOTO` con el endpoint privado y la ruta de la foto de validación `botellas-mesa.jpg`. Ejecutar `python -m pytest tests/test_ia_residuos.py -k webhook -v`. El despacho y la descarga de Meta siguen sustituidos por dobles de prueba.

El ensayo local con pesos reales observó 2,14–4,72 segundos en muestras nítidas tras la carga inicial, 0,10 segundos en una foto borrosa y 1.144 MiB de memoria residente máxima del proceso. Una botella individual devolvió un único reciclable con material sin determinar. Tres botellas sobre una mesa devolvieron tres sugerencias reciclables. La cáscara produjo un orgánico y un objeto dudoso. Pared y foto borrosa devolvieron cero residuos. El primer intento en frío venció a los 60 segundos y el siguiente terminó en 58,62 segundos mientras el servicio finalizaba su calentamiento.

La repetición con el adaptador final procesó las botellas en 4,86 segundos y rechazó un JPEG corrupto. El ensayo con webhook firmado, rol SQL limitado y esa foto de validación confirmó el alta de una solicitud reciclable. También verificó una solicitud orgánica por texto y el acceso por el endpoint que consume cada panel de coordinación.
