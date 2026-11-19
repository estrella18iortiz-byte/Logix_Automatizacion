"""Robot R1 · Envío de la orden de compra al proveedor.

La compra YA fue aprobada y comprada (eso pasa antes de Logix). Adquisiciones solo
registra la orden de compra: proveedor, área que pidió el material y qué se compró.
Logix hace lo demás, sin que nadie lo pida:
  1. Le pone folio (OC-2026-0001) y genera el PDF de la orden (formato 001-05) con QR.
  2. Se lo manda al proveedor con las instrucciones para facturar.
  3. La deja en «Esperando factura» para que el robot R2 la valide cuando llegue.
"""
from decimal import Decimal, InvalidOperation

from . import avisos, db
from .errores import ReglaNegocio


def proveedores_activos(cur) -> list[dict]:
    """Proveedores que se pueden elegir. Si alguno está en la lista 69-B del SAT, se avisa."""
    cur.execute("""SELECT p.id, p.razon_social, p.rfc, p.correo, p.codigo_telegram, p.telegram_chat_id,
                          s.situacion AS sat_69b
                   FROM proveedores p LEFT JOIN sat_lista_69b s ON s.rfc = p.rfc
                   WHERE p.activo = 1 ORDER BY p.razon_social""")
    return db.filas(cur)


def registrar_compra(cur, usuario: dict, proveedor_id: int, area_solicitante: str,
                     lineas: list[tuple[str, str, object, object]]) -> str:
    """Registra una compra ya aprobada. lineas = [(descripción, unidad, cantidad, precio con IVA)].
    Regresa el folio de la OC."""
    if not area_solicitante or not area_solicitante.strip():
        raise ReglaNegocio("Escriba el área que solicitó el material.")
    if not lineas:
        raise ReglaNegocio("Agregue al menos un renglón con lo que se compró.")
    renglones, total = [], Decimal("0")
    for descripcion, unidad, cantidad, precio in lineas:
        try:
            cantidad, precio = Decimal(str(cantidad)), Decimal(str(precio))
        except InvalidOperation:
            raise ReglaNegocio("La cantidad y el precio deben ser números.") from None
        if not descripcion or not descripcion.strip():
            raise ReglaNegocio("Cada renglón necesita una descripción.")
        if cantidad <= 0 or precio <= 0:
            raise ReglaNegocio(f"«{descripcion}»: la cantidad y el precio deben ser mayores a cero.")
        renglones.append((descripcion.strip(), (unidad or "Pieza").strip(), cantidad, precio))
        total += cantidad * precio

    cur.execute("SELECT razon_social, activo FROM proveedores WHERE id = ?", proveedor_id)
    prov = cur.fetchone()
    if not prov or not prov[1]:
        raise ReglaNegocio("Elija un proveedor activo del catálogo.")

    folio = db.siguiente_folio(cur, "ordenes_compra", "OC")
    cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, area_solicitante, total, registrada_por) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
                folio, proveedor_id, area_solicitante.strip(), total, usuario["id"])
    oc_id = cur.fetchone()[0]
    for descripcion, unidad, cantidad, precio in renglones:
        cur.execute("INSERT INTO oc_detalle (oc_id, descripcion, unidad, cantidad, precio_unitario) "
                    "VALUES (?, ?, ?, ?, ?)", oc_id, descripcion, unidad, cantidad, precio)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "REGISTRA_COMPRA", nuevo=f"{folio} ${total:,.2f}",
                detalle=f"Proveedor {prov[0]} · área {area_solicitante.strip()}")
    enviar_a_proveedor(cur, oc_id)
    return folio


def lineas_oc(cur, oc_id: int) -> list[dict]:
    cur.execute("SELECT descripcion, unidad, cantidad, precio_unitario, importe FROM oc_detalle "
                "WHERE oc_id = ? ORDER BY id", oc_id)
    return db.filas(cur)


def enviar_a_proveedor(cur, oc_id: int):
    """Genera el PDF de la OC y se lo manda al proveedor con las instrucciones para facturar."""
    from .pdfs import pdf_orden_compra
    ruta = pdf_orden_compra(cur, oc_id)
    cur.execute("UPDATE ordenes_compra SET ruta_pdf = ? OUTPUT INSERTED.folio, INSERTED.proveedor_id, "
                "INSERTED.total WHERE id = ?", str(ruta), oc_id)
    folio, proveedor_id, total = cur.fetchone()
    db.bitacora(cur, "ROBOT-R1", "OC", oc_id, "ENVIA_OC_PROVEEDOR", nuevo="ESPERANDO_FACTURA")
    avisos.a_proveedor(cur, proveedor_id, f"Orden de compra {folio}",
                       f"Le enviamos la orden de compra {folio} por ${total:,.2f} (IVA incluido). "
                       f"Para facturar: envíe el XML de su CFDI a nuestro buzón de facturas con «{folio}» "
                       "en el asunto (o por Telegram, con el folio en el pie del archivo). "
                       "Logix lo validará en automático y le responderá.")
