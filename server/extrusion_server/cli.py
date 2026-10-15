"""Administración desde la terminal del servidor.

    python -m extrusion_server.cli crear-clave "Ingeniería" --rol viewer
    python -m extrusion_server.cli crear-clave "Administrador" --rol admin
    python -m extrusion_server.cli lineas
    python -m extrusion_server.cli clave-linea L01          # clave nueva para una línea (la anterior deja de servir)
    python -m extrusion_server.cli desactivar-linea L01
    python -m extrusion_server.cli revocar-clave 3

Con Docker:  docker compose exec api python -m extrusion_server.cli lineas
"""
from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import insert, select, update

from .app import Settings, hash_token, new_token
from .db import api_keys, lines, make_engine, purge


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="extrusion_server.cli", description="Administración del servidor")
    sub = p.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("crear-clave", help="clave para leer (viewer) o administrar (admin)")
    k.add_argument("nombre")
    k.add_argument("--rol", choices=["viewer", "admin"], default="viewer")
    sub.add_parser("claves", help="lista las claves")
    r = sub.add_parser("revocar-clave")
    r.add_argument("id", type=int)
    sub.add_parser("lineas", help="lista las líneas registradas")
    t = sub.add_parser("clave-linea", help="genera una clave nueva para una línea")
    t.add_argument("line_id")
    d = sub.add_parser("desactivar-linea")
    d.add_argument("line_id")
    sub.add_parser("limpiar", help="borra lo que pasa la retención")
    a = p.parse_args(argv)
    st = Settings.from_env()
    eng = make_engine(st.database_url)
    now = time.time()
    if a.cmd == "crear-clave":
        token = new_token("vw" if a.rol == "viewer" else "ad")
        with eng.begin() as c:
            c.execute(insert(api_keys).values(name=a.nombre, role=a.rol, token_hash=hash_token(token), created=now,
                                              revoked=False))
        print(f"Clave {a.rol} para «{a.nombre}» (guárdala: no se vuelve a mostrar):\n{token}")
    elif a.cmd == "claves":
        with eng.connect() as c:
            for row in c.execute(select(api_keys).order_by(api_keys.c.id)).mappings():
                state = "revocada" if row["revoked"] else "activa"
                print(f"{row['id']:>4}  {row['role']:<7} {state:<9} {row['name']}")
    elif a.cmd == "revocar-clave":
        with eng.begin() as c:
            n = c.execute(update(api_keys).where(api_keys.c.id == a.id).values(revoked=True)).rowcount
        print("Clave revocada" if n else "No existe esa clave")
    elif a.cmd == "lineas":
        with eng.connect() as c:
            for row in c.execute(select(lines).order_by(lines.c.area, lines.c.id)).mappings():
                seen = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["last_seen"])) if row["last_seen"] \
                    else "nunca"
                flag = "" if row["enabled"] else " (desactivada)"
                print(f"{row['id']:<20} {row['area'] or '-':<15} {row['name']:<30} último envío: {seen}"
                      f" · v{row['app_version'] or '?'}{flag}")
    elif a.cmd == "clave-linea":
        token = new_token("ln")
        with eng.begin() as c:
            n = c.execute(update(lines).where(lines.c.id == a.line_id)
                          .values(token_hash=hash_token(token), enabled=True)).rowcount
        if not n:
            print("No existe esa línea", file=sys.stderr)
            return 1
        print(f"Clave nueva de la línea {a.line_id} (pégala en el monitor):\n{token}")
    elif a.cmd == "desactivar-linea":
        with eng.begin() as c:
            n = c.execute(update(lines).where(lines.c.id == a.line_id).values(enabled=False)).rowcount
        print("Línea desactivada" if n else "No existe esa línea")
    elif a.cmd == "limpiar":
        print(purge(eng, st.retention_days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
