"""Robot R2 · Motor de firmas electrónicas (un solo motor para los tres flujos).

    REQ  (requisición, 4 niveles): Jefe de área → Presupuestos → Subdirector → Director
    OC   (orden de compra, 3):     Adquisiciones → Jefe de RM → Subdirección Administrativa (Vo. Bo.)
    PAGO (autorización de pago, 3): Adquisiciones → Jefe de RM → Subdirección Administrativa

Los niveles vienen de la tabla flujos_aprobacion (se cambian sin tocar el código).
Reglas: se firma en orden (no se pueden saltar niveles), solo firma el rol que toca
y devolver exige un motivo. Lo que hace el robot solo: turnar al siguiente,
recordar a las 24 h y escalar a las 48 h.
"""
from datetime import datetime, timedelta

from . import avisos, db
from .errores import ReglaNegocio

NOMBRES = {"REQ": "requisición", "OC": "orden de compra", "PAGO": "autorización de pago"}


def _folio(cur, tipo: str, ref_id: int) -> str:
    tabla = "requisiciones" if tipo == "REQ" else "ordenes_compra"
    cur.execute(f"SELECT folio FROM {tabla} WHERE id = ?", ref_id)
    return cur.fetchone()[0]


def _area_de(cur, tipo: str, ref_id: int) -> int | None:
    """Área dueña del trámite (para que firme el Jefe de ESA área)."""
    if tipo == "REQ":
        cur.execute("SELECT area_id FROM requisiciones WHERE id = ?", ref_id)
    else:
        cur.execute("""SELECT TOP 1 r.area_id FROM oc_requisiciones x JOIN requisiciones r ON r.id = x.requisicion_id
                       WHERE x.oc_id = ?""", ref_id)
    fila = cur.fetchone()
    return fila[0] if fila else None


def _activar(cur, aprobacion_id: int):
    cur.execute("UPDATE aprobaciones SET estatus = 'PENDIENTE', fecha_asignacion = SYSDATETIME() "
                "OUTPUT INSERTED.tipo, INSERTED.referencia_id, INSERTED.rol WHERE id = ?", aprobacion_id)
    tipo, ref_id, rol = cur.fetchone()
    folio = _folio(cur, tipo, ref_id)
    area = _area_de(cur, tipo, ref_id) if rol == "JEFE_AREA" else None
    avisos.a_rol(cur, rol, f"Firma pendiente · {folio}",
                 f"Tiene una {NOMBRES[tipo]} por firmar: {folio}. Entre a Logix › Firmas pendientes.", area)


def iniciar(cur, tipo: str, ref_id: int, actor: str):
    """Crea todos los niveles del flujo y activa el primero."""
    cur.execute("SELECT nivel, rol FROM flujos_aprobacion WHERE tipo = ? ORDER BY nivel", tipo)
    niveles = cur.fetchall()
    primero = None
    for nivel, rol in niveles:
        cur.execute("INSERT INTO aprobaciones (tipo, referencia_id, nivel, rol, estatus) OUTPUT INSERTED.id "
                    "VALUES (?, ?, ?, ?, 'ESPERA')", tipo, ref_id, nivel, rol)
        aid = cur.fetchone()[0]
        primero = primero or aid
    db.bitacora(cur, actor, tipo, ref_id, "INICIA_FIRMAS", detalle=f"{len(niveles)} niveles")
    _activar(cur, primero)


def pendientes_de(cur, usuario: dict) -> list[dict]:
    """Bandeja de firmas: lo que le toca firmar a este usuario."""
    cur.execute("""
        SELECT a.id, a.tipo, a.referencia_id, a.nivel, a.fecha_asignacion,
               COALESCE(r.folio, oc.folio) AS folio,
               COALESCE(r.total, oc.total) AS total,
               COALESCE(r.justificacion, p.razon_social) AS detalle,
               COALESCE(r.area_id, (SELECT TOP 1 r2.area_id FROM oc_requisiciones x
                                    JOIN requisiciones r2 ON r2.id = x.requisicion_id WHERE x.oc_id = oc.id)) AS area_id
        FROM aprobaciones a
        LEFT JOIN requisiciones r  ON a.tipo = 'REQ' AND r.id = a.referencia_id
        LEFT JOIN ordenes_compra oc ON a.tipo IN ('OC','PAGO') AND oc.id = a.referencia_id
        LEFT JOIN proveedores p ON p.id = oc.proveedor_id
        WHERE a.estatus = 'PENDIENTE' AND a.rol = ?
        ORDER BY a.fecha_asignacion""", usuario["rol"])
    filas = db.filas(cur)
    if usuario["rol"] == "JEFE_AREA":
        filas = [f for f in filas if f["area_id"] == usuario["area_id"]]
    return filas


def _validar_turno(cur, usuario: dict, aprobacion_id: int):
    cur.execute("SELECT tipo, referencia_id, rol, estatus FROM aprobaciones WHERE id = ?", aprobacion_id)
    fila = cur.fetchone()
    if not fila:
        raise ReglaNegocio("La firma no existe.")
    tipo, ref_id, rol, estatus = fila
    if estatus != "PENDIENTE":
        raise ReglaNegocio("Esta firma no está pendiente (ya se respondió o aún no es su turno).")
    if rol != usuario["rol"]:
        raise ReglaNegocio(f"Esta firma le corresponde al rol {rol}.")
    if rol == "JEFE_AREA" and _area_de(cur, tipo, ref_id) != usuario["area_id"]:
        raise ReglaNegocio("Solo el Jefe del área solicitante puede firmar este nivel.")
    return tipo, ref_id


def aprobar(cur, usuario: dict, aprobacion_id: int):
    tipo, ref_id = _validar_turno(cur, usuario, aprobacion_id)
    cur.execute("UPDATE aprobaciones SET estatus = 'APROBADA', usuario_id = ?, fecha_respuesta = SYSDATETIME() "
                "WHERE id = ?", usuario["id"], aprobacion_id)
    cur.execute("SELECT nivel, rol FROM aprobaciones WHERE id = ?", aprobacion_id)
    nivel, rol = cur.fetchone()
    db.bitacora(cur, usuario["usuario"], tipo, ref_id, "APRUEBA",
                detalle=f"{NOMBRES[tipo].capitalize()} · nivel {nivel} ({rol.replace('_', ' ').title()})")
    cur.execute("SELECT TOP 1 id FROM aprobaciones WHERE tipo = ? AND referencia_id = ? AND estatus = 'ESPERA' "
                "ORDER BY nivel", tipo, ref_id)
    siguiente = cur.fetchone()
    if siguiente:
        _activar(cur, siguiente[0])
    else:
        _flujo_completo(cur, tipo, ref_id, usuario["usuario"])


def devolver(cur, usuario: dict, aprobacion_id: int, motivo: str):
    if not motivo or len(motivo.strip()) < 5:
        raise ReglaNegocio("Para devolver es obligatorio escribir el motivo.")
    tipo, ref_id = _validar_turno(cur, usuario, aprobacion_id)
    cur.execute("UPDATE aprobaciones SET estatus = 'DEVUELTA', usuario_id = ?, motivo = ?, "
                "fecha_respuesta = SYSDATETIME() WHERE id = ?", usuario["id"], motivo.strip(), aprobacion_id)
    # Los niveles que no se alcanzaron se cierran; si se corrige, el flujo empieza de nuevo.
    cur.execute("UPDATE aprobaciones SET estatus = 'CANCELADA' WHERE tipo = ? AND referencia_id = ? "
                "AND estatus = 'ESPERA'", tipo, ref_id)
    db.bitacora(cur, usuario["usuario"], tipo, ref_id, "DEVUELVE", detalle=motivo)
    folio = _folio(cur, tipo, ref_id)
    if tipo == "REQ":
        cur.execute("UPDATE requisiciones SET estatus = 'EN_CORRECCION' OUTPUT INSERTED.solicitante_id "
                    "WHERE id = ?", ref_id)
        avisos.a_usuario(cur, cur.fetchone()[0], f"Requisición devuelta · {folio}",
                         f"Su requisición {folio} fue devuelta. Motivo: {motivo}. Corríjala en Logix y reenvíela.")
    else:
        cur.execute("UPDATE ordenes_compra SET estatus = 'DETENIDA' WHERE id = ?", ref_id)
        cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES (?, ?, ?)",
                    ref_id, f"DEVUELTA_{tipo}", f"{usuario['nombre']} devolvió la {NOMBRES[tipo]}: {motivo}")
        avisos.a_rol(cur, "ADQUISICIONES", f"{NOMBRES[tipo].capitalize()} devuelta · {folio}",
                     f"{usuario['nombre']} devolvió {folio}. Motivo: {motivo}")


def _flujo_completo(cur, tipo: str, ref_id: int, actor: str):
    """Qué pasa cuando firma el último nivel (aquí está la automatización del turno)."""
    from . import compras, expediente, requisiciones
    if tipo == "REQ":
        requisiciones.al_validarse(cur, ref_id, actor)
    elif tipo == "OC":
        compras.al_autorizarse_oc(cur, ref_id, actor)
    elif tipo == "PAGO":
        expediente.turnar_a_finanzas(cur, ref_id, actor)


# ------------------------------------------------------------ robot (cada minuto)
def recordar_y_escalar(cur) -> int:
    """Recordatorio a las N horas y escalamiento a Adquisiciones (dueña del proceso) a las M horas."""
    horas_rec = int(db.parametro(cur, "HORAS_RECORDATORIO"))
    horas_esc = int(db.parametro(cur, "HORAS_ESCALAMIENTO"))
    ahora = datetime.now()
    cur.execute("SELECT id, tipo, referencia_id, rol, fecha_asignacion, recordatorios, escalada "
                "FROM aprobaciones WHERE estatus = 'PENDIENTE'")
    acciones = 0
    for aid, tipo, ref_id, rol, asignada, recs, escalada in cur.fetchall():
        espera = ahora - asignada
        folio = _folio(cur, tipo, ref_id)
        area = _area_de(cur, tipo, ref_id) if rol == "JEFE_AREA" else None
        if espera >= timedelta(hours=horas_esc) and not escalada:
            avisos.a_rol(cur, "ADQUISICIONES", f"Firma detenida · {folio}",
                         f"La {NOMBRES[tipo]} {folio} lleva {espera.days * 24 + espera.seconds // 3600} h "
                         f"esperando la firma del rol {rol}.")
            cur.execute("UPDATE aprobaciones SET escalada = 1 WHERE id = ?", aid)
            db.bitacora(cur, "ROBOT-R2", tipo, ref_id, "ESCALA", detalle=rol)
            acciones += 1
        elif espera >= timedelta(hours=horas_rec) and recs == 0:
            avisos.a_rol(cur, rol, f"Recordatorio de firma · {folio}",
                         f"La {NOMBRES[tipo]} {folio} sigue esperando su firma en Logix.", area)
            cur.execute("UPDATE aprobaciones SET recordatorios = recordatorios + 1 WHERE id = ?", aid)
            db.bitacora(cur, "ROBOT-R2", tipo, ref_id, "RECUERDA", detalle=rol)
            acciones += 1
    return acciones
