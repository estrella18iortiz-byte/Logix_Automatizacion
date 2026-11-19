"""Robots R4 y R5 · Comunicación Adquisiciones ⇄ Recursos Financieros y conciliación del pago.

Logix NO mueve dinero: el pago lo hace exclusivamente Recursos Financieros con su banco.
Lo que automatiza es la COMUNICACIÓN entre los dos departamentos, en ambos sentidos:

  Adquisiciones → Finanzas : el expediente completo (robot R3) y, si Finanzas lo devolvió,
                             el expediente corregido con la respuesta («Reenviar a Finanzas»).
  Finanzas → Adquisiciones : «Devolver con motivo» (falta algo o algo está mal),
                             «Programar fecha de pago» y «Pago registrado».
  En cada paso Logix avisa solo a quien le toca (y al proveedor cuando le interesa).

R4 (cada minuto): si un expediente lleva mucho tiempo sin respuesta de un lado o del otro,
    le manda un recordatorio a ese departamento (una vez al día).
R5 (cada minuto): Finanzas deja el archivo de movimientos del banco en banco/entrada;
    el robot identifica cada pago por el folio de la OC y el importe, lo marca PAGADO
    y avisa. Lo que no coincide se reporta, no se adivina. (En el prototipo el archivo es SIMULADO.)
"""
import csv
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from . import avisos, config, db
from .errores import ReglaNegocio


def _oc(cur, oc_id: int) -> tuple[str, str, int, Decimal]:
    cur.execute("SELECT folio, estatus, proveedor_id, total FROM ordenes_compra WHERE id = ?", oc_id)
    fila = cur.fetchone()
    if not fila:
        raise ReglaNegocio("La orden de compra no existe.")
    return fila


# ------------------------------------------------------------ bandejas
def por_pagar(cur) -> list[dict]:
    """Bandeja de Finanzas: expedientes que llegaron y esperan pago."""
    cur.execute("""SELECT oc.id, oc.folio, p.razon_social AS proveedor, oc.area_solicitante, oc.total,
                          pg.fecha_turno, pg.fecha_programada, e.ruta_pdf, e.memorandum
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   JOIN pagos pg ON pg.oc_id = oc.id LEFT JOIN expedientes e ON e.oc_id = oc.id
                   WHERE oc.estatus = 'EN_FINANZAS' ORDER BY pg.fecha_turno""")
    return db.filas(cur)


def devueltas(cur) -> list[dict]:
    """Bandeja de Adquisiciones: lo que Finanzas regresó, con su motivo."""
    cur.execute("""SELECT oc.id, oc.folio, p.razon_social AS proveedor, oc.total, e.fecha, e.detalle AS motivo,
                          ex.ruta_pdf
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   JOIN excepciones e ON e.oc_id = oc.id AND e.tipo = 'DEVUELTA_FINANZAS' AND e.estatus = 'ABIERTA'
                   LEFT JOIN expedientes ex ON ex.oc_id = oc.id
                   WHERE oc.estatus = 'DEVUELTA' ORDER BY e.fecha""")
    return db.filas(cur)


# ------------------------------------------------------------ Finanzas → Adquisiciones
def programar(cur, usuario: dict, oc_id: int, fecha: date):
    folio, estatus, proveedor_id, total = _oc(cur, oc_id)
    if estatus != "EN_FINANZAS":
        raise ReglaNegocio("Solo se programa el pago de expedientes que están en Finanzas.")
    if fecha < date.today():
        raise ReglaNegocio("La fecha de pago no puede ser anterior a hoy.")
    cur.execute("UPDATE pagos SET fecha_programada = ? WHERE oc_id = ?", fecha, oc_id)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "PROGRAMA_PAGO", nuevo=str(fecha))
    avisos.a_rol(cur, "ADQUISICIONES", f"Pago programado · {folio}",
                 f"Recursos Financieros programó el pago de la OC {folio} para el {fecha:%d/%m/%Y}.")
    avisos.a_proveedor(cur, proveedor_id, f"Pago programado · PAG-{folio[3:]}",
                       f"El pago de su OC {folio} por ${total:,.2f} quedó programado para el {fecha:%d/%m/%Y}. "
                       "Le avisaremos cuando se registre.")


def devolver(cur, usuario: dict, oc_id: int, motivo: str):
    """Finanzas regresa el expediente a Adquisiciones explicando qué falta o qué está mal."""
    if not motivo or len(motivo.strip()) < 5:
        raise ReglaNegocio("Para devolver es obligatorio escribir el motivo.")
    folio, estatus, _, _ = _oc(cur, oc_id)
    if estatus != "EN_FINANZAS":
        raise ReglaNegocio("Solo se devuelven expedientes que están en Finanzas.")
    cur.execute("UPDATE ordenes_compra SET estatus = 'DEVUELTA' WHERE id = ?", oc_id)
    cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES (?, 'DEVUELTA_FINANZAS', ?)",
                oc_id, motivo.strip())
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "DEVUELVE_A_ADQUISICIONES", "EN_FINANZAS", "DEVUELTA",
                motivo.strip())
    avisos.a_rol(cur, "ADQUISICIONES", f"Finanzas devolvió el expediente · {folio}",
                 f"Recursos Financieros devolvió el expediente de la OC {folio}. Motivo: {motivo.strip()}. "
                 "Corríjalo y use «Reenviar a Finanzas» en Logix.")


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
    avisos.a_rol(cur, "ADQUISICIONES", f"Compra pagada y cerrada · {folio}",
                 f"Recursos Financieros pagó la OC {folio} (referencia {referencia}). El expediente quedó cerrado.")


def registrar_pago(cur, usuario: dict, oc_id: int, referencia: str, fecha_pago: date):
    """Registro manual (respaldo por si no se usa el archivo del banco)."""
    if not referencia or len(referencia.strip()) < 4:
        raise ReglaNegocio("Escriba la referencia bancaria del pago.")
    _, estatus, _, _ = _oc(cur, oc_id)
    if estatus != "EN_FINANZAS":
        raise ReglaNegocio("Solo se registra el pago de expedientes que están en Finanzas.")
    _marcar_pagado(cur, oc_id, referencia.strip(), fecha_pago, usuario["usuario"], conciliado=False)


# ------------------------------------------------------------ Adquisiciones → Finanzas
def reenviar(cur, usuario: dict, oc_id: int, respuesta: str):
    """Adquisiciones contesta la devolución y regresa el expediente a Finanzas."""
    if not respuesta or len(respuesta.strip()) < 5:
        raise ReglaNegocio("Escriba qué se corrigió, para que Finanzas lo sepa.")
    folio, estatus, _, _ = _oc(cur, oc_id)
    if estatus != "DEVUELTA":
        raise ReglaNegocio(f"La OC {folio} no está devuelta por Finanzas.")
    cur.execute("UPDATE excepciones SET estatus = 'RESUELTA', resuelta_por = ?, fecha_resuelta = SYSDATETIME() "
                "WHERE oc_id = ? AND tipo = 'DEVUELTA_FINANZAS' AND estatus = 'ABIERTA'", usuario["id"], oc_id)
    cur.execute("UPDATE ordenes_compra SET estatus = 'EN_FINANZAS' WHERE id = ?", oc_id)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "REENVIA_A_FINANZAS", "DEVUELTA", "EN_FINANZAS",
                respuesta.strip())
    avisos.a_rol(cur, "FINANZAS", f"Expediente corregido · {folio}",
                 f"Adquisiciones corrigió y reenvió el expediente de la OC {folio}. "
                 f"Respuesta: {respuesta.strip()}")


# ------------------------------------------------------------ robot R4 (cada minuto)
def _ya_recordado_hoy(cur, oc_id: int) -> bool:
    cur.execute("SELECT COUNT(*) FROM bitacora WHERE entidad = 'OC' AND entidad_id = ? AND accion = 'RECUERDA' "
                "AND CAST(fecha AS DATE) = CAST(SYSDATETIME() AS DATE)", oc_id)
    return cur.fetchone()[0] > 0


def recordar_pendientes(cur, ahora: datetime | None = None) -> int:
    """Recordatorio a quien tiene detenido el expediente. Regresa cuántos mandó."""
    ahora = ahora or datetime.now()
    horas_fin = int(db.parametro(cur, "HORAS_RECORDATORIO_FINANZAS"))
    horas_adq = int(db.parametro(cur, "HORAS_RECORDATORIO_ADQUISICIONES"))
    enviados = 0
    # Finanzas: expediente recibido y sin fecha de pago.
    cur.execute("""SELECT oc.id, oc.folio, pg.fecha_turno FROM ordenes_compra oc JOIN pagos pg ON pg.oc_id = oc.id
                   WHERE oc.estatus = 'EN_FINANZAS' AND pg.fecha_programada IS NULL""")
    for oc_id, folio, desde in cur.fetchall():
        if ahora - desde >= timedelta(hours=horas_fin) and not _ya_recordado_hoy(cur, oc_id):
            avisos.a_rol(cur, "FINANZAS", f"Recordatorio · {folio}",
                         f"El expediente de la OC {folio} lleva más de {horas_fin} h en Finanzas sin fecha de pago.")
            db.bitacora(cur, "ROBOT-R4", "OC", oc_id, "RECUERDA", detalle="FINANZAS")
            enviados += 1
    # Adquisiciones: expediente devuelto sin corregir.
    cur.execute("""SELECT oc.id, oc.folio, e.fecha FROM ordenes_compra oc JOIN excepciones e ON e.oc_id = oc.id
                   WHERE oc.estatus = 'DEVUELTA' AND e.tipo = 'DEVUELTA_FINANZAS' AND e.estatus = 'ABIERTA'""")
    for oc_id, folio, desde in cur.fetchall():
        if ahora - desde >= timedelta(hours=horas_adq) and not _ya_recordado_hoy(cur, oc_id):
            avisos.a_rol(cur, "ADQUISICIONES", f"Recordatorio · {folio}",
                         f"Finanzas devolvió la OC {folio} hace más de {horas_adq} h y sigue sin reenviarse.")
            db.bitacora(cur, "ROBOT-R4", "OC", oc_id, "RECUERDA", detalle="ADQUISICIONES")
            enviados += 1
    return enviados


# ------------------------------------------------------------ robot R5 (cada minuto)
def conciliar_carpeta(carpeta: Path | None = None) -> list[str]:
    """CSV del banco con columnas: fecha, referencia, concepto, importe."""
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
                        _marcar_pagado(cur, fila[0], mov["referencia"], fecha, "ROBOT-R5", conciliado=True)
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
