"""Banco de pruebas local del webhook: NO es la app de producción.

Levanta un FastAPI mínimo con el mismo router que Breiner montará en main.py,
para que Manuel pueda probar el ciclo completo (firma, deduplicación, respuestas)
sin esperar el montaje en la app real y sin editar main.py por su cuenta.

Uso (venv activo, desde la raíz del repo):
    uvicorn scripts.app_whatsapp_dev:app --reload --port 8001
Luego prueba con:  python -m scripts.firma_payload_demo --verificar / --enviar
"""

from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from backend.conversacion import procesar_evento
from backend.ia_residuos import analizar_imagen
from backend.whatsapp import router as whatsapp_router

app = FastAPI(title="EcoConecta 360 - Webhook WhatsApp (solo desarrollo)")
app.state.procesar_evento = procesar_evento
app.state.analizar_imagen = analizar_imagen
app.include_router(whatsapp_router)
