"""Robot R3 · Arma el expediente y lo manda a Recursos Financieros.

Antes, Almacén imprimía los documentos, redactaba un memorándum y llevaba la carpeta
a mano a Finanzas. Ahora, en cuanto Almacén confirma que el material llegó:
  1. Logix revisa que el expediente esté completo: orden de compra + factura válida
     por el MISMO importe + entrada de almacén.
  2. Si falta algo, detiene la OC, abre una excepción y avisa a Adquisiciones.
  3. Si está completo, genera UN solo PDF (memorándum + expediente) con su huella SHA-256
     (prueba de que nadie lo alteró) y lo manda a Recursos Financieros.
  4. Le da al proveedor su ticket de seguimiento PAG-… y avisa a Finanzas y a Adquisiciones.
"""
import hashlib
from datetime import date

from . import avisos, db
from .pdfs import pdf_expediente

ACTOR = "ROBOT-R3"


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
    cur.execute("SELECT folio, estatus FROM ordenes_compra WHERE id = ?", oc_id)
    folio, estatus = cur.fetchone()
    faltantes = revisar_completo(cur, oc_id)
    if faltantes:
        cur.execute("UPDATE ordenes_compra SET estatus = 'DETENIDA' WHERE id = ?", oc_id)
        for f in faltantes:
            cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES (?, 'EXPEDIENTE_INCOMPLETO', ?)",
                        oc_id, f)
        db.bitacora(cur, ACTOR, "OC", oc_id, "EXPEDIENTE_INCOMPLETO", estatus, "DETENIDA", " | ".join(faltantes))
        avisos.a_rol(cur, "ADQUISICIONES", f"Expediente detenido · {folio}", "\n".join(faltantes))
        return

    # 1. Un solo PDF con memorándum + expediente y su huella digital.
    cur.execute("SELECT COUNT(*) FROM expedientes")
    memorandum = f"MEM-{date.today().year}-{cur.fetchone()[0] + 1:04d}"
    ruta = pdf_expediente(cur, oc_id, memorandum)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    cur.execute("INSERT INTO expedientes (oc_id, ruta_pdf, sha256, memorandum) VALUES (?, ?, ?, ?)",
                oc_id, str(ruta), huella, memorandum)

    # 2. Se manda a Recursos Financieros.
    cur.execute("INSERT INTO pagos (oc_id) VALUES (?)", oc_id)
    cur.execute("UPDATE ordenes_compra SET estatus = 'EN_FINANZAS' OUTPUT INSERTED.proveedor_id, INSERTED.total "
                "WHERE id = ?", oc_id)
    proveedor_id, total = cur.fetchone()
    db.bitacora(cur, ACTOR, "OC", oc_id, "ENVIA_A_FINANZAS", estatus, "EN_FINANZAS",
                f"{memorandum} SHA-256 {huella[:16]}…")

    # 3. Avisos: Finanzas (lo que llegó), Adquisiciones (ya salió) y proveedor (su ticket).
    avisos.a_rol(cur, "FINANZAS", f"Nuevo expediente para pago · {folio}",
                 f"Llegó el expediente de la OC {folio} por ${total:,.2f} (memorándum {memorandum}). "
                 "Ya trae la orden de compra, la factura validada y la entrada de almacén. "
                 "Revíselo en Logix › Expedientes y programe el pago.")
    avisos.a_rol(cur, "ADQUISICIONES", f"Expediente enviado a Finanzas · {folio}",
                 f"El expediente de la OC {folio} se envió a Recursos Financieros (memorándum {memorandum}).")
    ticket = f"PAG-{folio[3:]}"
    avisos.a_proveedor(cur, proveedor_id, f"Ticket de pago {ticket}",
                       f"Su entrega de la OC {folio} por ${total:,.2f} fue recibida y su expediente se envió a "
                       f"Recursos Financieros. Ticket: {ticket}. Le avisaremos cuando se programe y cuando se "
                       "registre el pago. (Este mensaje no confirma que el pago ya se realizó.)")
