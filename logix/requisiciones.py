"""Robot R1 · Requisición inteligente (paso 3 del instructivo, formato 001-03).

La persona solo dice QUÉ necesita y CUÁNTO. Logix:
  - asigna la partida presupuestal del concepto (ya no se memoriza),
  - propone el precio de referencia (último precio pagado),
  - valida el saldo de cada partida ANTES de enviar (antes se descubría al final),
  - avisa si el precio se aleja mucho de la referencia,
  - y la manda sola a las 4 firmas.
Así se evitan las 1 a 3 devoluciones por requisición que se reportaron en la entrevista.
"""
from collections import defaultdict
from decimal import Decimal

from . import avisos, db, firmas
from .errores import ReglaNegocio

DESVIACION_MAXIMA = Decimal("0.30")    # ±30 % contra el precio de referencia


def catalogo_conceptos(cur) -> list[dict]:
    cur.execute("""SELECT c.id, c.descripcion, c.unidad, c.precio_referencia, p.clave AS partida,
                          p.descripcion AS partida_desc, p.saldo
                   FROM conceptos c JOIN partidas p ON p.id = c.partida_id ORDER BY c.descripcion""")
    return db.filas(cur)


def validar_lineas(cur, lineas: list[tuple[int, Decimal, Decimal]]) -> list[str]:
    """lineas = [(concepto_id, cantidad, precio_unitario)]. Regresa la lista de errores."""
    errores = []
    if not lineas:
        return ["Agregue al menos un artículo."]
    por_partida = defaultdict(Decimal)
    saldo = {}
    for concepto_id, cantidad, precio in lineas:
        cur.execute("""SELECT c.descripcion, c.precio_referencia, p.clave, p.saldo
                       FROM conceptos c JOIN partidas p ON p.id = c.partida_id WHERE c.id = ?""", concepto_id)
        fila = cur.fetchone()
        if not fila:
            errores.append(f"El concepto {concepto_id} no existe en el catálogo.")
            continue
        desc, ref, partida, saldo_partida = fila
        if cantidad <= 0:
            errores.append(f"«{desc}»: la cantidad debe ser mayor que cero.")
        if precio <= 0:
            errores.append(f"«{desc}»: el precio debe ser mayor que cero.")
        elif abs(precio - ref) / ref > DESVIACION_MAXIMA:
            errores.append(f"«{desc}»: el precio ${precio:,.2f} se aleja más del 30 % del precio de "
                           f"referencia ${ref:,.2f}. Verifique la cotización.")
        por_partida[partida] += Decimal(cantidad) * Decimal(precio)
        saldo[partida] = saldo_partida
    for partida, monto in por_partida.items():
        if monto > saldo[partida]:
            errores.append(f"Saldo insuficiente en la partida {partida}: se solicitan ${monto:,.2f} "
                           f"y hay ${saldo[partida]:,.2f} disponibles.")
    return errores


def crear(cur, usuario: dict, justificacion: str, lineas) -> str:
    if not justificacion or len(justificacion.strip()) < 10:
        raise ReglaNegocio("Escriba una justificación de al menos 10 caracteres.")
    errores = validar_lineas(cur, lineas)
    if errores:
        raise ReglaNegocio("\n".join(errores))
    folio = db.siguiente_folio(cur, "requisiciones", "REQ")
    total = sum(Decimal(c) * Decimal(p) for _, c, p in lineas)
    cur.execute("INSERT INTO requisiciones (folio, area_id, solicitante_id, justificacion, total) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
                folio, usuario["area_id"], usuario["id"], justificacion.strip(), total)
    req_id = cur.fetchone()[0]
    for concepto_id, cantidad, precio in lineas:
        cur.execute("INSERT INTO requisicion_detalle (requisicion_id, concepto_id, cantidad, precio_unitario) "
                    "VALUES (?, ?, ?, ?)", req_id, concepto_id, cantidad, precio)
    db.bitacora(cur, usuario["usuario"], "REQ", req_id, "CREA", nuevo=f"{folio} ${total:,.2f}")
    firmas.iniciar(cur, "REQ", req_id, usuario["usuario"])
    return folio


def detalle(cur, req_id: int) -> list[dict]:
    cur.execute("""SELECT d.id, d.concepto_id, c.descripcion, c.unidad, d.cantidad, d.precio_unitario, d.importe,
                          p.clave AS partida
                   FROM requisicion_detalle d JOIN conceptos c ON c.id = d.concepto_id
                   JOIN partidas p ON p.id = c.partida_id WHERE d.requisicion_id = ?""", req_id)
    return db.filas(cur)


def corregir_y_reenviar(cur, usuario: dict, req_id: int, cambios: dict[int, tuple[Decimal, Decimal]]):
    """cambios = {detalle_id: (nueva_cantidad, nuevo_precio)}. El historial queda en la bitácora."""
    cur.execute("SELECT estatus, solicitante_id, folio FROM requisiciones WHERE id = ?", req_id)
    estatus, solicitante, folio = cur.fetchone()
    if estatus != "EN_CORRECCION":
        raise ReglaNegocio("Solo se pueden corregir requisiciones devueltas.")
    if solicitante != usuario["id"]:
        raise ReglaNegocio("Solo quien la creó puede corregirla.")
    actuales = {d["id"]: d for d in detalle(cur, req_id)}
    lineas = [(d["concepto_id"], *cambios.get(i, (d["cantidad"], d["precio_unitario"]))) for i, d in actuales.items()]
    errores = validar_lineas(cur, lineas)
    if errores:
        raise ReglaNegocio("\n".join(errores))
    for det_id, (cant, precio) in cambios.items():
        anterior = actuales[det_id]
        cur.execute("UPDATE requisicion_detalle SET cantidad = ?, precio_unitario = ? WHERE id = ?", cant, precio, det_id)
        db.bitacora(cur, usuario["usuario"], "REQ", req_id, "CORRIGE",
                    f"{anterior['cantidad']} x ${anterior['precio_unitario']}", f"{cant} x ${precio}",
                    anterior["descripcion"])
    total = sum(Decimal(c) * Decimal(p) for _, c, p in lineas)
    cur.execute("UPDATE requisiciones SET total = ?, estatus = 'EN_FIRMAS' WHERE id = ?", total, req_id)
    firmas.iniciar(cur, "REQ", req_id, usuario["usuario"])


def al_validarse(cur, req_id: int, actor: str):
    """Última firma: se compromete el saldo y se avisa a Adquisiciones."""
    for d in detalle(cur, req_id):
        cur.execute("UPDATE partidas SET saldo = saldo - ? WHERE clave = ?", d["importe"], d["partida"])
    cur.execute("UPDATE requisiciones SET estatus = 'VALIDADA' OUTPUT INSERTED.folio, INSERTED.solicitante_id "
                "WHERE id = ?", req_id)
    folio, solicitante = cur.fetchone()
    db.bitacora(cur, actor, "REQ", req_id, "CAMBIO_ESTATUS", "EN_FIRMAS", "VALIDADA")
    avisos.a_rol(cur, "ADQUISICIONES", f"Requisición validada · {folio}",
                 f"La requisición {folio} ya tiene las 4 firmas. Logix ya filtró a los proveedores aptos.")
    avisos.a_usuario(cur, solicitante, f"Requisición validada · {folio}",
                     f"Su requisición {folio} fue validada y pasó a Adquisiciones.")


def de_usuario(cur, usuario: dict) -> list[dict]:
    cur.execute("""SELECT r.id, r.folio, r.fecha, r.total, r.estatus, r.justificacion,
                          (SELECT TOP 1 motivo FROM aprobaciones a WHERE a.tipo='REQ' AND a.referencia_id=r.id
                           AND a.estatus='DEVUELTA' ORDER BY a.fecha_respuesta DESC) AS motivo
                   FROM requisiciones r WHERE r.area_id = ? ORDER BY r.fecha DESC""", usuario["area_id"])
    return db.filas(cur)
