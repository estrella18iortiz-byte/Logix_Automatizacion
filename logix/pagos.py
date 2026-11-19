"""Finanzas y robot R10 · Conciliación del pago (pasos 12 y 13 del instructivo).

Logix NO mueve dinero: la dispersión bancaria la hace exclusivamente Recursos Financieros.
Lo que automatiza es el registro: Finanzas deja el archivo de movimientos del banco
en la carpeta banco/entrada y el robot identifica cada pago por el folio de la OC y el importe,
marca el expediente como PAGADO y avisa al proveedor y al área.
(En el prototipo el archivo del banco es SIMULADO.)
"""
import csv
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from . import avisos, config, db
from .errores import ReglaNegocio


def en_camino(cur) -> list[dict]:
    """Pre-alerta: expedientes en firmas de pago (todavía no llegan a Finanzas)."""
    cur.execute("""SELECT oc.id, oc.folio, p.razon_social AS proveedor, oc.total,
                          (SELECT COUNT(*) FROM aprobaciones a WHERE a.tipo='PAGO' AND a.referencia_id=oc.id
                           AND a.estatus='APROBADA') AS firmas
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   WHERE oc.estatus = 'EN_FIRMAS_PAGO' ORDER BY oc.folio""")
    return db.filas(cur)


def por_pagar(cur) -> list[dict]:
    cur.execute("""SELECT oc.id, oc.folio, p.razon_social AS proveedor, oc.total, pg.fecha_turno,
                          pg.fecha_programada, e.ruta_pdf
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   JOIN pagos pg ON pg.oc_id = oc.id LEFT JOIN expedientes e ON e.oc_id = oc.id
                   WHERE oc.estatus = 'EN_FINANZAS' ORDER BY pg.fecha_turno""")
    return db.filas(cur)


def programar(cur, usuario: dict, oc_id: int, fecha: date):
    cur.execute("UPDATE pagos SET fecha_programada = ? WHERE oc_id = ?", fecha, oc_id)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "PROGRAMA_PAGO", nuevo=str(fecha))


def _marcar_pagado(cur, oc_id: int, referencia: str, fecha_pago: date, actor: str, conciliado: bool):
    cur.execute("UPDATE pagos SET referencia = ?, fecha_pago = ?, conciliado = ? WHERE oc_id = ?",
                referencia, fecha_pago, int(conciliado), oc_id)
    cur.execute("UPDATE ordenes_compra SET estatus = 'PAGADA' OUTPUT INSERTED.folio, INSERTED.proveedor_id, "
                "INSERTED.total WHERE id = ?", oc_id)
    folio, proveedor_id, total = cur.fetchone()
    db.bitacora(cur, actor, "OC", oc_id, "PAGADA", "EN_FINANZAS", "PAGADA", f"ref {referencia}")
    avisos.a_proveedor(cur, proveedor_id, f"Pago realizado · {folio}",
                       f"Recursos Financieros registró el pago de la OC {folio} por ${total:,.2f} "
                       f"el {fecha_pago:%d/%m/%Y} (referencia {referencia}). ¡Gracias!")
    cur.execute("""SELECT DISTINCT r.area_id FROM oc_requisiciones x JOIN requisiciones r ON r.id = x.requisicion_id
                   WHERE x.oc_id = ?""", oc_id)
    for (area_id,) in cur.fetchall():
        avisos.a_rol(cur, "JEFE_AREA", f"Compra cerrada · {folio}", f"La compra {folio} quedó pagada y cerrada.", area_id)


def registrar_pago(cur, usuario: dict, oc_id: int, referencia: str, fecha_pago: date):
    """Registro manual (respaldo por si no se usa el archivo del banco)."""
    if not referencia or len(referencia.strip()) < 4:
        raise ReglaNegocio("Escriba la referencia bancaria del pago.")
    cur.execute("SELECT estatus FROM ordenes_compra WHERE id = ?", oc_id)
    if cur.fetchone()[0] != "EN_FINANZAS":
        raise ReglaNegocio("Solo se registra el pago de expedientes turnados a Finanzas.")
    _marcar_pagado(cur, oc_id, referencia.strip(), fecha_pago, usuario["usuario"], conciliado=False)


def devolver(cur, usuario: dict, oc_id: int, motivo: str):
    if not motivo or len(motivo.strip()) < 5:
        raise ReglaNegocio("Para devolver es obligatorio escribir el motivo.")
    cur.execute("UPDATE ordenes_compra SET estatus = 'DETENIDA' OUTPUT INSERTED.folio WHERE id = ?", oc_id)
    folio = cur.fetchone()[0]
    cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES (?, 'DEVUELTA_FINANZAS', ?)", oc_id, motivo)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "DEVUELVE_FINANZAS", detalle=motivo)
    avisos.a_rol(cur, "ADQUISICIONES", f"Finanzas devolvió · {folio}", motivo)


def conciliar_carpeta(carpeta: Path | None = None) -> list[str]:
    """Robot R10. CSV con columnas: fecha, referencia, concepto, importe."""
    entrada = carpeta or (config.RAIZ / "banco" / "entrada")
    procesados = entrada.parent / "procesados"
    entrada.mkdir(parents=True, exist_ok=True)
    procesados.mkdir(parents=True, exist_ok=True)
    resumen = []
    for archivo in sorted(entrada.glob("*.csv")):
        with db.conexion() as con:
            cur = con.cursor()
            with open(archivo, encoding="utf-8-sig") as fh:
                for mov in csv.DictReader(fh):
                    importe = Decimal(mov["importe"].replace(",", "").replace("$", ""))
                    cur.execute("""SELECT oc.id, oc.folio, oc.total FROM ordenes_compra oc
                                   WHERE oc.estatus = 'EN_FINANZAS' AND ? LIKE '%' + oc.folio + '%'""",
                                mov["concepto"].upper())
                    fila = cur.fetchone()
                    if fila and fila[2] == importe:
                        fecha = datetime.strptime(mov["fecha"], "%Y-%m-%d").date()
                        _marcar_pagado(cur, fila[0], mov["referencia"], fecha, "ROBOT-R10", conciliado=True)
                        resumen.append(f"{fila[1]} conciliada (ref {mov['referencia']})")
                    else:
                        detalle = (f"Movimiento sin expediente que coincida: {mov['concepto']} ${importe:,.2f} "
                                   f"(ref {mov['referencia']})")
                        cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES (?, 'PAGO_NO_IDENTIFICADO', ?)",
                                    fila[0] if fila else None, detalle)
                        avisos.a_rol(cur, "FINANZAS", "Movimiento bancario sin identificar", detalle)
                        resumen.append(detalle)
        shutil.move(str(archivo), procesados / f"{datetime.now():%Y%m%d_%H%M%S}_{archivo.name}")
    return resumen
