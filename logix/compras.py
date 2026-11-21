"""Robot R1 · Genera la orden de compra y se la manda al proveedor (SIN que nadie la capture).

La requisición llega YA VALIDADA (evento simulado, simulador.py) y el proveedor es uno de
los proveedores FIJOS ya avalados para esa partida. En cuanto llega, Logix:
  1. Le pone folio (OC-2026-0001) y genera el PDF de la orden (formato 001-05) con QR.
  2. Se lo manda al proveedor por correo y Telegram, con el plazo de 7 días para entregar
     el material y las instrucciones para facturar.
  3. La deja en «Esperando material»: desde ese momento corre el plazo que vigila el robot R3.
"""
from decimal import Decimal, InvalidOperation

from . import avisos, db
from .errores import ReglaNegocio


def proveedores_activos(cur) -> list[dict]:
    """Catálogo de proveedores fijos (ya avalados) que se pueden elegir."""
    cur.execute("""SELECT p.id, p.razon_social, p.rfc, p.correo, p.clabe, p.codigo_telegram, p.telegram_chat_id
                   FROM proveedores p WHERE p.activo = 1 ORDER BY p.razon_social""")
    return db.filas(cur)


def generar_oc(cur, proveedor_id: int, area_solicitante: str, lineas: list[tuple[str, str, object, object]],
               requisicion_id: int | None = None, actor: str = "ROBOT-R1") -> str:
    """Genera la OC de una requisición validada. lineas = [(descripción, unidad, cantidad, precio con IVA)].
    Aunque la requisición ya viene validada, se revisa que los datos tengan sentido. Regresa el folio."""
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
    cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, requisicion_id, area_solicitante, total) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
                folio, proveedor_id, requisicion_id, area_solicitante.strip(), total)
    oc_id = cur.fetchone()[0]
    for descripcion, unidad, cantidad, precio in renglones:
        cur.execute("INSERT INTO oc_detalle (oc_id, descripcion, unidad, cantidad, precio_unitario) "
                    "VALUES (?, ?, ?, ?, ?)", oc_id, descripcion, unidad, cantidad, precio)
    req = ""
    if requisicion_id:
        cur.execute("SELECT folio FROM requisiciones WHERE id = ?", requisicion_id)
        req = f" · requisición {cur.fetchone()[0]}"
    db.bitacora(cur, actor, "OC", oc_id, "GENERA_OC", nuevo=f"{folio} ${total:,.2f}",
                detalle=f"Proveedor {prov[0]} · área {area_solicitante.strip()}{req}")
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
    dias = db.parametro(cur, "DIAS_ESPERA_MATERIAL")
    renglones = "\n".join(f"  • {l['cantidad'].normalize():f} {l['unidad']} · {l['descripcion']}"
                          for l in lineas_oc(cur, oc_id))
    db.bitacora(cur, "ROBOT-R1", "OC", oc_id, "ENVIA_OC_PROVEEDOR", nuevo="ESPERANDO_MATERIAL")
    # El mensaje dice QUÉ se compró y QUÉ puede hacer el proveedor; el PDF oficial va adjunto.
    avisos.a_proveedor(cur, proveedor_id, f"Orden de compra {folio}",
                       f"Le enviamos la orden de compra {folio} por ${total:,.2f} (IVA incluido). El PDF oficial "
                       f"va adjunto.\n\nQué se compró:\n{renglones}\n\n"
                       f"1) Entregue el material en nuestro Almacén en un máximo de {dias} días; si no llega, la "
                       "compra se cancela.\n"
                       "2) Envíe su factura: mande el archivo XML de su CFDI por este chat y escriba "
                       f"«{folio}» en el pie del archivo (o por correo con «{folio}» en el asunto). Logix la valida "
                       "en automático antes de pagar.\n"
                       f"3) Para saber cómo va su compra y su pago, escriba aquí «{folio}» en cualquier momento.",
                       adjunto=str(ruta))
