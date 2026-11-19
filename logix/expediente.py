"""Robot R4 · Arma el expediente digital y lo turna (paso 12 del instructivo).

Antes, Almacén imprimía 5 documentos, redactaba un memorándum y llevaba la carpeta
a firmas y a Finanzas. Ahora, al firmar de recibido el área:
  1. Logix revisa la TRIADA: factura válida = OC, requisición aprobada y entrada de almacén.
  2. Si está completa, genera un solo PDF (memorándum + expediente) con su huella SHA-256.
  3. Lo manda a las 3 firmas de pago y Finanzas lo ve «en camino» (pre-alerta).
  4. Con la última firma, lo turna a Finanzas y le da al proveedor su ticket.
"""
import hashlib
from datetime import date

from . import avisos, db, firmas
from .pdfs import pdf_expediente


def revisar_triada(cur, oc_id: int) -> list[str]:
    faltantes = []
    cur.execute("SELECT oc.total, f.total FROM ordenes_compra oc LEFT JOIN facturas f "
                "ON f.oc_id = oc.id AND f.resultado = 'VALIDA' WHERE oc.id = ?", oc_id)
    total_oc, total_f = cur.fetchone()
    if total_f is None:
        faltantes.append("No hay factura válida.")
    elif total_f != total_oc:
        faltantes.append(f"El importe de la factura (${total_f:,.2f}) no coincide con la OC (${total_oc:,.2f}).")
    cur.execute("""SELECT r.folio FROM oc_requisiciones x JOIN requisiciones r ON r.id = x.requisicion_id
                   WHERE x.oc_id = ? AND (SELECT COUNT(*) FROM aprobaciones a WHERE a.tipo = 'REQ'
                   AND a.referencia_id = r.id AND a.estatus = 'APROBADA') <
                   (SELECT COUNT(*) FROM flujos_aprobacion WHERE tipo = 'REQ')""", oc_id)
    for (folio,) in cur.fetchall():
        faltantes.append(f"La requisición {folio} no tiene todas sus firmas.")
    cur.execute("SELECT folio_entrada, firma_area_id FROM recepciones WHERE oc_id = ?", oc_id)
    rec = cur.fetchone()
    if not rec:
        faltantes.append("No hay entrada de almacén.")
    elif not rec[1]:
        faltantes.append("Falta la firma de recibido del área.")
    return faltantes


def armar(cur, oc_id: int, actor: str):
    cur.execute("SELECT folio FROM ordenes_compra WHERE id = ?", oc_id)
    folio = cur.fetchone()[0]
    faltantes = revisar_triada(cur, oc_id)
    if faltantes:
        cur.execute("UPDATE ordenes_compra SET estatus = 'DETENIDA' WHERE id = ?", oc_id)
        for f in faltantes:
            cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES (?, 'TRIADA_INCOMPLETA', ?)", oc_id, f)
        db.bitacora(cur, "ROBOT-R4", "OC", oc_id, "TRIADA_INCOMPLETA", detalle=" | ".join(faltantes))
        avisos.a_rol(cur, "ADQUISICIONES", f"Expediente detenido · {folio}", "\n".join(faltantes))
        return
    cur.execute("SELECT COUNT(*) FROM expedientes")
    memorandum = f"MEM-{date.today().year}-{cur.fetchone()[0] + 1:04d}"
    ruta = pdf_expediente(cur, oc_id, memorandum)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    cur.execute("INSERT INTO expedientes (oc_id, ruta_pdf, sha256, memorandum) VALUES (?, ?, ?, ?)",
                oc_id, str(ruta), huella, memorandum)
    cur.execute("UPDATE ordenes_compra SET estatus = 'EN_FIRMAS_PAGO' WHERE id = ?", oc_id)
    db.bitacora(cur, "ROBOT-R4", "OC", oc_id, "EXPEDIENTE_INTEGRADO", "RECIBIDA", "EN_FIRMAS_PAGO",
                f"{memorandum} SHA-256 {huella[:16]}…")
    avisos.a_rol(cur, "FINANZAS", f"Pago en camino · {folio}",
                 f"El expediente {folio} ya está integrado y validado (memorándum {memorandum}). "
                 "Está en firmas de autorización de pago; lo verá en su bandeja «En camino».")
    firmas.iniciar(cur, "PAGO", oc_id, "ROBOT-R4")


def turnar_a_finanzas(cur, oc_id: int, actor: str):
    """Última firma de pago: el expediente llega a Finanzas y el proveedor recibe su ticket."""
    cur.execute("INSERT INTO pagos (oc_id) VALUES (?)", oc_id)
    cur.execute("UPDATE ordenes_compra SET estatus = 'EN_FINANZAS' OUTPUT INSERTED.folio, INSERTED.proveedor_id, "
                "INSERTED.total WHERE id = ?", oc_id)
    folio, proveedor_id, total = cur.fetchone()
    db.bitacora(cur, actor, "OC", oc_id, "TURNA_FINANZAS", "EN_FIRMAS_PAGO", "EN_FINANZAS")
    ticket = f"PAG-{folio[3:]}"
    avisos.a_proveedor(cur, proveedor_id, f"Ticket de pago {ticket}",
                       f"Su pago de la OC {folio} por ${total:,.2f} fue AUTORIZADO y TURNADO a Recursos Financieros. "
                       f"Ticket: {ticket}. Le avisaremos cuando se registre el pago. "
                       "(Este mensaje no confirma que el pago ya se realizó.)")
    avisos.a_rol(cur, "FINANZAS", f"Expediente turnado · {folio}",
                 f"El expediente {folio} ya tiene las 3 autorizaciones. Programe el pago en Logix.")
