"""Robot R5 · Pago AUTOMÁTICO en el banco emulado y respuesta a cada resultado del banco.

Cuando el expediente llega completo a Recursos Financieros (factura validada + material
confirmado por el Jefe de Almacén), Logix manda la transferencia al banco emulado sin
que nadie presione nada. Lo que hace con la respuesta del banco:

  CONFIRMADO          OC PAGADA · aviso al proveedor (Finanzas no recibe nada: solo ve las fallas)
  PAGO_DUPLICADO      ya se había pagado → también queda PAGADA (no se paga dos veces)
  ERROR_GENERAL       se reintenta SOLO, hasta 3 intentos (uno por vuelta del robot);
                      si sigue fallando → error para Finanzas
  SALDO_INSUFICIENTE  ┐ no se reintenta: la OC queda en PAGO_CON_ERROR y Finanzas decide
  MONTO_INCORRECTO    │ con dos botones: «Reintentar pago» o «Cancelar pago» (con motivo).
  DIVISA_INCORRECTA   ┘ Al proveedor se le avisa «pago en proceso, hubo un retraso».
  CUENTA_INVALIDA     igual, pero al proveedor se le pide corregir su CLABE.

Solo cuando Finanzas presiona «Cancelar pago» la compra se cancela y se avisa al
proveedor (cancelacion.py).
"""
from . import avisos, banco_emulado, cancelacion, db
from .errores import ReglaNegocio

ACTOR = "ROBOT-R5"


def _datos(cur, oc_id: int):
    cur.execute("""SELECT oc.folio, oc.estatus, oc.proveedor_id, p.clabe, pg.monto, pg.moneda, pg.intentos, pg.estatus
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   JOIN pagos pg ON pg.oc_id = oc.id WHERE oc.id = ?""", oc_id)
    fila = cur.fetchone()
    if not fila:
        raise ReglaNegocio("Esa orden no tiene un pago en Recursos Financieros.")
    return fila


# ------------------------------------------------------------ el pago automático
def pagar(cur, oc_id: int, actor: str = ACTOR) -> str:
    """Manda la transferencia al banco emulado y actúa según la respuesta. Regresa el código del banco."""
    folio, estatus_oc, proveedor_id, clabe, monto, moneda, intentos, _ = _datos(cur, oc_id)
    intentos += 1
    r = banco_emulado.transferir(cur, folio, clabe, monto, moneda)
    db.bitacora(cur, actor, "OC", oc_id, "BANCO_RESPONDE", nuevo=r.codigo, detalle=f"Intento {intentos}: {r.mensaje}")

    if r.confirmado:
        _confirmar(cur, oc_id, folio, proveedor_id, monto, r, intentos, estatus_oc)
        return r.codigo

    max_intentos = int(db.parametro(cur, "REINTENTOS_BANCO"))
    if r.codigo == "ERROR_GENERAL" and intentos < max_intentos:
        # Falla momentánea: el robot lo vuelve a intentar en la siguiente vuelta (cada minuto).
        cur.execute("UPDATE pagos SET estatus = 'REINTENTO', intentos = ?, codigo_error = ?, detalle_error = ? "
                    "WHERE oc_id = ?", intentos, r.codigo, r.mensaje[:500], oc_id)
        return r.codigo

    # Error que necesita a una persona: Finanzas decide si reintenta o cancela.
    cur.execute("UPDATE pagos SET estatus = 'ERROR', intentos = ?, codigo_error = ?, detalle_error = ? "
                "WHERE oc_id = ?", intentos, r.codigo, r.mensaje[:500], oc_id)
    cur.execute("UPDATE ordenes_compra SET estatus = 'PAGO_CON_ERROR' WHERE id = ?", oc_id)
    db.bitacora(cur, actor, "OC", oc_id, "PAGO_CON_ERROR", estatus_oc, "PAGO_CON_ERROR", r.codigo)
    que_hacer = {
        "SALDO_INSUFICIENTE": "Cuando haya saldo, presione «Reintentar pago».",
        "MONTO_INCORRECTO": "Revise el monto contra la factura y el límite por operación; luego reintente o cancele.",
        "DIVISA_INCORRECTA": "La factura no está en pesos (MXN). Reintente cuando se corrija o cancele el pago.",
        "CUENTA_INVALIDA": "Se le pidió al proveedor su CLABE correcta. Corríjala con «Corregir CLABE» y reintente.",
        "ERROR_GENERAL": f"El banco falló {intentos} veces seguidas. Reintente más tarde o cancele el pago.",
    }.get(r.codigo, "Reintente o cancele el pago.")
    avisos.a_rol(cur, "FINANZAS", f"Error del banco · {folio}",
                 f"El banco no pudo pagar la OC {folio} (${monto:,.2f}).\nError: {r.codigo} · {r.mensaje}\n{que_hacer}")
    if r.codigo == "CUENTA_INVALIDA":
        avisos.a_proveedor(cur, proveedor_id, f"Pago detenido · PAG-{folio[3:]}",
                           f"No pudimos transferir el pago de la OC {folio}: el banco rechazó su cuenta CLABE "
                           f"registrada ({clabe}). Envíenos su CLABE correcta de 18 dígitos para continuar.")
    else:
        avisos.a_proveedor(cur, proveedor_id, f"Pago en proceso · PAG-{folio[3:]}",
                           f"El pago de su OC {folio} por ${monto:,.2f} sigue en proceso: hubo un retraso con el "
                           "banco. Le avisaremos en cuanto se confirme.")
    return r.codigo


def _confirmar(cur, oc_id, folio, proveedor_id, monto, r, intentos, estatus_oc):
    cur.execute("UPDATE pagos SET estatus = 'CONFIRMADO', intentos = ?, referencia_banco = ?, fecha_pago = SYSDATETIME(), "
                "codigo_error = NULL, detalle_error = NULL WHERE oc_id = ?", intentos, r.clave_rastreo, oc_id)
    cur.execute("UPDATE ordenes_compra SET estatus = 'PAGADA' WHERE id = ?", oc_id)
    db.bitacora(cur, ACTOR, "OC", oc_id, "PAGADA", estatus_oc, "PAGADA",
                f"Banco confirmó · clave de rastreo {r.clave_rastreo}")
    avisos.a_proveedor(cur, proveedor_id, f"Pago confirmado · {folio}",
                       f"¡Todo está bien! El banco confirmó el pago de la orden {folio} por ${monto:,.2f}. "
                       f"Clave de rastreo: {r.clave_rastreo}. Gracias.")


def programar(cur, oc_id: int) -> int:
    """Decide cuándo sale el pago: entre MINUTOS_PAGO_MIN y MINUTOS_PAGO_MAX. Regresa los minutos (0 = ahora)."""
    import random
    from datetime import datetime, timedelta
    minimo = int(db.parametro(cur, "MINUTOS_PAGO_MIN"))
    maximo = max(minimo, int(db.parametro(cur, "MINUTOS_PAGO_MAX")))
    minutos = random.randint(minimo, maximo) if maximo > 0 else 0
    if minutos:
        cur.execute("UPDATE pagos SET estatus = 'PROGRAMADO', programado_para = ? WHERE oc_id = ?",
                    datetime.now() + timedelta(minutes=minutos), oc_id)
        db.bitacora(cur, ACTOR, "OC", oc_id, "PAGO_PROGRAMADO", detalle=f"Sale al banco en {minutos} min")
    return minutos


def pagar_programados(cur, ahora=None) -> int:
    """Vuelta del robot: manda al banco los pagos cuya hora ya llegó. Regresa cuántos mandó."""
    from datetime import datetime
    cur.execute("SELECT oc_id FROM pagos WHERE estatus = 'PROGRAMADO' AND programado_para <= ?",
                ahora or datetime.now())
    ids = [f[0] for f in cur.fetchall()]
    for oc_id in ids:
        cur.execute("UPDATE pagos SET estatus = 'EN_PROCESO' WHERE oc_id = ?", oc_id)
        pagar(cur, oc_id)
    return len(ids)


def reintentar_pendientes(cur) -> int:
    """Vuelta del robot: reintenta los pagos que tuvieron un error general. Regresa cuántos intentó."""
    cur.execute("SELECT oc_id FROM pagos WHERE estatus = 'REINTENTO'")
    ids = [f[0] for f in cur.fetchall()]
    for oc_id in ids:
        pagar(cur, oc_id)
    return len(ids)


# ------------------------------------------------------------ lo que decide Finanzas
def reintentar(cur, usuario: dict, oc_id: int) -> str:
    """Botón «Reintentar pago»: vuelve a mandar la transferencia (los intentos empiezan de nuevo)."""
    folio, estatus, *_ = _datos(cur, oc_id)
    if estatus != "PAGO_CON_ERROR":
        raise ReglaNegocio(f"La OC {folio} no tiene un error de pago (estatus {estatus}).")
    cur.execute("UPDATE pagos SET estatus = 'EN_PROCESO', intentos = 0 WHERE oc_id = ?", oc_id)
    cur.execute("UPDATE ordenes_compra SET estatus = 'EN_FINANZAS' WHERE id = ?", oc_id)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "REINTENTA_PAGO", "PAGO_CON_ERROR", "EN_FINANZAS")
    return pagar(cur, oc_id, actor=usuario["usuario"])


def cancelar_pago(cur, usuario: dict, oc_id: int, motivo: str) -> str:
    """Botón «Cancelar pago»: la compra se cancela y se avisa al proveedor."""
    folio, estatus, *_ = _datos(cur, oc_id)
    if estatus != "PAGO_CON_ERROR":
        raise ReglaNegocio("Solo se cancela el pago de una orden que tuvo un error del banco.")
    return cancelacion.cancelar(cur, oc_id, "PAGO_CANCELADO", motivo, usuario["usuario"])


def corregir_clabe(cur, usuario: dict, oc_id: int, clabe: str):
    """Finanzas captura la CLABE correcta que mandó el proveedor (se valida el dígito verificador)."""
    clabe = (clabe or "").strip().replace(" ", "")
    if not banco_emulado.clabe_valida(clabe):
        raise ReglaNegocio("La CLABE debe tener 18 dígitos y un dígito verificador correcto.")
    folio, _, proveedor_id, anterior, *_ = _datos(cur, oc_id)
    cur.execute("UPDATE proveedores SET clabe = ? WHERE id = ?", clabe, proveedor_id)
    db.bitacora(cur, usuario["usuario"], "PROVEEDOR", proveedor_id, "CORRIGE_CLABE", anterior, clabe, folio)


# ------------------------------------------------------------ bandejas
def fallas(cur) -> list[dict]:
    """Bandeja de Finanzas: SOLO los pagos que el banco rechazó y necesitan una decisión de dinero."""
    return [f for f in en_finanzas(cur) if f["estatus"] == "PAGO_CON_ERROR"]


def en_finanzas(cur) -> list[dict]:
    """Expedientes con pago en curso o con error del banco."""
    cur.execute("""SELECT oc.id, oc.folio, oc.estatus, p.razon_social AS proveedor, p.clabe, oc.total,
                          pg.fecha_turno, pg.estatus AS estatus_pago, pg.intentos, pg.codigo_error,
                          pg.detalle_error, e.ruta_pdf, e.memorandum
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   JOIN pagos pg ON pg.oc_id = oc.id LEFT JOIN expedientes e ON e.oc_id = oc.id
                   WHERE oc.estatus IN ('EN_FINANZAS', 'PAGO_CON_ERROR') ORDER BY pg.fecha_turno""")
    return db.filas(cur)


def pagados(cur, limite: int = 100) -> list[dict]:
    cur.execute(f"""SELECT TOP {int(limite)} oc.id, oc.folio, p.razon_social AS proveedor, pg.monto,
                           pg.referencia_banco, pg.fecha_pago, pg.intentos, e.ruta_pdf
                    FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                    JOIN pagos pg ON pg.oc_id = oc.id LEFT JOIN expedientes e ON e.oc_id = oc.id
                    WHERE pg.estatus = 'CONFIRMADO' ORDER BY pg.fecha_pago DESC""")
    return db.filas(cur)
