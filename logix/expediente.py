"""Robot R4 · Arma el expediente y lo entrega a Recursos Financieros.

Finanzas es quien recibe, al final, la FACTURA validada y la CONFIRMACIÓN de que el
material está en almacén. En cuanto Logix tiene las dos cosas (no importa cuál llegó primero):
  1. Revisa que el expediente esté completo: orden de compra + factura válida por el
     MISMO importe + entrada de almacén.
  2. Genera UN solo PDF (memorándum + expediente) con su huella SHA-256
     (prueba de que nadie lo alteró) y lo deja en la bandeja de Finanzas.
  3. Le da al proveedor su ticket PAG-…. (A Finanzas NO se le avisa: si todo está bien
     el pago sale solo; solo se le avisa cuando el banco falla.)
  4. Como no hay problemas, le pide al robot R5 que haga el pago en el banco emulado. Para que se
     parezca a un banco real, el pago sale entre MINUTOS_PAGO_MIN y MINUTOS_PAGO_MAX (5–10 min)
     después; si los dos parámetros valen 0, sale en ese momento (así corren las pruebas).
"""
import hashlib
from datetime import date

from . import avisos, db
from .pdfs import pdf_expediente

ACTOR = "ROBOT-R4"


def revisar_completo(cur, oc_id: int) -> list[str]:
    """Regresa la lista de lo que falta (vacía = expediente completo)."""
    faltantes = []
    cur.execute("SELECT oc.total, f.total FROM ordenes_compra oc LEFT JOIN facturas f "
                "ON f.oc_id = oc.id AND f.resultado = 'VALIDA' WHERE oc.id = ?", oc_id)
    total_oc, total_f = cur.fetchone()
    if total_f is None:
        faltantes.append("No hay factura válida.")
    elif total_f != total_oc:
        faltantes.append(f"El importe de la factura (${total_f:,.2f}) no coincide con la OC (${total_oc:,.2f}).")
    cur.execute("SELECT COUNT(*) FROM recepciones WHERE oc_id = ?", oc_id)
    if not cur.fetchone()[0]:
        faltantes.append("No hay entrada de almacén (el material no se ha confirmado).")
    return faltantes


def armar_y_enviar(cur, oc_id: int):
    from . import pagos   # aquí para evitar una importación circular
    cur.execute("SELECT folio, estatus FROM ordenes_compra WHERE id = ?", oc_id)
    folio, estatus = cur.fetchone()
    faltantes = revisar_completo(cur, oc_id)
    if faltantes:
        # No debería pasar (solo se llama con factura y material), pero si pasa no se paga nada.
        db.bitacora(cur, ACTOR, "OC", oc_id, "EXPEDIENTE_INCOMPLETO", detalle=" | ".join(faltantes))
        return

    # 1. Un solo PDF con memorándum + expediente y su huella digital.
    cur.execute("SELECT COUNT(*) FROM expedientes")
    memorandum = f"MEM-{date.today().year}-{cur.fetchone()[0] + 1:04d}"
    ruta = pdf_expediente(cur, oc_id, memorandum)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    cur.execute("INSERT INTO expedientes (oc_id, ruta_pdf, sha256, memorandum) VALUES (?, ?, ?, ?)",
                oc_id, str(ruta), huella, memorandum)

    # 2. Llega a Recursos Financieros con el monto y la moneda de la factura validada.
    cur.execute("SELECT TOP 1 total, moneda FROM facturas WHERE oc_id = ? AND resultado = 'VALIDA'", oc_id)
    monto, moneda = cur.fetchone()
    cur.execute("INSERT INTO pagos (oc_id, monto, moneda) VALUES (?, ?, ?)", oc_id, monto, moneda)
    cur.execute("UPDATE ordenes_compra SET estatus = 'EN_FINANZAS' OUTPUT INSERTED.proveedor_id, INSERTED.total "
                "WHERE id = ?", oc_id)
    proveedor_id, total = cur.fetchone()
    db.bitacora(cur, ACTOR, "OC", oc_id, "ENVIA_A_FINANZAS", estatus, "EN_FINANZAS",
                f"{memorandum} SHA-256 {huella[:16]}…")

    # 3. El robot R5 programa el pago (sale al banco en 5–10 minutos, como un banco real).
    minutos = pagos.programar(cur, oc_id)

    # 4. Aviso al proveedor con su ticket.
    ticket = f"PAG-{folio[3:]}"
    cuando = (f"El pago sale al banco en unos {minutos} minutos." if minutos
              else "El pago ya se mandó al banco.")
    avisos.a_proveedor(cur, proveedor_id, f"Ticket de pago {ticket}",
                       f"🧾 Su factura y su material de la orden {folio} por ${total:,.2f} están completos y pasan al "
                       f"banco.\nTicket: {ticket}\n{cuando} Le avisaremos en cuanto el banco lo confirme.\n\n"
                       f"Para ver cómo va su pago, escriba «{ticket}» o «{folio}» en este chat.")
    if not minutos:
        pagos.pagar(cur, oc_id)
