"""Consultas para el tablero, el seguimiento por folio (RF-15), excepciones, bitácora e indicadores."""
from . import db

ETAPAS = ["Requisición", "Firmas", "Orden de compra", "Factura", "Recepción", "Firmas de pago", "Finanzas", "Pagado"]
ETAPA_DE_ESTATUS = {
    "EN_FIRMAS": 2, "ESPERANDO_FACTURA": 3, "FACTURA_VALIDADA": 4, "RECIBIDA": 4,
    "EN_FIRMAS_PAGO": 5, "EN_FINANZAS": 6, "PAGADA": 7, "DETENIDA": None,
}
ESTATUS_LEGIBLE = {
    "EN_FIRMAS": "En firmas", "EN_CORRECCION": "Devuelta para corrección", "VALIDADA": "Validada",
    "EN_OC": "En orden de compra", "ESPERANDO_FACTURA": "Esperando factura del proveedor",
    "FACTURA_VALIDADA": "Factura validada · esperando el bien", "RECIBIDA": "Bien recibido · falta firma del área",
    "EN_FIRMAS_PAGO": "En autorización de pago", "EN_FINANZAS": "Turnado a Finanzas", "PAGADA": "Pagada",
    "DETENIDA": "Detenida por excepción",
}


def seguimiento(cur, folio: str) -> dict | None:
    """Línea de tiempo de una requisición o de una OC (o de su ticket PAG-)."""
    folio = folio.strip().upper()
    if folio.startswith("PAG-"):
        folio = "OC-" + folio[4:]
    if folio.startswith("REQ-"):
        cur.execute("SELECT id, folio, estatus, total FROM requisiciones WHERE folio = ?", folio)
        fila = cur.fetchone()
        if not fila:
            return None
        rid, folio, estatus, total = fila
        cur.execute("SELECT TOP 1 oc.folio, oc.estatus FROM oc_requisiciones x JOIN ordenes_compra oc ON oc.id = x.oc_id "
                    "WHERE x.requisicion_id = ?", rid)
        oc = cur.fetchone()
        ids = [("REQ", rid)]
        etapa = 1 if estatus in ("EN_FIRMAS", "EN_CORRECCION") else 2
        if oc:
            return {**seguimiento(cur, oc[0]), "consultado": folio}
    else:
        cur.execute("SELECT id, folio, estatus, total FROM ordenes_compra WHERE folio = ?", folio)
        fila = cur.fetchone()
        if not fila:
            return None
        oid, folio, estatus, total = fila
        cur.execute("SELECT requisicion_id FROM oc_requisiciones WHERE oc_id = ?", oid)
        ids = [("REQ", r) for (r,) in cur.fetchall()] + [("OC", oid), ("PAGO", oid)]
        etapa = ETAPA_DE_ESTATUS.get(estatus)
    condiciones = " OR ".join("(entidad = ? AND entidad_id = ?)" for _ in ids)
    params = [x for par in ids for x in (("OC" if par[0] == "PAGO" else par[0]), par[1])]
    cur.execute(f"SELECT fecha, actor, accion, valor_nuevo, detalle FROM bitacora WHERE {condiciones} ORDER BY fecha",
                *params)
    eventos = db.filas(cur)
    cur.execute(f"SELECT fecha_respuesta AS fecha, u.nombre AS actor, a.tipo, a.estatus, a.motivo FROM aprobaciones a "
                f"LEFT JOIN usuarios u ON u.id = a.usuario_id WHERE a.estatus IN ('APROBADA','DEVUELTA') AND ("
                + " OR ".join("(a.tipo = ? AND a.referencia_id = ?)" for _ in ids) + ") ORDER BY fecha_respuesta",
                *[x for par in ids for x in par])
    return {"folio": folio, "consultado": folio, "estatus": ESTATUS_LEGIBLE.get(estatus, estatus), "total": total,
            "etapa": etapa, "eventos": eventos, "firmas": db.filas(cur)}


def tablero(cur) -> dict:
    cur.execute("SELECT estatus, COUNT(*) FROM requisiciones GROUP BY estatus")
    reqs = dict(cur.fetchall())
    cur.execute("SELECT estatus, COUNT(*) FROM ordenes_compra GROUP BY estatus")
    ocs = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM excepciones WHERE estatus = 'ABIERTA'")
    exc = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM aprobaciones WHERE estatus = 'PENDIENTE'")
    firmas = cur.fetchone()[0]
    return {"requisiciones": reqs, "ordenes": ocs, "excepciones": exc, "firmas_pendientes": firmas}


def indicadores(cur) -> dict:
    """Métricas para la E4: salen solas de la bitácora (no se capturan a mano)."""
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN resultado='RECHAZADA' THEN 1 ELSE 0 END) FROM facturas")
    total_f, rech = cur.fetchone()
    cur.execute("""SELECT AVG(CAST(DATEDIFF(MINUTE, rc.fecha_recepcion, e.fecha) AS FLOAT))
                   FROM recepciones rc JOIN expedientes e ON e.oc_id = rc.oc_id""")
    min_armado = cur.fetchone()[0]
    cur.execute("""SELECT AVG(CAST(DATEDIFF(MINUTE, fecha_asignacion, fecha_respuesta) AS FLOAT))
                   FROM aprobaciones WHERE estatus = 'APROBADA' AND fecha_asignacion IS NOT NULL""")
    min_firma = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ordenes_compra WHERE estatus = 'PAGADA'")
    pagadas = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ordenes_compra")
    total_oc = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT oc_id) FROM excepciones WHERE oc_id IS NOT NULL")
    con_exc = cur.fetchone()[0]
    return {
        "facturas_procesadas": total_f or 0,
        "facturas_rechazadas": rech or 0,
        "min_promedio_armado_expediente": round(min_armado, 1) if min_armado is not None else None,
        "min_promedio_por_firma": round(min_firma, 1) if min_firma is not None else None,
        "ordenes_pagadas": pagadas,
        "ordenes_totales": total_oc,
        "pct_ordenes_con_excepcion": round(100 * con_exc / total_oc, 1) if total_oc else 0,
        "hojas_impresas": 0,
    }


def excepciones_abiertas(cur) -> list[dict]:
    cur.execute("""SELECT e.id, e.fecha, e.tipo, e.detalle, oc.folio FROM excepciones e
                   LEFT JOIN ordenes_compra oc ON oc.id = e.oc_id WHERE e.estatus = 'ABIERTA' ORDER BY e.fecha DESC""")
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
        db.bitacora(cur, usuario["usuario"], "OC", oc_id, "REACTIVA", "DETENIDA", "ESPERANDO_FACTURA", nota)


def bitacora(cur, limite: int = 300) -> list[dict]:
    cur.execute(f"SELECT TOP {int(limite)} fecha, actor, entidad, entidad_id, accion, valor_anterior, valor_nuevo, "
                "detalle FROM bitacora ORDER BY id DESC")
    return db.filas(cur)


def notificaciones(cur, limite: int = 200) -> list[dict]:
    cur.execute(f"SELECT TOP {int(limite)} id, creada, canal, destinatario, asunto, estatus, intentos, mensaje "
                "FROM notificaciones ORDER BY id DESC")
    return db.filas(cur)
