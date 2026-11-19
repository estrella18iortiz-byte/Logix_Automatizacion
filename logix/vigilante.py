"""Robot R6 · Vigilante del cierre de ejercicio.

Si un pago no se hace antes de la fecha límite de diciembre, se tiene que cubrir con el
presupuesto del año siguiente (riesgo señalado en la entrevista). Una vez al día, Logix
revisa todas las compras abiertas y les pone semáforo:
    🔴 rojo: faltan 15 días o menos · 🟡 amarillo: de 16 a 30 días · 🟢 verde: más de 30.
A las rojas les manda alerta a Adquisiciones y a Finanzas (una vez al día, no más).
"""
from datetime import date, datetime

from . import avisos, consultas, db

ABIERTAS = ("ESPERANDO_FACTURA", "FACTURA_VALIDADA", "EN_FINANZAS", "DEVUELTA", "DETENIDA")


def semaforo_de(dias: int, rojo: int, amarillo: int) -> str:
    if dias <= rojo:
        return "ROJO"
    if dias <= amarillo:
        return "AMARILLO"
    return "VERDE"


def estado_cierre(cur, hoy: date | None = None) -> list[dict]:
    hoy = hoy or date.today()
    limite = datetime.strptime(db.parametro(cur, "FECHA_LIMITE_PAGOS"), "%Y-%m-%d").date()
    rojo = int(db.parametro(cur, "DIAS_SEMAFORO_ROJO"))
    amarillo = int(db.parametro(cur, "DIAS_SEMAFORO_AMARILLO"))
    dias = (limite - hoy).days
    cur.execute(f"""SELECT oc.id, oc.folio, oc.estatus, oc.total, p.razon_social AS proveedor
                    FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                    WHERE oc.estatus IN ({','.join('?' * len(ABIERTAS))}) ORDER BY oc.folio""", *ABIERTAS)
    filas = db.filas(cur)
    for f in filas:
        f["dias"] = dias
        f["semaforo"] = semaforo_de(dias, rojo, amarillo)
    return filas


def revisar(cur, hoy: date | None = None) -> int:
    """Manda las alertas del día. Regresa cuántas mandó."""
    enviadas = 0
    for f in estado_cierre(cur, hoy):
        if f["semaforo"] != "ROJO":
            continue
        cur.execute("SELECT COUNT(*) FROM bitacora WHERE entidad = 'OC' AND entidad_id = ? "
                    "AND accion = 'ALERTA_CIERRE' AND CAST(fecha AS DATE) = CAST(SYSDATETIME() AS DATE)", f["id"])
        if cur.fetchone()[0]:
            continue                                   # ya se avisó hoy
        estatus = consultas.ESTATUS_LEGIBLE.get(f["estatus"], f["estatus"])
        texto = (f"🔴 La compra {f['folio']} ({f['proveedor']}, ${f['total']:,.2f}) sigue en «{estatus}» "
                 f"y faltan {f['dias']} días para la fecha límite de pagos del ejercicio.")
        for rol in ("ADQUISICIONES", "FINANZAS"):
            avisos.a_rol(cur, rol, f"Riesgo de cierre de ejercicio · {f['folio']}", texto)
        db.bitacora(cur, "ROBOT-R6", "OC", f["id"], "ALERTA_CIERRE", detalle=f"{f['dias']} días")
        enviadas += 1
    return enviadas
