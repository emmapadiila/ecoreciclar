"""Verifica reinicio opcional y backup/restore sin sobrescribir bases existentes.

Requiere Docker, .env y ausencia de escrituras concurrentes durante la comparación.
Deja el dump y la base restaurada para inspección; no elimina volúmenes ni bases.
"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from backend.models import Base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", help="Contexto Docker opcional; no modifica el contexto global")
    parser.add_argument("--database", help="Base origen; por defecto POSTGRES_DB")
    parser.add_argument("--restart", action="store_true", help="Reinicia el contenedor db antes del backup")
    args = parser.parse_args()
    load_dotenv()
    source = args.database or os.getenv("POSTGRES_DB", "ecoconecta")
    user = os.getenv("POSTGRES_USER", "ecoconecta")
    compose = ["docker"] + (["--context", args.context] if args.context else []) + ["compose"]

    def run(*parts, capture=False):
        result = subprocess.run(compose + list(parts), check=True, text=True,
                                stdout=subprocess.PIPE if capture else None)
        return result.stdout.strip() if capture else None

    def query(db, sql):
        return run("exec", "-T", "db", "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", user,
                   "-d", db, "-At", "-c", sql, capture=True)

    def snapshot(db):
        tables = {}
        for table in sorted(Base.metadata.tables):
            # Los nombres provienen de metadata propia, no de entrada externa.
            result = query(
                db, f"SELECT count(*)::text || ':' || md5(coalesce(string_agg(row_to_json(t)::text, '|' ORDER BY id), '')) FROM \"{table}\" t")
            tables[table] = result
        tables["alembic_version"] = query(db, "SELECT version_num FROM alembic_version")
        tables["sequences"] = query(db, "SELECT sequencename || ':' || coalesce(last_value::text,'NULL') FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename")
        return tables

    before = snapshot(source)
    if args.restart:
        run("restart", "db")
        run("up", "-d", "--wait", "db")
        after_restart = snapshot(source)
        if before != after_restart:
            raise SystemExit("ERROR: el contenido cambió al reiniciar; revisar escrituras concurrentes")
        print("PASS: reinicio conserva contenido y secuencias de las 18 tablas")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    restore_db = "ecoconecta_restore_" + stamp.lower() + "_test"
    container_dump = "/tmp/ecoconecta_" + stamp + ".dump"
    Path("backups").mkdir(mode=0o700, exist_ok=True)
    local_dump = Path("backups") / ("ecoconecta_" + stamp + ".dump")
    run("exec", "-T", "db", "pg_dump", "-U", user, "-d", source, "-Fc", "--no-owner", "--no-acl", "-f", container_dump)
    run("cp", "db:" + container_dump, str(local_dump))
    local_dump.chmod(0o600)
    run("exec", "-T", "db", "createdb", "-U", user, "--template=template0", restore_db)
    run("exec", "-T", "db", "pg_restore", "-U", user, "-d", restore_db, "--no-owner", "--no-acl", "--exit-on-error", container_dump)
    restored = snapshot(restore_db)
    if before != restored:
        raise SystemExit("ERROR: restauración distinta; conservar artefactos para diagnóstico")
    # Solo hashes y conteos; no guarda nombres, teléfonos, direcciones ni mensajes.
    evidence = {"source": source, "restored_database": restore_db, "dump": str(local_dump),
                "restart_checked": args.restart, "verified_utc": stamp, "snapshots": restored}
    evidence_path = local_dump.with_suffix(".json")
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    evidence_path.chmod(0o600)
    print("PASS: backup/restore conserva contenido, secuencias y revisión Alembic")
    print("Respaldo local:", local_dump)
    print("Base restaurada conservada:", restore_db)


if __name__ == "__main__":
    main()
