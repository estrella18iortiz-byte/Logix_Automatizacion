"""Recepción del bien (pasos 9 y 10 del instructivo).

Lo único que hace una persona aquí es lo que ningún software puede hacer:
  - Almacén revisa el bien FÍSICO y confirma con un clic (y marca si recibió la hoja de seguridad).
  - El área solicitante firma de recibido y califica al proveedor (1 a 5).
Logix hace lo demás: genera la entrada y la salida simultáneas y, con la firma del área,
arma el expediente (R4) y lo manda a las firmas de pago.
"""
from . import avisos, db, expediente
from .errores import ReglaNegocio


def por_recibir(cur) -> list[dict]:
    cur.execute("""SELECT oc.id, oc.folio, p.razon_social AS proveedor, oc.total, oc.fecha
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   WHERE oc.estatus = 'FACTURA_VALIDADA' ORDER BY oc.fecha""")
    return db.filas(cur)


def confirmar_recepcion(cur, usuario: dict, oc_id: int, fds_entregada: bool) -> tuple[str, str]:
    cur.execute("SELECT folio, estatus FROM ordenes_compra WHERE id = ?", oc_id)
    folio, estatus = cur.fetchone()
    if estatus != "FACTURA_VALIDADA":
        raise ReglaNegocio(f"La OC {folio} no está lista para recibirse (estatus {estatus}). "
                           "Primero debe validarse la factura.")
    cur.execute("SELECT COUNT(*) FROM recepciones")
    n = cur.fetchone()[0] + 1
    entrada, salida = f"ENT-{n:05d}", f"SAL-{n:05d}"      # entrada y salida simultánea (paso 10)
    cur.execute("INSERT INTO recepciones (oc_id, almacen_id, folio_entrada, folio_salida, fds_entregada) "
                "VALUES (?, ?, ?, ?, ?)", oc_id, usuario["id"], entrada, salida, int(fds_entregada))
    cur.execute("UPDATE ordenes_compra SET estatus = 'RECIBIDA' WHERE id = ?", oc_id)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "RECIBE_BIEN", "FACTURA_VALIDADA", "RECIBIDA",
                f"{entrada}/{salida} FDS={'sí' if fds_entregada else 'no'}")
    cur.execute("""SELECT DISTINCT r.area_id FROM oc_requisiciones x JOIN requisiciones r ON r.id = x.requisicion_id
                   WHERE x.oc_id = ?""", oc_id)
    for (area_id,) in cur.fetchall():
        for rol in ("SOLICITANTE", "JEFE_AREA"):
            avisos.a_rol(cur, rol, f"Su material llegó · {folio}",
                         f"Almacén recibió el material de la OC {folio}. Al recogerlo, firme de recibido en Logix.",
                         area_id)
    return entrada, salida


def por_firmar_area(cur, usuario: dict) -> list[dict]:
    cur.execute("""SELECT DISTINCT oc.id, oc.folio, p.razon_social AS proveedor, oc.total, rc.fecha_recepcion
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   JOIN recepciones rc ON rc.oc_id = oc.id
                   JOIN oc_requisiciones x ON x.oc_id = oc.id JOIN requisiciones r ON r.id = x.requisicion_id
                   WHERE oc.estatus = 'RECIBIDA' AND rc.firma_area_id IS NULL AND r.area_id = ?""",
                usuario["area_id"])
    return db.filas(cur)


def firmar_recibido(cur, usuario: dict, oc_id: int, calificacion: int):
    if calificacion not in (1, 2, 3, 4, 5):
        raise ReglaNegocio("Califique al proveedor del 1 al 5.")
    if oc_id not in [f["id"] for f in por_firmar_area(cur, usuario)]:
        raise ReglaNegocio("Esta OC no tiene una recepción pendiente de firma para su área.")
    cur.execute("UPDATE recepciones SET firma_area_id = ?, fecha_firma_area = SYSDATETIME(), calificacion = ? "
                "WHERE oc_id = ?", usuario["id"], calificacion, oc_id)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "FIRMA_RECIBIDO", nuevo=f"calificación {calificacion}")
    expediente.armar(cur, oc_id, usuario["usuario"])
