"""Consultas para el tablero, el seguimiento por folio, cancelaciones, bitácora e indicadores."""
from . import db

ETAPAS = ["OC enviada", "Material en almacén", "Factura validada", "Pago en el banco", "Pagado"]
# En qué etapa está la OC según su estatus (None = cancelada, fuera del camino normal).
ETAPA_DE_ESTATUS = {
    "ESPERANDO_MATERIAL": 0, "MATERIAL_RECIBIDO": 1, "EN_FINANZAS": 3, "PAGO_CON_ERROR": 3, "PAGADA": 4,
    "CANCELADA": None,
}
ESTATUS_LEGIBLE = {
    "ESPERANDO_MATERIAL": "Esperando el material (máx. 7 días)",
    "MATERIAL_RECIBIDO": "Material recibido · esperando la factura (48 h)",
    "EN_FINANZAS": "En Recursos Financieros · pago en proceso",
    "PAGO_CON_ERROR": "Error del banco · Finanzas lo revisa",
    "PAGADA": "Pagada",
    "CANCELADA": "Cancelada",
}


def seguimiento(cur, folio: str) -> dict | None:
    """Línea de tiempo de una OC (o de su ticket de pago PAG-)."""
    folio = folio.strip().upper()
    if folio.startswith("PAG-"):
        folio = "OC-" + folio[4:]
    cur.execute("SELECT id, folio, estatus, total, motivo_cancelacion FROM ordenes_compra WHERE folio = ?", folio)
    fila = cur.fetchone()
    if not fila:
        return None
    oid, folio, estatus, total, motivo = fila
    cur.execute("SELECT fecha, actor, accion, valor_nuevo, detalle FROM bitacora "
                "WHERE entidad = 'OC' AND entidad_id = ? ORDER BY fecha, id", oid)
    eventos = db.filas(cur)
    etapa = ETAPA_DE_ESTATUS.get(estatus)
    # La factura puede llegar antes que el material: si ya está validada, se marca esa etapa.
    cur.execute("SELECT COUNT(*) FROM facturas WHERE oc_id = ? AND resultado = 'VALIDA'", oid)
    if etapa == 1 and cur.fetchone()[0]:
        etapa = 2
    return {"folio": folio, "estatus": ESTATUS_LEGIBLE.get(estatus, estatus), "codigo_estatus": estatus,
            "total": total, "etapa": etapa, "eventos": eventos, "motivo_cancelacion": motivo}


def tablero(cur) -> dict:
    cur.execute("SELECT estatus, COUNT(*) FROM ordenes_compra GROUP BY estatus")
    ocs = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM ordenes_compra WHERE material_por_devolver = 1 AND material_devuelto = 0")
    por_devolver = cur.fetchone()[0]
    return {"ordenes": ocs, "por_devolver": por_devolver}


def indicadores(cur) -> dict:
    """Métricas para la E4: salen solas de la base y la bitácora (no se capturan a mano)."""
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN resultado='RECHAZADA' THEN 1 ELSE 0 END) FROM facturas")
    total_f, rech = cur.fetchone()
    # Horas desde que se envía la OC hasta que el Jefe de Almacén confirma el material.
    cur.execute("""SELECT AVG(CAST(DATEDIFF(MINUTE, oc.fecha, rc.fecha_recepcion) AS FLOAT)) / 60
                   FROM ordenes_compra oc JOIN recepciones rc ON rc.oc_id = oc.id""")
    horas_material = cur.fetchone()[0]
    # Segundos desde que el expediente llega a Finanzas hasta que el banco confirma (pago automático).
    cur.execute("""SELECT AVG(CAST(DATEDIFF(MILLISECOND, fecha_turno, fecha_pago) AS FLOAT)) / 1000
                   FROM pagos WHERE estatus = 'CONFIRMADO'""")
    seg_pago = cur.fetchone()[0]
    cur.execute("SELECT estatus, COUNT(*) FROM ordenes_compra GROUP BY estatus")
    por_estatus = dict(cur.fetchall())
    total_oc = sum(por_estatus.values())
    cur.execute("SELECT tipo_cancelacion, COUNT(*) FROM ordenes_compra WHERE estatus = 'CANCELADA' "
                "GROUP BY tipo_cancelacion")
    cancelaciones = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM banco_movimientos WHERE resultado <> 'CONFIRMADO'")
    errores_banco = cur.fetchone()[0]
    canceladas = por_estatus.get("CANCELADA", 0)
    return {
        "facturas_procesadas": total_f or 0,
        "facturas_rechazadas": rech or 0,
        "horas_promedio_hasta_material": round(horas_material, 1) if horas_material is not None else None,
        "segundos_promedio_pago": round(seg_pago, 2) if seg_pago is not None else None,
        "ordenes_pagadas": por_estatus.get("PAGADA", 0),
        "ordenes_canceladas": canceladas,
        "cancelaciones_por_tipo": cancelaciones,
        "errores_del_banco": errores_banco,
        "ordenes_totales": total_oc,
        "pct_canceladas": round(100 * canceladas / total_oc, 1) if total_oc else 0,
        "hojas_impresas": 0,
    }


def canceladas(cur, limite: int = 200) -> list[dict]:
    """Compras canceladas con su causa y razón (para Adquisiciones)."""
    cur.execute(f"""SELECT TOP {int(limite)} oc.id, oc.folio, p.razon_social AS proveedor, oc.total,
                           oc.tipo_cancelacion, oc.motivo_cancelacion, oc.fecha_cancelacion,
                           oc.material_por_devolver, oc.material_devuelto
                    FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                    WHERE oc.estatus = 'CANCELADA' ORDER BY oc.fecha_cancelacion DESC""")
    return db.filas(cur)


def bitacora(cur, limite: int = 300) -> list[dict]:
    cur.execute(f"SELECT TOP {int(limite)} fecha, actor, entidad, entidad_id, accion, valor_anterior, valor_nuevo, "
                "detalle FROM bitacora ORDER BY id DESC")
    return db.filas(cur)


def notificaciones(cur, limite: int = 200) -> list[dict]:
    cur.execute(f"SELECT TOP {int(limite)} id, creada, canal, destinatario, asunto, estatus, intentos, mensaje "
                "FROM notificaciones ORDER BY id DESC")
    return db.filas(cur)
