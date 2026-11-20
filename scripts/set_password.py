"""Alta manual de contraseña de una cuenta existente, sin contraseñas en argumentos."""
from getpass import getpass
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.auth import hash_password
from backend.db import engine
from backend.models import Usuario


def main():
    email = input("Correo de cuenta existente: ").strip().lower()
    password = getpass("Contraseña (mínimo 12 caracteres): ")
    if len(password) < 12 or password != getpass("Repetir contraseña: "):
        raise SystemExit("Contraseña corta o confirmación diferente")
    with Session(engine()) as session, session.begin():
        user = session.scalar(select(Usuario).where(Usuario.correo == email))
        if user is None:
            raise SystemExit("La cuenta no existe; no se crea ni autoriza automáticamente")
        user.password_hash = hash_password(password)
    print("Hash actualizado; contraseña no mostrada.")


if __name__ == "__main__":
    main()
