"""Genera secretos locales; nunca sobrescribe un .env existente ni imprime secretos."""
import os
import secrets
from pathlib import Path


def main():
    password = secrets.token_hex(32)
    secret = secrets.token_hex(32)
    content = Path(".env.example").read_text(encoding="utf-8")
    content = content.replace("POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={password}\n")
    content = content.replace("AUTH_SECRET=\n", f"AUTH_SECRET={secret}\n")
    content = content.replace("REEMPLAZAR", password)
    fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(".env creado con valores aleatorios locales; no se muestran credenciales.")


if __name__ == "__main__":
    main()
