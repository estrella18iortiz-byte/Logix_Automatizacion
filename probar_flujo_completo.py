"""Casos de prueba de punta a punta (E4): de la requisición al pago, con datos simulados.

    python probar_flujo_completo.py

Reinicia la base (generar_datos), ejecuta cada caso y guarda la evidencia en
resultados/resultados_pruebas.csv (id, criterio de aceptación, resultado y tiempo).
"""
import csv
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import generar_datos
from logix import (compras, config, consultas, db, firmas, notificador, pagos, recepcion,
                   requisiciones, usuarios, vigilante)
from logix.cfdi_simulado import generar_xml
from logix.errores import ReglaNegocio
from logix.robot_facturas import procesar_factura

RAIZ = Path(__file__).resolve().parent
RESULTADOS = []


def caso(cid: str, criterio: str, descripcion: str):
    def deco(fn):
        def correr(ctx):
            t0 = time.perf_counter()
            try:
                with db.conexion() as con:
                    fn(con.cursor(), ctx)
                ok, nota = True, ""
            except AssertionError as e:
                ok, nota = False, str(e)
            except Exception as e:  # noqa: BLE001
                ok, nota = False, f"{type(e).__name__}: {e}"
            seg = time.perf_counter() - t0
            RESULTADOS.append([cid, criterio, descripcion, "APROBADO" if ok else "FALLIDO", f"{seg:.2f}", nota])
            print(f"{'✔' if ok else '✘'} {cid:6} {criterio:7} {descripcion[:70]:70} {seg:5.2f}s {nota[:80]}")
        return correr
    return deco


def debe_fallar(fn, texto: str):
    try:
        fn()
    except ReglaNegocio as e:
        assert texto.lower() in str(e).lower(), f"mensaje inesperado: {e}"
        return
    raise AssertionError("se esperaba que la regla lo impidiera")


def u(cur, nombre):
    return usuarios.iniciar_sesion(cur, nombre, generar_datos.PASSWORD_DEMO)


def concepto(cur, texto):
    cur.execute("SELECT id, precio_referencia FROM conceptos WHERE descripcion LIKE ?", f"%{texto}%")
    return cur.fetchone()


def firmar_todo(cur, tipo, ref_id):
    """Firma cada nivel con el usuario del rol que toca."""
    while True:
        cur.execute("SELECT id, rol FROM aprobaciones WHERE tipo = ? AND referencia_id = ? AND estatus = 'PENDIENTE'",
                    tipo, ref_id)
        fila = cur.fetchone()
        if not fila:
            return
        cur.execute("SELECT TOP 1 usuario FROM usuarios WHERE rol = ?", fila[1])
        firmas.aprobar(cur, u(cur, cur.fetchone()[0]), fila[0])


# ----------------------------------------------------------------------- casos
@caso("CP-01", "CA-15", "Inicio de sesión: correcto, contraseña errónea y bloqueo tras 5 intentos")
def cp01(cur, ctx):
    assert u(cur, "solicitante")["rol"] == "SOLICITANTE"
    for _ in range(5):
        debe_fallar(lambda: usuarios.iniciar_sesion(cur, "director", "mala"), "incorrectos")
    debe_fallar(lambda: usuarios.iniciar_sesion(cur, "director", generar_datos.PASSWORD_DEMO), "bloqueado")
    cur.execute("UPDATE usuarios SET intentos_fallidos = 0 WHERE usuario = 'director'")


@caso("CP-02", "CA-01", "Requisición con monto mayor al saldo de la partida se bloquea")
def cp02(cur, ctx):
    toner, precio = concepto(cur, "Tóner")
    debe_fallar(lambda: requisiciones.crear(cur, u(cur, "solicitante"), "Tóner para todo el año escolar",
                                            [(toner, Decimal(100), precio)]), "saldo insuficiente")


@caso("CP-03", "CA-01", "Precio 30 % arriba de la referencia se bloquea con explicación")
def cp03(cur, ctx):
    mouse, precio = concepto(cur, "Mouse")
    debe_fallar(lambda: requisiciones.crear(cur, u(cur, "solicitante"), "Mouse para el laboratorio de redes",
                                            [(mouse, Decimal(2), precio * Decimal("1.5"))]), "30 %")


@caso("CP-04", "CA-02", "Requisición correcta: folio, partida automática y turno al Jefe de su área")
def cp04(cur, ctx):
    mouse, p1 = concepto(cur, "Mouse")
    hdmi, p2 = concepto(cur, "HDMI")
    folio = requisiciones.crear(cur, u(cur, "solicitante"), "Equipo para el laboratorio de redes",
                                [(mouse, Decimal(10), p1), (hdmi, Decimal(5), p2)])
    cur.execute("SELECT id, estatus FROM requisiciones WHERE folio = ?", folio)
    ctx["req"], estatus = cur.fetchone()
    assert estatus == "EN_FIRMAS"
    pend = firmas.pendientes_de(cur, u(cur, "jefe.area"))
    assert any(p["folio"] == folio for p in pend), "no le llegó al Jefe de área"
    ctx["folio_req"] = folio


@caso("CP-05", "CA-02", "No se pueden saltar niveles ni firmar por otro rol")
def cp05(cur, ctx):
    cur.execute("SELECT id FROM aprobaciones WHERE tipo='REQ' AND referencia_id=? AND nivel=2", ctx["req"])
    nivel2 = cur.fetchone()[0]
    debe_fallar(lambda: firmas.aprobar(cur, u(cur, "presupuestos"), nivel2), "no está pendiente")
    cur.execute("SELECT id FROM aprobaciones WHERE tipo='REQ' AND referencia_id=? AND nivel=1", ctx["req"])
    nivel1 = cur.fetchone()[0]
    debe_fallar(lambda: firmas.aprobar(cur, u(cur, "director"), nivel1), "corresponde al rol")


@caso("CP-06", "CA-02", "Devolver exige motivo; la corrección reinicia las firmas y queda en bitácora")
def cp06(cur, ctx):
    cur.execute("SELECT id FROM aprobaciones WHERE tipo='REQ' AND referencia_id=? AND estatus='PENDIENTE'", ctx["req"])
    aid = cur.fetchone()[0]
    jefe = u(cur, "jefe.area")
    debe_fallar(lambda: firmas.devolver(cur, jefe, aid, ""), "motivo")
    firmas.devolver(cur, jefe, aid, "Bajar a 8 mouse, ya hay 2 en almacén")
    cur.execute("SELECT estatus FROM requisiciones WHERE id = ?", ctx["req"])
    assert cur.fetchone()[0] == "EN_CORRECCION"
    det = requisiciones.detalle(cur, ctx["req"])
    mouse = next(d for d in det if "Mouse" in d["descripcion"])
    requisiciones.corregir_y_reenviar(cur, u(cur, "solicitante"), ctx["req"],
                                      {mouse["id"]: (Decimal(8), mouse["precio_unitario"])})
    cur.execute("SELECT estatus FROM requisiciones WHERE id = ?", ctx["req"])
    assert cur.fetchone()[0] == "EN_FIRMAS"
    cur.execute("SELECT COUNT(*) FROM bitacora WHERE entidad='REQ' AND entidad_id=? AND accion='CORRIGE'", ctx["req"])
    assert cur.fetchone()[0] == 1


@caso("CP-07", "CA-02", "Las 4 firmas validan la requisición y comprometen el saldo de la partida")
def cp07(cur, ctx):
    cur.execute("SELECT saldo FROM partidas WHERE clave = '21401'")
    antes = cur.fetchone()[0]
    firmar_todo(cur, "REQ", ctx["req"])
    cur.execute("SELECT estatus, total FROM requisiciones WHERE id = ?", ctx["req"])
    estatus, total = cur.fetchone()
    cur.execute("SELECT saldo FROM partidas WHERE clave = '21401'")
    despues = cur.fetchone()[0]
    assert estatus == "VALIDADA", estatus
    assert antes - despues == total, f"saldo {antes} -> {despues}, total {total}"


@caso("CP-08", "CA-03", "Proveedor no apto (62 pts, evaluación vencida o lista 69-B) se bloquea")
def cp08(cur, ctx):
    adq = u(cur, "adquisiciones")
    dictamen = {p["rfc"]: p for p in compras.evaluar_proveedores(cur)}
    for rfc, texto in (("COD030303CC3", "62 puntos"), ("ELD040404DD4", "vencida"), ("DFA050505EE5", "69-B")):
        pid = dictamen[rfc]["id"]
        debe_fallar(lambda: compras.crear_oc(cur, adq, [ctx["req"]], pid), texto)
    assert compras.evaluar_proveedores(cur)[0]["apto"], "el sugerido debe ser apto"


@caso("CP-09", "CA-04", "Compra mayor al umbral sin cotizaciones comparativas no genera OC")
def cp09(cur, ctx):
    cur.execute("UPDATE parametros SET valor = '1000' WHERE clave = 'UMBRAL_COTIZACIONES'")
    cur.execute("SELECT id FROM proveedores WHERE rfc = 'CDE020202BB2'")
    pid = cur.fetchone()[0]
    debe_fallar(lambda: compras.crear_oc(cur, u(cur, "adquisiciones"), [ctx["req"]], pid), "cotizaciones")
    cur.execute("UPDATE parametros SET valor = '300000' WHERE clave = 'UMBRAL_COTIZACIONES'")


@caso("CP-10", "CA-03", "OC con proveedor apto: 3 firmas, PDF 001-05 con QR y envío al proveedor")
def cp10(cur, ctx):
    cur.execute("SELECT id FROM proveedores WHERE rfc = 'CDE020202BB2'")
    pid = cur.fetchone()[0]
    folio = compras.crear_oc(cur, u(cur, "adquisiciones"), [ctx["req"]], pid)
    cur.execute("SELECT id FROM ordenes_compra WHERE folio = ?", folio)
    ctx["oc"], ctx["folio_oc"] = cur.fetchone()[0], folio
    firmar_todo(cur, "OC", ctx["oc"])
    cur.execute("SELECT estatus, ruta_pdf, total FROM ordenes_compra WHERE id = ?", ctx["oc"])
    estatus, ruta, ctx["total_oc"] = cur.fetchone()
    assert estatus == "ESPERANDO_FACTURA", estatus
    assert Path(ruta).exists(), "no se generó el PDF de la OC"


@caso("CP-11", "CA-08", "Robot R3: factura con importe distinto se rechaza y abre excepción")
def cp11(cur, ctx):
    lineas = [(l["descripcion"], l["cantidad"], l["precio_unitario"]) for l in compras.lineas_oc(cur, ctx["oc"])]
    xml = generar_xml("CDE020202BB2", "Cómputo Demo", generar_datos.RFC_INSTITUCION, lineas,
                      total_forzado=ctx["total_oc"] + 300)
    res, cods = procesar_factura(cur, xml, "factura_mala.xml", ctx["folio_oc"])
    assert res == "RECHAZADA" and cods == ["IMPORTE_DISTINTO"], cods
    ctx["lineas"] = lineas


@caso("CP-12", "CA-05", "Almacén no puede recibir el bien sin factura válida")
def cp12(cur, ctx):
    debe_fallar(lambda: recepcion.confirmar_recepcion(cur, u(cur, "almacen"), ctx["oc"], True), "factura")


@caso("CP-13", "CA-08", "Robot R3: factura correcta se valida y avisa a Almacén")
def cp13(cur, ctx):
    xml = generar_xml("CDE020202BB2", "Cómputo Demo", generar_datos.RFC_INSTITUCION, ctx["lineas"])
    res, cods = procesar_factura(cur, xml, "factura_buena.xml", ctx["folio_oc"])
    assert res == "VALIDA", cods


@caso("CP-14", "CA-05", "Recepción: entrada y salida simultánea automática; aviso al área")
def cp14(cur, ctx):
    ent, sal = recepcion.confirmar_recepcion(cur, u(cur, "almacen"), ctx["oc"], True)
    assert ent.startswith("ENT-") and sal.startswith("SAL-")


@caso("CP-15", "CA-06", "Firma de recibido: expediente PDF + memorándum + SHA-256 y pre-alerta a Finanzas")
def cp15(cur, ctx):
    recepcion.firmar_recibido(cur, u(cur, "jefe.area"), ctx["oc"], 5)
    cur.execute("SELECT ruta_pdf, sha256, memorandum FROM expedientes WHERE oc_id = ?", ctx["oc"])
    ruta, sha, mem = cur.fetchone()
    assert Path(ruta).exists() and len(sha) == 64 and mem.startswith("MEM-")
    assert any(e["id"] == ctx["oc"] for e in pagos.en_camino(cur)), "Finanzas no lo ve en camino"


@caso("CP-16", "CA-07", "3 firmas de pago turnan a Finanzas y emiten ticket al proveedor")
def cp16(cur, ctx):
    firmar_todo(cur, "PAGO", ctx["oc"])
    assert any(p["id"] == ctx["oc"] for p in pagos.por_pagar(cur))
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE asunto LIKE 'Ticket de pago%'")
    assert cur.fetchone()[0] >= 1


@caso("CP-17", "CA-10", "Robot R10: conciliación del archivo del banco marca PAGADA; lo no identificado es excepción")
def cp17(cur, ctx):
    carpeta = config.RAIZ / "banco" / "entrada"
    carpeta.mkdir(parents=True, exist_ok=True)
    with open(carpeta / "movimientos_prueba.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "referencia", "concepto", "importe"])
        w.writerow([date.today().isoformat(), "SPEI778899", f"PAGO {ctx['folio_oc']}", f"{ctx['total_oc']:.2f}"])
        w.writerow([date.today().isoformat(), "SPEI000111", "PAGO OC-2026-0999", "123.00"])


@caso("CP-18", "CA-12", "Seguimiento por folio (REQ, OC y ticket PAG) muestra la línea de tiempo")
def cp18(cur, ctx):
    for f in (ctx["folio_req"], ctx["folio_oc"], "PAG-" + ctx["folio_oc"][3:]):
        s = consultas.seguimiento(cur, f)
        assert s and s["estatus"] == "Pagada", (f, s and s["estatus"])
        assert len(s["eventos"]) >= 10
    assert consultas.seguimiento(cur, "OC-2026-9999") is None


@caso("CP-19", "CA-14", "Robot R2: recordatorio a las 24 h y escalamiento a las 48 h")
def cp19(cur, ctx):
    mouse, p = concepto(cur, "Mouse")
    folio = requisiciones.crear(cur, u(cur, "solicitante"), "Reposición de mouse dañados", [(mouse, Decimal(1), p)])
    cur.execute("SELECT id FROM requisiciones WHERE folio = ?", folio)
    rid = cur.fetchone()[0]
    cur.execute("UPDATE aprobaciones SET fecha_asignacion = DATEADD(HOUR, -25, SYSDATETIME()) "
                "WHERE tipo='REQ' AND referencia_id=? AND estatus='PENDIENTE'", rid)
    assert firmas.recordar_y_escalar(cur) == 1
    cur.execute("UPDATE aprobaciones SET fecha_asignacion = DATEADD(HOUR, -49, SYSDATETIME()) "
                "WHERE tipo='REQ' AND referencia_id=? AND estatus='PENDIENTE'", rid)
    assert firmas.recordar_y_escalar(cur) == 1
    assert firmas.recordar_y_escalar(cur) == 0, "no debe repetir avisos"


@caso("CP-20", "CA-14", "Robot R6: semáforo rojo a 10 días del cierre; alerta solo una vez al día")
def cp20(cur, ctx):
    limite = datetime.strptime(db.parametro(cur, "FECHA_LIMITE_PAGOS"), "%Y-%m-%d").date()
    hoy = limite - timedelta(days=10)
    estado = vigilante.estado_cierre(cur, hoy)
    assert estado and all(e["semaforo"] == "ROJO" for e in estado)
    assert vigilante.revisar(cur, hoy) == len(estado)
    assert vigilante.revisar(cur, hoy) == 0
    assert vigilante.estado_cierre(cur, limite - timedelta(days=40))[0]["semaforo"] == "VERDE"


@caso("CP-21", "CA-16", "La bitácora no se puede modificar ni borrar")
def cp21(cur, ctx):
    try:
        cur.execute("DELETE FROM bitacora")
    except Exception:  # noqa: BLE001
        return
    raise AssertionError("se pudo borrar la bitácora")


@caso("CP-23", "RNF-02", "Consulta de folio con 1,000 expedientes simulados en ≤ 2 s")
def cp23(cur, ctx):
    cur.execute("SELECT id FROM proveedores WHERE rfc = 'PDA010101AA1'")
    pid = cur.fetchone()[0]
    for i in range(1000):
        cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, total, estatus) VALUES (?, ?, 100, 'PAGADA')",
                    f"OC-1999-{i:04d}", pid)
        cur.execute("INSERT INTO bitacora (actor, entidad, entidad_id, accion) VALUES ('CARGA', 'OC', SCOPE_IDENTITY(), 'VOLUMEN')")
    t0 = time.perf_counter()
    s = consultas.seguimiento(cur, ctx["folio_oc"])
    seg = time.perf_counter() - t0
    ctx["t_consulta"] = seg
    assert s and seg <= 2, f"{seg:.3f} s"
    cur.execute("DELETE FROM ordenes_compra WHERE folio LIKE 'OC-1999-%'")


def main():
    print("Reiniciando la base con datos simulados ...")
    generar_datos.main()
    print()
    ctx = {}
    for c in (cp01, cp02, cp03, cp04, cp05, cp06, cp07, cp08, cp09, cp10, cp11, cp12, cp13, cp14, cp15, cp16):
        c(ctx)
    cp17(ctx)
    conciliadas = pagos.conciliar_carpeta()
    with db.conexion() as con:
        cur = con.cursor()
        cur.execute("SELECT estatus FROM ordenes_compra WHERE id = ?", ctx.get("oc"))
        ok = cur.fetchone()[0] == "PAGADA" and len(conciliadas) == 2
    RESULTADOS.append(["CP-17b", "CA-10", "Conciliación: OC PAGADA y 1 movimiento no identificado",
                       "APROBADO" if ok else "FALLIDO", "", "; ".join(conciliadas)])
    print(f"{'✔' if ok else '✘'} CP-17b conciliación: {conciliadas}")
    for c in (cp18, cp19, cp20, cp21):
        c(ctx)
    r5 = notificador.enviar_pendientes()
    ok5 = r5["SIMULADA"] > 0 and r5["FALLIDA"] == 0
    RESULTADOS.append(["CP-22", "CA-12", "Robot R5 procesa la cola de avisos (modo simulado)",
                       "APROBADO" if ok5 else "FALLIDO", "", str(r5)])
    print(f"{'✔' if ok5 else '✘'} CP-22  avisos: {r5}")
    cp23(ctx)

    with db.conexion() as con:
        ind = consultas.indicadores(con.cursor())
    salida = RAIZ / "resultados"
    salida.mkdir(exist_ok=True)
    with open(salida / "resultados_pruebas.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "criterio", "descripcion", "resultado", "segundos", "nota"])
        w.writerows(RESULTADOS)
    aprobados = sum(r[3] == "APROBADO" for r in RESULTADOS)
    print(f"\n{aprobados} de {len(RESULTADOS)} casos aprobados · evidencia en {salida / 'resultados_pruebas.csv'}")
    print("Indicadores:", ind)


if __name__ == "__main__":
    main()
