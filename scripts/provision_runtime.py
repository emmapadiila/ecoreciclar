"""Crea un rol de aplicación no propietario. Ejecutar después de Alembic como DBA.

Genera contraseña local si falta y la conserva en .env, nunca en stdout.
No gira credenciales existentes ni concede DDL, DELETE o TRUNCATE.
"""
import argparse
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv, set_key
from psycopg import connect, sql
from sqlalchemy.engine import make_url
from backend.db import database_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Provisionar permisos en TEST_DATABASE_URL")
    args = parser.parse_args()
    load_dotenv()
    url = os.environ["TEST_DATABASE_URL"] if args.test else database_url()
    url = make_url(url) if isinstance(url, str) else url
    if args.test and not url.database.endswith("_test"):
        raise SystemExit("La base de pruebas debe terminar en _test")
    role = os.getenv("DB_APP_USER", "ecoconecta_app")
    if role == url.username or role in ("postgres", "public"):
        raise SystemExit("El rol runtime debe ser distinto del propietario y de roles reservados")
    password = os.getenv("DB_APP_PASSWORD")
    with connect(host=url.host, port=url.port, user=url.username, password=url.password, dbname=url.database) as conn:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
        if exists and not password:
            raise SystemExit("Rol existente: configure DB_APP_PASSWORD; no se rota automáticamente")
        if not password:
            password = secrets.token_hex(32)
            set_key(".env", "DB_APP_USER", role)
            set_key(".env", "DB_APP_PASSWORD", password)
            Path(".env").chmod(0o600)
        identifier = sql.Identifier(role)
        if not exists:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION").format(identifier, sql.Literal(password)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(url.database), identifier))
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(identifier))
        conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(identifier))
        conn.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(identifier))
        conn.execute(sql.SQL("GRANT INSERT ON usuarios, conversaciones, mensajes_whatsapp, solicitudes, solicitud_materiales, asignaciones, recolecciones, movimientos_puntos, historial_estados, notificaciones, clasificaciones_ia TO {}").format(identifier))
        conn.execute(sql.SQL("GRANT UPDATE ON solicitudes, solicitud_materiales, asignaciones, conversaciones, mensajes_whatsapp, notificaciones TO {}").format(identifier))
        conn.execute(sql.SQL("GRANT INSERT ON eventos_solicitud TO {}").format(identifier))
        # SELECT FOR SHARE requiere también algún permiso UPDATE en tablas consultadas.
        conn.execute(sql.SQL("GRANT UPDATE(id) ON usuarios, colectivos, coordinadores_colectivo, recolectores, materiales, reglas_puntos TO {}").format(identifier))
    print("Rol runtime provisionado sin privilegios de propietario; secretos conservados solo en .env")


if __name__ == "__main__":
    main()
