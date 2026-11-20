"""Prueba el webhook de WhatsApp en local, sin Meta y sin red externa.

Firma un payload de ejemplo con META_APP_SECRET y lo manda al webhook de
desarrollo. Requiere META_APP_SECRET y WHATSAPP_VERIFY_TOKEN en .env (valores
locales de prueba; no necesitan ser los reales de Meta todavía).

Pasos (venv activo, desde la raíz del repo):
    uvicorn scripts.app_whatsapp_dev:app --port 8001      # terminal 1
    python -m scripts.firma_payload_demo --verificar      # terminal 2: GET esperado 200 'reto_demo'
    python -m scripts.firma_payload_demo --enviar         # 1a vez: {"nuevos": 1}
    python -m scripts.firma_payload_demo --enviar         # 2a vez: {"nuevos": 0}  <- T04 demostrada
Sin flags imprime el comando curl equivalente para inspección manual.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

URL_BASE = os.getenv("URL_WEBHOOK_DEV", "http://127.0.0.1:8001")
SECRETO = os.getenv("META_APP_SECRET", "")
TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "ENTRADA_DEMO",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "573000000000",
                            "phone_number_id": "TELEFONO_DEMO",
                        },
                        "contacts": [
                            {"profile": {"name": "Demo"}, "wa_id": "573001234567"}
                        ],
                        "messages": [
                            {
                                "from": "573001234567",
                                "id": "wamid.DEMO0001",
                                "timestamp": "1763700000",
                                "text": {"body": "Hola"},
                                "type": "text",
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


def _firma(cuerpo: bytes) -> str:
    return (
        "sha256="
        + hmac.new(SECRETO.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba local del webhook WhatsApp")
    parser.add_argument(
        "--verificar", action="store_true", help="prueba el GET de verificación"
    )
    parser.add_argument(
        "--enviar", action="store_true", help="envía el POST firmado al webhook local"
    )
    args = parser.parse_args()

    if not SECRETO:
        sys.exit(
            "META_APP_SECRET no está en .env; agrega un valor local de prueba "
            "(por ejemplo: openssl rand -hex 16)."
        )
    cuerpo = json.dumps(PAYLOAD, separators=(",", ":")).encode("utf-8")

    if args.verificar:
        respuesta = httpx.get(
            f"{URL_BASE}/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": TOKEN,
                "hub.challenge": "reto_demo",
            },
        )
        print(f"[GET] {respuesta.status_code} -> {respuesta.text!r}")
        print(
            "Esperado: 200 y 'reto_demo'. Un 403 indica token distinto entre .env y la petición."
        )
        return

    if args.enviar:
        respuesta = httpx.post(
            f"{URL_BASE}/webhooks/whatsapp",
            content=cuerpo,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _firma(cuerpo),
            },
        )
        print(f"[POST] {respuesta.status_code} -> {respuesta.text}")
        return

    print("Comando curl equivalente:")
    print(
        f"curl -X POST {URL_BASE}/webhooks/whatsapp "
        f"-H 'Content-Type: application/json' "
        f'-H "X-Hub-Signature-256: {_firma(cuerpo)}" '
        f"--data-binary '{cuerpo.decode()}'"
    )


if __name__ == "__main__":
    main()
