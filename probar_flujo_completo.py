"""Casos de prueba de punta a punta (E4): de la compra ya aprobada al pago, con datos simulados.

    python probar_flujo_completo.py

Reinicia la base (generar_datos), ejecuta cada caso y guarda la evidencia en
resultados/resultados_pruebas.csv (id, criterio de aceptación, resultado y tiempo).
"""
import csv
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import generar_datos
from logix import compras, config, consultas, db, notificador, pagos, recepcion, usuarios, vigilante
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


def avisos_con(cur, asunto: str) -> int:
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE asunto LIKE ?", asunto + "%")
    return cur.fetchone()[0]


def estatus(cur, oc_id) -> str:
    cur.execute("SELECT estatus FROM ordenes_compra WHERE id = ?", oc_id)
    return cur.fetchone()[0]


# ----------------------------------------------------------------------- casos
@caso("CP-01", "CA-15", "Inicio de sesión: correcto, contraseña errónea y bloqueo tras 5 intentos")
def cp01(cur, ctx):
    assert u(cur, "adquisiciones")["rol"] == "ADQUISICIONES"
    for _ in range(5):
        debe_fallar(lambda: usuarios.iniciar_sesion(cur, "finanzas", "mala"), "incorrectos")
    debe_fallar(lambda: usuarios.iniciar_sesion(cur, "finanzas", generar_datos.PASSWORD_DEMO), "bloqueado")
    cur.execute("UPDATE usuarios SET intentos_fallidos = 0 WHERE usuario = 'finanzas'")


@caso("CP-02", "CA-03", "Registrar compra sin renglones o con cantidad 0 se bloquea con explicación")
def cp02(cur, ctx):
    adq = u(cur, "adquisiciones")
    cur.execute("SELECT id FROM proveedores WHERE rfc = 'CDE020202BB2'")
    ctx["prov"] = cur.fetchone()[0]
    debe_fallar(lambda: compras.registrar_compra(cur, adq, ctx["prov"], "Sistemas", []), "al menos un renglón")
    debe_fallar(lambda: compras.registrar_compra(cur, adq, ctx["prov"], "Sistemas",
                                                 [("Mouse óptico USB", "Pieza", 0, 150)]), "mayores a cero")
    debe_fallar(lambda: compras.registrar_compra(cur, adq, ctx["prov"], "",
                                                 [("Mouse óptico USB", "Pieza", 1, 150)]), "área")


@caso("CP-03", "CA-03", "R1: compra aprobada se registra, genera PDF 001-05 con QR y se envía al proveedor")
def cp03(cur, ctx):
    folio = compras.registrar_compra(cur, u(cur, "adquisiciones"), ctx["prov"], "Departamento de Sistemas y Computación",
                                     [("Mouse óptico USB", "Pieza", 10, 150), ("Cable HDMI 2 m", "Pieza", 5, 180)])
    cur.execute("SELECT id, estatus, ruta_pdf, total FROM ordenes_compra WHERE folio = ?", folio)
    ctx["oc"], est, ruta, ctx["total_oc"] = cur.fetchone()
    ctx["folio_oc"] = folio
    assert est == "ESPERANDO_FACTURA", est
    assert Path(ruta).exists(), "no se generó el PDF de la OC"
    assert ctx["total_oc"] == 2400, ctx["total_oc"]
    assert avisos_con(cur, f"Orden de compra {folio}") >= 1, "no se avisó al proveedor"


@caso("CP-04", "CA-08", "R2: factura con importe distinto se rechaza, abre excepción y avisa al proveedor")
def cp04(cur, ctx):
    lineas = [(l["descripcion"], l["cantidad"], l["precio_unitario"]) for l in compras.lineas_oc(cur, ctx["oc"])]
    xml = generar_xml("CDE020202BB2", "Cómputo Demo", generar_datos.RFC_INSTITUCION, lineas,
                      total_forzado=ctx["total_oc"] + 300)
    res, cods = procesar_factura(cur, xml, "factura_mala.xml", ctx["folio_oc"])
    assert res == "RECHAZADA" and cods == ["IMPORTE_DISTINTO"], cods
    assert avisos_con(cur, f"Factura rechazada · {ctx['folio_oc']}") >= 1
    ctx["lineas"] = lineas


@caso("CP-05", "CA-05", "Almacén no puede recibir el material sin factura válida")
def cp05(cur, ctx):
    debe_fallar(lambda: recepcion.confirmar_recepcion(cur, u(cur, "almacen"), ctx["oc"]), "factura")


@caso("CP-06", "CA-08", "R2: factura correcta se valida y avisa a Almacén")
def cp06(cur, ctx):
    xml = generar_xml("CDE020202BB2", "Cómputo Demo", generar_datos.RFC_INSTITUCION, ctx["lineas"])
    res, cods = procesar_factura(cur, xml, "factura_buena.xml", ctx["folio_oc"])
    assert res == "VALIDA", cods
    assert estatus(cur, ctx["oc"]) == "FACTURA_VALIDADA"
    assert avisos_con(cur, f"Factura validada · {ctx['folio_oc']}") >= 2, "faltó el aviso a Almacén o al proveedor"


@caso("CP-07", "CA-05", "Almacén reporta material incompleto: excepción y aviso a Adquisiciones")
def cp07(cur, ctx):
    alm = u(cur, "almacen")
    debe_fallar(lambda: recepcion.reportar_problema(cur, alm, ctx["oc"], ""), "describa")
    recepcion.reportar_problema(cur, alm, ctx["oc"], "Llegaron 8 mouse de 10")
    assert estatus(cur, ctx["oc"]) == "FACTURA_VALIDADA", "debe seguir esperando el material"
    assert avisos_con(cur, f"Problema en la entrega · {ctx['folio_oc']}") >= 1


@caso("CP-08", "CA-06", "R3: Almacén confirma → entrada/salida, expediente PDF + SHA-256 y envío a Finanzas")
def cp08(cur, ctx):
    ent, sal = recepcion.confirmar_recepcion(cur, u(cur, "almacen"), ctx["oc"], True, "Ya llegaron los 10")
    assert ent.startswith("ENT-") and sal.startswith("SAL-")
    cur.execute("SELECT ruta_pdf, sha256, memorandum FROM expedientes WHERE oc_id = ?", ctx["oc"])
    ruta, sha, mem = cur.fetchone()
    assert Path(ruta).exists() and len(sha) == 64 and mem.startswith("MEM-")
    assert estatus(cur, ctx["oc"]) == "EN_FINANZAS"
    assert any(p["id"] == ctx["oc"] for p in pagos.por_pagar(cur)), "Finanzas no lo ve en su bandeja"
    assert avisos_con(cur, f"Nuevo expediente para pago · {ctx['folio_oc']}") >= 1
    assert avisos_con(cur, "Ticket de pago PAG-") >= 1, "el proveedor no recibió su ticket"


@caso("CP-09", "CA-07", "Finanzas devuelve a Adquisiciones: exige motivo y avisa a Adquisiciones")
def cp09(cur, ctx):
    fin = u(cur, "finanzas")
    debe_fallar(lambda: pagos.devolver(cur, fin, ctx["oc"], ""), "motivo")
    pagos.devolver(cur, fin, ctx["oc"], "La factura no trae el sello del SAT legible")
    assert estatus(cur, ctx["oc"]) == "DEVUELTA"
    assert any(d["id"] == ctx["oc"] for d in pagos.devueltas(cur)), "Adquisiciones no la ve en devueltas"
    assert avisos_con(cur, f"Finanzas devolvió el expediente · {ctx['folio_oc']}") >= 1
    debe_fallar(lambda: pagos.registrar_pago(cur, fin, ctx["oc"], "SPEI123", date.today()), "en finanzas")


@caso("CP-10", "CA-07", "Adquisiciones corrige y reenvía a Finanzas con respuesta; Finanzas recibe aviso")
def cp10(cur, ctx):
    adq = u(cur, "adquisiciones")
    debe_fallar(lambda: pagos.reenviar(cur, adq, ctx["oc"], ""), "corrigió")
    pagos.reenviar(cur, adq, ctx["oc"], "El proveedor envió el PDF con sello legible")
    assert estatus(cur, ctx["oc"]) == "EN_FINANZAS"
    assert avisos_con(cur, f"Expediente corregido · {ctx['folio_oc']}") >= 1
    cur.execute("SELECT COUNT(*) FROM excepciones WHERE oc_id = ? AND tipo = 'DEVUELTA_FINANZAS' AND estatus = 'ABIERTA'",
                ctx["oc"])
    assert cur.fetchone()[0] == 0, "la devolución debe quedar resuelta"


@caso("CP-11", "CA-07", "Finanzas programa la fecha de pago: avisa a Adquisiciones y al proveedor")
def cp11(cur, ctx):
    fin = u(cur, "finanzas")
    debe_fallar(lambda: pagos.programar(cur, fin, ctx["oc"], date.today() - timedelta(days=1)), "anterior")
    pagos.programar(cur, fin, ctx["oc"], date.today() + timedelta(days=3))
    assert avisos_con(cur, f"Pago programado · {ctx['folio_oc']}") >= 1, "no se avisó a Adquisiciones"
    assert avisos_con(cur, "Pago programado · PAG-") >= 1, "no se avisó al proveedor"


@caso("CP-12", "CA-14", "R4: recordatorio a Finanzas y a Adquisiciones por expedientes sin respuesta (1 vez al día)")
def cp12(cur, ctx):
    # Una OC «vieja» en Finanzas sin fecha de pago: se simula que llegó hace 3 días.
    cur.execute("SELECT id FROM ordenes_compra WHERE folio = 'OC-2026-0001'")
    vieja = cur.fetchone()[0]
    cur.execute("UPDATE ordenes_compra SET estatus = 'EN_FINANZAS' WHERE id = ?", vieja)
    cur.execute("INSERT INTO pagos (oc_id, fecha_turno) VALUES (?, DATEADD(DAY, -3, SYSDATETIME()))", vieja)
    assert pagos.recordar_pendientes(cur) == 1
    assert pagos.recordar_pendientes(cur) == 0, "no debe repetir el aviso el mismo día"
    cur.execute("DELETE FROM pagos WHERE oc_id = ?", vieja)
    cur.execute("UPDATE ordenes_compra SET estatus = 'ESPERANDO_FACTURA' WHERE id = ?", vieja)


@caso("CP-13", "CA-10", "R5: conciliación del archivo del banco marca PAGADA; lo no identificado es excepción")
def cp13(cur, ctx):
    carpeta = config.RAIZ / "banco" / "entrada"
    carpeta.mkdir(parents=True, exist_ok=True)
    with open(carpeta / "movimientos_prueba.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "referencia", "concepto", "importe"])
        w.writerow([date.today().isoformat(), "SPEI778899", f"PAGO {ctx['folio_oc']}", f"{ctx['total_oc']:.2f}"])
        w.writerow([date.today().isoformat(), "SPEI000111", "PAGO OC-2026-0999", "123.00"])


@caso("CP-14", "CA-12", "Seguimiento por folio (OC y ticket PAG) muestra «Pagada» y la línea de tiempo")
def cp14(cur, ctx):
    for f in (ctx["folio_oc"], "PAG-" + ctx["folio_oc"][3:]):
        s = consultas.seguimiento(cur, f)
        assert s and s["estatus"] == "Pagada", (f, s and s["estatus"])
        assert len(s["eventos"]) >= 8, len(s["eventos"])
    assert consultas.seguimiento(cur, "OC-2026-9999") is None


@caso("CP-15", "CA-14", "R6: semáforo rojo a 10 días del 15 de diciembre; alerta solo una vez al día")
def cp15(cur, ctx):
    limite = datetime.strptime(db.parametro(cur, "FECHA_LIMITE_PAGOS"), "%Y-%m-%d").date()
    assert (limite.month, limite.day) == (12, 15), limite
    hoy = limite - timedelta(days=10)
    estado = vigilante.estado_cierre(cur, hoy)
    assert estado and all(e["semaforo"] == "ROJO" for e in estado)
    assert vigilante.revisar(cur, hoy) == len(estado)
    assert vigilante.revisar(cur, hoy) == 0
    assert vigilante.estado_cierre(cur, limite - timedelta(days=40))[0]["semaforo"] == "VERDE"


@caso("CP-16", "CA-16", "La bitácora no se puede modificar ni borrar")
def cp16(cur, ctx):
    try:
        cur.execute("DELETE FROM bitacora")
    except Exception:  # noqa: BLE001
        return
    raise AssertionError("se pudo borrar la bitácora")


@caso("CP-18", "RNF-02", "Consulta de folio con 1,000 expedientes simulados en ≤ 2 s")
def cp18(cur, ctx):
    cur.execute("SELECT id FROM proveedores WHERE rfc = 'PDA010101AA1'")
    pid = cur.fetchone()[0]
    for i in range(1000):
        cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, area_solicitante, total, estatus) "
                    "VALUES (?, ?, 'Carga', 100, 'PAGADA')", f"OC-1999-{i:04d}", pid)
        cur.execute("INSERT INTO bitacora (actor, entidad, entidad_id, accion) VALUES ('CARGA', 'OC', SCOPE_IDENTITY(), 'VOLUMEN')")
    t0 = time.perf_counter()
    s = consultas.seguimiento(cur, ctx["folio_oc"])
    seg = time.perf_counter() - t0
    assert s and seg <= 2, f"{seg:.3f} s"
    cur.execute("DELETE FROM ordenes_compra WHERE folio LIKE 'OC-1999-%'")


def main():
    print("Reiniciando la base con datos simulados ...")
    generar_datos.main()
    print()
    ctx = {}
    for c in (cp01, cp02, cp03, cp04, cp05, cp06, cp07, cp08, cp09, cp10, cp11, cp12, cp13):
        c(ctx)
    conciliadas = pagos.conciliar_carpeta()
    with db.conexion() as con:
        ok = estatus(con.cursor(), ctx.get("oc")) == "PAGADA" and len(conciliadas) == 2
    RESULTADOS.append(["CP-13b", "CA-10", "Conciliación: OC PAGADA y 1 movimiento no identificado",
                       "APROBADO" if ok else "FALLIDO", "", "; ".join(conciliadas)])
    print(f"{'✔' if ok else '✘'} CP-13b conciliación: {conciliadas}")
    for c in (cp14, cp15, cp16):
        c(ctx)
    r7 = notificador.enviar_pendientes()
    ok7 = r7["SIMULADA"] > 0 and r7["FALLIDA"] == 0
    RESULTADOS.append(["CP-17", "CA-12", "Robot R7 procesa la cola de avisos (modo simulado)",
                       "APROBADO" if ok7 else "FALLIDO", "", str(r7)])
    print(f"{'✔' if ok7 else '✘'} CP-17  avisos: {r7}")
    cp18(ctx)

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
