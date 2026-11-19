"""Consultas para el tablero, el seguimiento por folio, excepciones, bitácora e indicadores."""
from . import db

ETAPAS = ["Compra registrada", "Factura", "Almacén", "Recursos Financieros", "Pagado"]
# En qué etapa está la OC según su estatus (None = detenida, fuera del camino normal).
ETAPA_DE_ESTATUS = {
    "ESPERANDO_FACTURA": 1, "FACTURA_VALIDADA": 2, "EN_FINANZAS": 3, "PAGADA": 4,
    "DEVUELTA": None, "DETENIDA": None,
}
ESTATUS_LEGIBLE = {
    "ESPERANDO_FACTURA": "Esperando factura del proveedor",
    "FACTURA_VALIDADA": "Factura validada · esperando el material en almacén",
    "EN_FINANZAS": "En Recursos Financieros",
    "DEVUELTA": "Devuelta por Finanzas a Adquisiciones",
    "PAGADA": "Pagada",
    "DETENIDA": "Detenida por excepción",
}


def seguimiento(cur, folio: str) -> dict | None:
    """Línea de tiempo de una OC (o de su ticket de pago PAG-)."""
    folio = folio.strip().upper()
    if folio.startswith("PAG-"):
        folio = "OC-" + folio[4:]
    cur.execute("SELECT id, folio, estatus, total FROM ordenes_compra WHERE folio = ?", folio)
    fila = cur.fetchone()
    if not fila:
        return None
    oid, folio, estatus, total = fila
    cur.execute("SELECT fecha, actor, accion, valor_nuevo, detalle FROM bitacora "
                "WHERE entidad = 'OC' AND entidad_id = ? ORDER BY fecha, id", oid)
    eventos = db.filas(cur)
    return {"folio": folio, "estatus": ESTATUS_LEGIBLE.get(estatus, estatus), "codigo_estatus": estatus,
            "total": total, "etapa": ETAPA_DE_ESTATUS.get(estatus), "eventos": eventos}


def tablero(cur) -> dict:
    cur.execute("SELECT estatus, COUNT(*) FROM ordenes_compra GROUP BY estatus")
    ocs = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM excepciones WHERE estatus = 'ABIERTA'")
    exc = cur.fetchone()[0]
    return {"ordenes": ocs, "excepciones": exc}


def indicadores(cur) -> dict:
    """Métricas para la E4: salen solas de la base y la bitácora (no se capturan a mano)."""
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN resultado='RECHAZADA' THEN 1 ELSE 0 END) FROM facturas")
    total_f, rech = cur.fetchone()
    # Minutos desde que Almacén confirma hasta que el expediente llega a Finanzas (antes: días, a mano).
    cur.execute("""SELECT AVG(CAST(DATEDIFF(SECOND, rc.fecha_recepcion, e.fecha) AS FLOAT)) / 60
                   FROM recepciones rc JOIN expedientes e ON e.oc_id = rc.oc_id""")
    min_envio = cur.fetchone()[0]
    # Horas desde que el expediente llega a Finanzas hasta que se paga.
    cur.execute("""SELECT AVG(CAST(DATEDIFF(MINUTE, pg.fecha_turno, b.fecha) AS FLOAT)) / 60
                   FROM pagos pg JOIN bitacora b ON b.entidad = 'OC' AND b.entidad_id = pg.oc_id
                   AND b.accion = 'PAGADA'""")
    horas_pago = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ordenes_compra WHERE estatus = 'PAGADA'")
    pagadas = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ordenes_compra")
    total_oc = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT oc_id) FROM excepciones WHERE oc_id IS NOT NULL")
    con_exc = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bitacora WHERE accion = 'DEVUELVE_A_ADQUISICIONES'")
    devoluciones = cur.fetchone()[0]
    return {
        "facturas_procesadas": total_f or 0,
        "facturas_rechazadas": rech or 0,
        "min_promedio_envio_a_finanzas": round(min_envio, 2) if min_envio is not None else None,
        "horas_promedio_en_finanzas": round(horas_pago, 1) if horas_pago is not None else None,
        "devoluciones_de_finanzas": devoluciones,
        "ordenes_pagadas": pagadas,
        "ordenes_totales": total_oc,
        "pct_ordenes_con_excepcion": round(100 * con_exc / total_oc, 1) if total_oc else 0,
        "hojas_impresas": 0,
    }


def excepciones_abiertas(cur) -> list[dict]:
    """Excepciones para Adquisiciones (las devoluciones de Finanzas tienen su propia bandeja)."""
    cur.execute("""SELECT e.id, e.fecha, e.tipo, e.detalle, oc.folio FROM excepciones e
                   LEFT JOIN ordenes_compra oc ON oc.id = e.oc_id
                   WHERE e.estatus = 'ABIERTA' AND e.tipo <> 'DEVUELTA_FINANZAS' ORDER BY e.fecha DESC""")
    return db.filas(cur)


def resolver_excepcion(cur, usuario: dict, exc_id: int, nota: str, reactivar: bool = False):
    """Cierra la excepción. Si reactivar=True y la OC estaba DETENIDA, vuelve a esperar factura."""
    cur.execute("UPDATE excepciones SET estatus = 'RESUELTA', resuelta_por = ?, fecha_resuelta = SYSDATETIME() "
                "OUTPUT INSERTED.oc_id WHERE id = ?", usuario["id"], exc_id)
    oc_id = cur.fetchone()[0]
    db.bitacora(cur, usuario["usuario"], "EXCEPCION", exc_id, "RESUELVE", detalle=nota)
    if reactivar and oc_id:
        cur.execute("UPDATE ordenes_compra SET estatus = 'ESPERANDO_FACTURA' WHERE id = ? AND estatus = 'DETENIDA'",
                    oc_id)
        if cur.rowcount:
            db.bitacora(cur, usuario["usuario"], "OC", oc_id, "REACTIVA", "DETENIDA", "ESPERANDO_FACTURA", nota)


def bitacora(cur, limite: int = 300) -> list[dict]:
    cur.execute(f"SELECT TOP {int(limite)} fecha, actor, entidad, entidad_id, accion, valor_anterior, valor_nuevo, "
                "detalle FROM bitacora ORDER BY id DESC")
    return db.filas(cur)


def notificaciones(cur, limite: int = 200) -> list[dict]:
    cur.execute(f"SELECT TOP {int(limite)} id, creada, canal, destinatario, asunto, estatus, intentos, mensaje "
                "FROM notificaciones ORDER BY id DESC")
    return db.filas(cur)
