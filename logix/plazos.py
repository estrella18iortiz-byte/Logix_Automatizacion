"""Robot R3 · Vigilante de plazos (corre cada minuto, sin que nadie lo active).

MATERIAL (máximo 7 días desde que se envió la OC):
  · Día 3 ............ recordatorio al proveedor: «recuerde mandar el material»
  · Día 7 menos 5 h .. último aviso al proveedor: «si no manda el material, la compra se cancela»
  · Día 7 ............ si el Jefe de Almacén no confirmó, la compra se CANCELA sola
                       (aviso al proveedor por correo y Telegram)

FACTURA (48 horas desde que el Jefe de Almacén confirmó el material):
  · Al confirmar el material ya se le pidió la factura al proveedor (recepcion.py).
  · A las 48 h, si no hay factura válida, la compra se CANCELA y el material se devuelve.

Cada aviso se manda UNA sola vez: antes de mandarlo se revisa en la bitácora si ya se mandó.
Todos los tiempos están en la tabla parametros (se cambian sin tocar el código).
"""
from datetime import datetime, timedelta

from . import avisos, cancelacion, db

ACTOR = "ROBOT-R3"


def _ya_hecho(cur, oc_id: int, accion: str) -> bool:
    cur.execute("SELECT COUNT(*) FROM bitacora WHERE entidad = 'OC' AND entidad_id = ? AND accion = ?", oc_id, accion)
    return cur.fetchone()[0] > 0


def revisar(cur, ahora: datetime | None = None) -> dict:
    """Una vuelta del vigilante. Regresa cuántos recordatorios, avisos y cancelaciones hizo."""
    ahora = ahora or datetime.now()
    dias_material = int(db.parametro(cur, "DIAS_ESPERA_MATERIAL"))
    dia_recordatorio = int(db.parametro(cur, "DIAS_RECORDATORIO_MATERIAL"))
    horas_aviso = int(db.parametro(cur, "HORAS_AVISO_ANTES_DE_CANCELAR"))
    horas_factura = int(db.parametro(cur, "HORAS_ESPERA_FACTURA"))
    hechos = {"recordatorios": 0, "avisos_cancelacion": 0, "cancelaciones": 0}

    # ---------- 1. Material que no llega
    cur.execute("SELECT id, folio, proveedor_id, fecha FROM ordenes_compra WHERE estatus = 'ESPERANDO_MATERIAL'")
    for oc_id, folio, proveedor_id, enviada in cur.fetchall():
        vence = enviada + timedelta(days=dias_material)
        if ahora >= vence:
            cancelacion.cancelar(cur, oc_id, "MATERIAL_NO_LLEGO",
                                 f"Pasaron {dias_material} días desde que se envió la orden de compra y el "
                                 "Jefe de Almacén no confirmó la llegada del material.", ACTOR)
            hechos["cancelaciones"] += 1
        elif ahora >= vence - timedelta(hours=horas_aviso) and not _ya_hecho(cur, oc_id, "AVISO_CANCELACION"):
            avisos.a_proveedor(cur, proveedor_id, f"Último aviso · {folio}",
                               f"Quedan {horas_aviso} horas para entregar el material de la OC {folio} "
                               f"(vence el {vence:%d/%m/%Y a las %H:%M}). Si no lo manda, la compra se cancela.")
            db.bitacora(cur, ACTOR, "OC", oc_id, "AVISO_CANCELACION", detalle=f"Vence {vence:%d/%m %H:%M}")
            hechos["avisos_cancelacion"] += 1
        elif (ahora >= enviada + timedelta(days=dia_recordatorio)
              and not _ya_hecho(cur, oc_id, "RECUERDA_MATERIAL")):
            avisos.a_proveedor(cur, proveedor_id, f"Recordatorio · {folio}",
                               f"Le recordamos enviar el material de la OC {folio}. Tiene hasta el "
                               f"{vence:%d/%m/%Y a las %H:%M}; después la compra se cancela.")
            db.bitacora(cur, ACTOR, "OC", oc_id, "RECUERDA_MATERIAL", detalle=f"Día {dia_recordatorio}")
            hechos["recordatorios"] += 1

    # ---------- 2. Factura que no llega (el material ya está en almacén)
    cur.execute("""SELECT oc.id, rc.fecha_recepcion FROM ordenes_compra oc JOIN recepciones rc ON rc.oc_id = oc.id
                   WHERE oc.estatus = 'MATERIAL_RECIBIDO'""")
    for oc_id, recibido in cur.fetchall():
        if ahora >= recibido + timedelta(hours=horas_factura):
            cancelacion.cancelar(cur, oc_id, "FACTURA_NO_LLEGO",
                                 f"Pasaron {horas_factura} horas desde que llegó el material y no se recibió "
                                 "una factura válida.", ACTOR)
            hechos["cancelaciones"] += 1
    return hechos
