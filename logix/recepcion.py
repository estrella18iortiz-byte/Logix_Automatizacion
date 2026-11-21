"""Recepción en almacén · el JEFE DE ALMACÉN confirma el material (máximo 7 días).

Lo único que hace una persona aquí es lo que ningún software puede hacer:
revisar el material FÍSICO. El Jefe de Almacén tiene dos botones:

  «✔ Llegó bien»  → entrada y salida automáticas. Si la factura ya estaba validada,
                     el expediente se arma y se paga en ese momento; si no, Logix le
                     PIDE la factura al proveedor (tiene 48 h para mandarla).
  «↩ Devolución»  → el material no llegó o llegó en mal estado. El jefe ESCRIBE LA RAZÓN
                     (obligatoria); la compra se cancela y Logix le manda la razón al
                     proveedor por correo y Telegram.

Para revisar, el jefe ve QUÉ se aceptó comprar: la requisición validada, el área,
la partida y cada artículo con su unidad y cantidad (detalle_para_revisar).

Si pasan 7 días sin que el jefe confirme, el robot R3 (plazos.py) cancela solo.
"""
from datetime import datetime, timedelta

from . import avisos, cancelacion, db, expediente
from .errores import ReglaNegocio


def por_recibir(cur) -> list[dict]:
    """Órdenes enviadas cuyo material todavía no llega, con los días que le quedan."""
    dias = int(db.parametro(cur, "DIAS_ESPERA_MATERIAL"))
    cur.execute("""SELECT oc.id, oc.folio, p.razon_social AS proveedor, oc.area_solicitante, oc.total, oc.fecha,
                          (SELECT COUNT(*) FROM facturas f WHERE f.oc_id = oc.id AND f.resultado = 'VALIDA')
                              AS factura_valida
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   WHERE oc.estatus = 'ESPERANDO_MATERIAL' ORDER BY oc.fecha""")
    filas = db.filas(cur)
    ahora = datetime.now()
    for f in filas:
        f["vence"] = f["fecha"] + timedelta(days=dias)
        f["horas_restantes"] = max(0, int((f["vence"] - ahora).total_seconds() // 3600))
    return filas


def detalle_para_revisar(cur, oc_id: int) -> dict:
    """Lo que el Jefe de Almacén debe recibir: requisición validada + artículos, unidades y cantidades."""
    from .compras import lineas_oc
    cur.execute("""SELECT oc.folio, oc.area_solicitante, oc.total, p.razon_social AS proveedor,
                          r.folio AS requisicion, r.partida, r.partida_nombre, r.justificacion, r.firmas
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   LEFT JOIN requisiciones r ON r.id = oc.requisicion_id WHERE oc.id = ?""", oc_id)
    d = db.filas(cur)[0]
    d["lineas"] = lineas_oc(cur, oc_id)
    return d


def por_devolver(cur) -> list[dict]:
    """Compras canceladas cuyo material sigue en el almacén y debe regresarse al proveedor."""
    cur.execute("""SELECT oc.id, oc.folio, p.razon_social AS proveedor, oc.tipo_cancelacion, oc.motivo_cancelacion,
                          oc.fecha_cancelacion
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   WHERE oc.material_por_devolver = 1 AND oc.material_devuelto = 0 ORDER BY oc.fecha_cancelacion""")
    return db.filas(cur)


def _folio_esperando(cur, oc_id: int) -> str:
    cur.execute("SELECT folio, estatus FROM ordenes_compra WHERE id = ?", oc_id)
    fila = cur.fetchone()
    if not fila:
        raise ReglaNegocio("La orden de compra no existe.")
    folio, estatus = fila
    if estatus != "ESPERANDO_MATERIAL":
        raise ReglaNegocio(f"La OC {folio} no está esperando material (estatus {estatus}).")
    return folio


def confirmar_recepcion(cur, usuario: dict, oc_id: int, observaciones: str = "") -> tuple[str, str]:
    """El material llegó bien: entrada y salida automáticas y siguiente paso (factura o pago)."""
    folio = _folio_esperando(cur, oc_id)
    cur.execute("SELECT COUNT(*) FROM recepciones")
    n = cur.fetchone()[0] + 1
    entrada, salida = f"ENT-{n:05d}", f"SAL-{n:05d}"      # entrada y salida simultánea
    cur.execute("INSERT INTO recepciones (oc_id, almacen_id, folio_entrada, folio_salida, observaciones) "
                "VALUES (?, ?, ?, ?, ?)", oc_id, usuario["id"], entrada, salida,
                (observaciones or "").strip()[:500] or None)
    cur.execute("UPDATE ordenes_compra SET estatus = 'MATERIAL_RECIBIDO' OUTPUT INSERTED.proveedor_id WHERE id = ?",
                oc_id)
    proveedor_id = cur.fetchone()[0]
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "RECIBE_MATERIAL", "ESPERANDO_MATERIAL", "MATERIAL_RECIBIDO",
                f"{entrada}/{salida}")

    cur.execute("SELECT COUNT(*) FROM facturas WHERE oc_id = ? AND resultado = 'VALIDA'", oc_id)
    if cur.fetchone()[0]:
        # La factura ya estaba validada: se le confirma el material y el expediente se va a Finanzas.
        avisos.a_proveedor(cur, proveedor_id, f"Material recibido · {folio}",
                           f"✅ Nuestro Almacén recibió y revisó su material de la orden {folio} (entrada {entrada}). "
                           "Su factura ya estaba validada, así que su expediente pasa a Recursos Financieros para "
                           "el pago. En un momento le llega su ticket.")
        expediente.armar_y_enviar(cur, oc_id)
    else:
        horas = db.parametro(cur, "HORAS_ESPERA_FACTURA")
        avisos.a_proveedor(cur, proveedor_id, f"Material recibido · envíe su factura · {folio}",
                           f"✅ Nuestro Almacén recibió y revisó su material de la orden {folio} (entrada {entrada}).\n\n"
                           f"Ahora envíe su factura: mande el XML de su CFDI por este chat con «{folio}» en el pie "
                           f"del archivo (o por correo con «{folio}» en el asunto). Tiene {horas} horas; si no llega, "
                           "la compra se cancela y el material se le devuelve.")
        db.bitacora(cur, "ROBOT-R3", "OC", oc_id, "PIDE_FACTURA", detalle=f"Plazo {horas} h")
    return entrada, salida


def devolucion(cur, usuario: dict, oc_id: int, razon: str) -> str:
    """El material no llegó o llegó en mal estado: el jefe escribe la razón y la compra se cancela."""
    if not razon or len(razon.strip()) < 5:
        raise ReglaNegocio("Escribe la razón de la devolución (qué pasó con el material).")
    _folio_esperando(cur, oc_id)
    return cancelacion.cancelar(cur, oc_id, "DEVOLUCION_ALMACEN", razon, usuario["usuario"])
