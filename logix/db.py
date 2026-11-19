"""Conexión a SQL Server y bitácora de auditoría."""
from contextlib import contextmanager

import pyodbc

from . import config


@contextmanager
def conexion():
    """Abre una conexión; confirma (commit) si todo sale bien y deshace si hay error."""
    con = pyodbc.connect(config.cadena_conexion(), autocommit=False)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def filas(cur) -> list[dict]:
    """Convierte el resultado de una consulta en una lista de diccionarios."""
    columnas = [c[0] for c in cur.description]
    return [dict(zip(columnas, f)) for f in cur.fetchall()]


def parametro(cur, clave: str) -> str:
    cur.execute("SELECT valor FROM parametros WHERE clave = ?", clave)
    fila = cur.fetchone()
    if fila is None:
        raise KeyError(f"Falta el parámetro {clave} en la tabla parametros.")
    return fila[0]


def siguiente_folio(cur, tabla: str, prefijo: str) -> str:
    """REQ-2026-0001, OC-2026-0001... consecutivo por año."""
    from datetime import date
    base = f"{prefijo}-{date.today().year}-"
    cur.execute(f"SELECT MAX(folio) FROM {tabla} WHERE folio LIKE ?", base + "%")
    ultimo = cur.fetchone()[0]
    n = int(ultimo.rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{base}{n:04d}"


def bitacora(cur, actor: str, entidad: str, entidad_id, accion: str,
             anterior=None, nuevo=None, detalle=None):
    """Toda operación importante deja rastro: quién, qué, cuándo y qué cambió."""
    cur.execute(
        "INSERT INTO bitacora (actor, entidad, entidad_id, accion, valor_anterior, valor_nuevo, detalle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        actor, entidad, entidad_id, accion,
        None if anterior is None else str(anterior)[:200],
        None if nuevo is None else str(nuevo)[:200],
        None if detalle is None else str(detalle)[:1000],
    )
