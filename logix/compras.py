"""Robots R8 y R9 · Proveedor apto y Orden de Compra (pasos 4, 5 y 7 del instructivo).

R8: de todo el catálogo (001-04) Logix deja solo a los proveedores APTOS:
    activos, con evaluación 001-02 de más de 70 puntos, evaluación vigente (se
    reevalúa cada año) y que NO aparezcan en la lista 69-B del SAT. Sugiere al mejor.
R9: con la confirmación de Adquisiciones, genera la OC (001-05), la manda a firmas
    y, al autorizarse, le envía al proveedor la OC con instrucciones para facturar.
"""
from datetime import date, timedelta
from decimal import Decimal

from . import avisos, db, firmas
from .errores import ReglaNegocio


def evaluar_proveedores(cur) -> list[dict]:
    """Todos los proveedores con su dictamen (apto o motivo por el que no lo es)."""
    minimo = int(db.parametro(cur, "PUNTAJE_MINIMO"))
    cur.execute("""SELECT p.id, p.razon_social, p.rfc, p.puntaje_evaluacion, p.fecha_evaluacion, p.activo,
                          p.codigo_telegram, p.telegram_chat_id,
                          s.situacion AS sat_69b
                   FROM proveedores p LEFT JOIN sat_lista_69b s ON s.rfc = p.rfc ORDER BY p.razon_social""")
    resultado = []
    for p in db.filas(cur):
        motivos = []
        if not p["activo"]:
            motivos.append("dado de baja del catálogo")
        if (p["puntaje_evaluacion"] or 0) <= minimo:
            motivos.append(f"evaluación de {p['puntaje_evaluacion']} puntos (mínimo más de {minimo})")
        if not p["fecha_evaluacion"] or p["fecha_evaluacion"] < date.today() - timedelta(days=365):
            motivos.append("evaluación vencida (más de 1 año)")
        if p["sat_69b"]:
            motivos.append(f"en lista 69-B del SAT ({p['sat_69b']})")
        p["apto"] = not motivos
        p["motivo"] = "; ".join(motivos) or "Apto"
        resultado.append(p)
    # El sugerido es el apto con mejor puntaje.
    resultado.sort(key=lambda x: (not x["apto"], -(x["puntaje_evaluacion"] or 0)))
    return resultado


def requisiciones_validadas(cur) -> list[dict]:
    cur.execute("""SELECT r.id, r.folio, a.nombre AS area, r.total, r.fecha, r.justificacion
                   FROM requisiciones r JOIN areas a ON a.id = r.area_id
                   WHERE r.estatus = 'VALIDADA' ORDER BY r.fecha""")
    return db.filas(cur)


def crear_oc(cur, usuario: dict, requisicion_ids: list[int], proveedor_id: int,
             cotizaciones_adjuntas: bool = False) -> str:
    if not requisicion_ids:
        raise ReglaNegocio("Seleccione al menos una requisición validada.")
    apto = {p["id"]: p for p in evaluar_proveedores(cur)}.get(proveedor_id)
    if not apto:
        raise ReglaNegocio("El proveedor no existe.")
    if not apto["apto"]:
        raise ReglaNegocio(f"No se puede comprar a {apto['razon_social']}: {apto['motivo']}.")
    total = Decimal("0")
    for rid in requisicion_ids:
        cur.execute("SELECT folio, estatus, total FROM requisiciones WHERE id = ?", rid)
        folio, estatus, monto = cur.fetchone()
        if estatus != "VALIDADA":
            raise ReglaNegocio(f"La requisición {folio} no está validada (estatus {estatus}).")
        total += monto
    umbral = Decimal(db.parametro(cur, "UMBRAL_COTIZACIONES"))
    if total > umbral and not cotizaciones_adjuntas:
        raise ReglaNegocio(f"La compra es de ${total:,.2f} (mayor a ${umbral:,.2f}): "
                           "adjunte las cotizaciones comparativas.")
    folio_oc = db.siguiente_folio(cur, "ordenes_compra", "OC")
    cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, total) OUTPUT INSERTED.id VALUES (?, ?, ?)",
                folio_oc, proveedor_id, total)
    oc_id = cur.fetchone()[0]
    for rid in requisicion_ids:
        cur.execute("INSERT INTO oc_requisiciones VALUES (?, ?)", oc_id, rid)
        cur.execute("UPDATE requisiciones SET estatus = 'EN_OC' WHERE id = ?", rid)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "CREA", nuevo=f"{folio_oc} ${total:,.2f}",
                detalle=f"Proveedor {apto['razon_social']}")
    firmas.iniciar(cur, "OC", oc_id, usuario["usuario"])
    return folio_oc


def lineas_oc(cur, oc_id: int) -> list[dict]:
    cur.execute("""SELECT c.descripcion, c.unidad, d.cantidad, d.precio_unitario, d.importe,
                          r.folio AS requisicion, a.nombre AS area
                   FROM oc_requisiciones x JOIN requisiciones r ON r.id = x.requisicion_id
                   JOIN areas a ON a.id = r.area_id
                   JOIN requisicion_detalle d ON d.requisicion_id = r.id
                   JOIN conceptos c ON c.id = d.concepto_id WHERE x.oc_id = ?""", oc_id)
    return db.filas(cur)


def al_autorizarse_oc(cur, oc_id: int, actor: str):
    """Última firma de la OC: se genera el PDF y se envía al proveedor."""
    from .pdfs import pdf_orden_compra
    ruta = pdf_orden_compra(cur, oc_id)
    cur.execute("UPDATE ordenes_compra SET estatus = 'ESPERANDO_FACTURA', ruta_pdf = ? "
                "OUTPUT INSERTED.folio, INSERTED.proveedor_id, INSERTED.total WHERE id = ?", str(ruta), oc_id)
    folio, proveedor_id, total = cur.fetchone()
    db.bitacora(cur, actor, "OC", oc_id, "CAMBIO_ESTATUS", "EN_FIRMAS", "ESPERANDO_FACTURA")
    avisos.a_proveedor(cur, proveedor_id, f"Orden de compra {folio}",
                       f"Le enviamos la orden de compra {folio} por ${total:,.2f} (IVA incluido). "
                       f"Para facturar: envíe el XML y el PDF de su CFDI a nuestro buzón de facturas con "
                       f"«{folio}» en el asunto. Logix lo validará en automático y le responderá.")
