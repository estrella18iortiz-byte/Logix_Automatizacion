"""Casos de prueba de punta a punta (E4) del diagrama del 19-nov-2026, con datos simulados.

    python probar_flujo_completo.py

Reinicia la base (generar_datos), ejecuta cada caso y guarda la evidencia en
resultados/resultados_pruebas.csv (id, criterio de aceptación, resultado y tiempo).

Recorre TODAS las ramas del diagrama:
  · material: recordatorio día 3, último aviso 5 h antes, cancelación día 7, devolución con razón
  · factura: 48 h sin factura, factura inválida (cancela y devuelve material), factura antes del material
  · pago: banco confirma, error general con 3 reintentos, saldo insuficiente, monto, divisa,
          CLABE inválida, pago duplicado; Finanzas reintenta o cancela
"""
import csv
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import generar_datos
from logix import (banco_emulado, cancelacion, compras, consultas, notificador, pagos, plazos, recepcion,
                   usuarios)
from logix import db
from logix.cfdi_simulado import generar_xml
from logix.errores import ReglaNegocio
from logix.robot_facturas import procesar_factura

RAIZ = Path(__file__).resolve().parent
RESULTADOS = []
RFC_PROV = "CDE020202BB2"          # Cómputo Demo (proveedor fijo)


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
            print(f"{'✔' if ok else '✘'} {cid:6} {criterio:7} {descripcion[:74]:74} {seg:5.2f}s {nota[:80]}")
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


def nueva_oc(cur, lineas=None, rfc=RFC_PROV) -> tuple[int, str]:
    """Registra una compra aprobada (robot R1) y regresa (id, folio)."""
    adq = u(cur, "adquisiciones")
    cur.execute("SELECT id FROM proveedores WHERE rfc = ?", rfc)
    folio = compras.registrar_compra(cur, adq, cur.fetchone()[0], "Departamento de Sistemas",
                                     lineas or [("Mouse óptico USB", "Pieza", 4, 150)])
    cur.execute("SELECT id FROM ordenes_compra WHERE folio = ?", folio)
    return cur.fetchone()[0], folio


def factura(cur, oc_id, folio, rfc=RFC_PROV, **kw):
    """El proveedor manda su factura XML (robot R2). kw: total_forzado, moneda..."""
    lineas = [(l["descripcion"], l["cantidad"], l["precio_unitario"]) for l in compras.lineas_oc(cur, oc_id)]
    xml = generar_xml(rfc, "Proveedor Demo", generar_datos.RFC_INSTITUCION, lineas, **kw)
    return procesar_factura(cur, xml, f"{folio}.xml", folio)


def atrasar_oc(cur, oc_id, **delta):
    cur.execute("UPDATE ordenes_compra SET fecha = ? WHERE id = ?", datetime.now() - timedelta(**delta), oc_id)


# ======================================================================= inicio
@caso("CP-01", "CA-15", "Inicio de sesión: correcto, contraseña errónea y bloqueo tras 5 intentos")
def cp01(cur, ctx):
    assert u(cur, "adquisiciones")["rol"] == "ADQUISICIONES"
    for _ in range(5):
        debe_fallar(lambda: usuarios.iniciar_sesion(cur, "finanzas", "mala"), "incorrectos")
    debe_fallar(lambda: usuarios.iniciar_sesion(cur, "finanzas", generar_datos.PASSWORD_DEMO), "bloqueado")
    cur.execute("UPDATE usuarios SET intentos_fallidos = 0 WHERE usuario = 'finanzas'")


@caso("CP-02", "CA-03", "Registrar compra sin renglones, con cantidad 0 o sin área se bloquea con explicación")
def cp02(cur, ctx):
    adq = u(cur, "adquisiciones")
    cur.execute("SELECT id FROM proveedores WHERE rfc = ?", RFC_PROV)
    prov = cur.fetchone()[0]
    debe_fallar(lambda: compras.registrar_compra(cur, adq, prov, "Sistemas", []), "al menos un renglón")
    debe_fallar(lambda: compras.registrar_compra(cur, adq, prov, "Sistemas", [("Mouse", "Pieza", 0, 150)]),
                "mayores a cero")
    debe_fallar(lambda: compras.registrar_compra(cur, adq, prov, "", [("Mouse", "Pieza", 1, 150)]), "área")


@caso("CP-03", "CA-03", "R1: la compra aprobada genera la OC en PDF con QR y se manda al proveedor")
def cp03(cur, ctx):
    oc_id, folio = nueva_oc(cur, [("Mouse óptico USB", "Pieza", 10, 150), ("Cable HDMI 2 m", "Pieza", 5, 180)])
    cur.execute("SELECT estatus, ruta_pdf, total FROM ordenes_compra WHERE id = ?", oc_id)
    est, ruta, total = cur.fetchone()
    assert est == "ESPERANDO_MATERIAL", est
    assert Path(ruta).exists(), "no se generó el PDF de la OC"
    assert total == 2400, total
    assert avisos_con(cur, f"Orden de compra {folio}") >= 1, "no se avisó al proveedor"
    ctx["oc_plazos"] = (oc_id, folio)


# ======================================================================= material
@caso("CP-04", "CA-14", "R3: al día 3 se le recuerda al proveedor mandar el material (una sola vez)")
def cp04(cur, ctx):
    oc_id, folio = ctx["oc_plazos"]
    atrasar_oc(cur, oc_id, days=3, hours=1)
    assert plazos.revisar(cur)["recordatorios"] >= 1
    assert avisos_con(cur, f"Recordatorio · {folio}") >= 1
    assert plazos.revisar(cur)["recordatorios"] == 0, "no debe repetir el recordatorio"


@caso("CP-05", "CA-14", "R3: 5 horas antes del día 7 se avisa al proveedor que se va a cancelar (una vez)")
def cp05(cur, ctx):
    oc_id, folio = ctx["oc_plazos"]
    atrasar_oc(cur, oc_id, days=7, hours=-4)          # faltan 4 horas para el día 7
    assert plazos.revisar(cur)["avisos_cancelacion"] == 1
    assert avisos_con(cur, f"Último aviso · {folio}") >= 1
    assert plazos.revisar(cur)["avisos_cancelacion"] == 0
    assert estatus(cur, oc_id) == "ESPERANDO_MATERIAL", "todavía no debe cancelarse"


@caso("CP-06", "CA-14", "R3: al día 7 sin material la compra se cancela sola; avisa a proveedor y Adquisiciones")
def cp06(cur, ctx):
    oc_id, folio = ctx["oc_plazos"]
    atrasar_oc(cur, oc_id, days=7, minutes=1)
    assert plazos.revisar(cur)["cancelaciones"] >= 1
    cur.execute("SELECT estatus, tipo_cancelacion, material_por_devolver FROM ordenes_compra WHERE id = ?", oc_id)
    assert tuple(cur.fetchone()) == ("CANCELADA", "MATERIAL_NO_LLEGO", False)
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE asunto = ? AND mensaje LIKE '%ya no lo envíe%'",
                f"Compra cancelada · {folio}")
    assert cur.fetchone()[0] >= 1, "faltó el aviso al proveedor"
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE asunto = ? AND mensaje LIKE 'Logix canceló%'",
                f"Compra cancelada · {folio}")
    assert cur.fetchone()[0] >= 1, "faltó el aviso a Adquisiciones"


@caso("CP-07", "CA-05", "Jefe de Almacén: «Devolución» exige razón, cancela y avisa a Adquisiciones y proveedor")
def cp07(cur, ctx):
    oc_id, folio = nueva_oc(cur)
    alm = u(cur, "almacen")
    debe_fallar(lambda: recepcion.devolucion(cur, alm, oc_id, ""), "razón")
    recepcion.devolucion(cur, alm, oc_id, "Llegaron 2 mouse rotos y faltan 2")
    cur.execute("SELECT estatus, tipo_cancelacion, motivo_cancelacion FROM ordenes_compra WHERE id = ?", oc_id)
    est, tipo, motivo = cur.fetchone()
    assert (est, tipo) == ("CANCELADA", "DEVOLUCION_ALMACEN") and "rotos" in motivo
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE asunto = ? AND mensaje LIKE '%rotos%'",
                f"Compra cancelada · {folio}")
    assert cur.fetchone()[0] >= 2, "la razón no les llegó a Adquisiciones y al proveedor"
    debe_fallar(lambda: recepcion.confirmar_recepcion(cur, alm, oc_id), "no está esperando material")


@caso("CP-08", "CA-05", "Jefe de Almacén: «Llegó bien» → entrada/salida y se le pide la factura al proveedor")
def cp08(cur, ctx):
    oc_id, folio = nueva_oc(cur)
    ent, sal = recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    assert ent.startswith("ENT-") and sal.startswith("SAL-")
    assert estatus(cur, oc_id) == "MATERIAL_RECIBIDO"
    assert avisos_con(cur, f"Envíe su factura · {folio}") >= 1, "no se le pidió la factura"
    ctx["oc_sin_factura"] = (oc_id, folio)


# ======================================================================= factura
@caso("CP-09", "CA-08", "R3: 48 h sin factura → compra cancelada y material por devolver; Almacén lo devuelve")
def cp09(cur, ctx):
    oc_id, folio = ctx["oc_sin_factura"]
    atrasar_oc(cur, oc_id, hours=72)          # la OC se envió hace 3 días y el material llegó hace 49 h
    cur.execute("UPDATE recepciones SET fecha_recepcion = DATEADD(HOUR, -49, SYSDATETIME()) WHERE oc_id = ?", oc_id)
    assert plazos.revisar(cur)["cancelaciones"] >= 1
    cur.execute("SELECT tipo_cancelacion, material_por_devolver FROM ordenes_compra WHERE id = ?", oc_id)
    assert tuple(cur.fetchone()) == ("FACTURA_NO_LLEGO", True)
    assert any(d["id"] == oc_id for d in recepcion.por_devolver(cur))
    assert avisos_con(cur, f"Material por devolver · {folio}") >= 1, "Almacén no recibió el aviso"
    cancelacion.marcar_material_devuelto(cur, u(cur, "almacen"), oc_id)
    assert not any(d["id"] == oc_id for d in recepcion.por_devolver(cur))


@caso("CP-10", "CA-08", "R2: factura inválida → compra cancelada, material devuelto y aviso al proveedor")
def cp10(cur, ctx):
    oc_id, folio = nueva_oc(cur)
    recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    res, cods = factura(cur, oc_id, folio, total_forzado=Decimal("999.99"))
    assert res == "RECHAZADA" and cods == ["IMPORTE_DISTINTO"], cods
    cur.execute("SELECT estatus, tipo_cancelacion, material_por_devolver FROM ordenes_compra WHERE id = ?", oc_id)
    assert tuple(cur.fetchone()) == ("CANCELADA", "FACTURA_INVALIDA", True)
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE asunto = ? AND mensaje LIKE '%se le devolverá%'",
                f"Compra cancelada · {folio}")
    assert cur.fetchone()[0] >= 1, "el proveedor no recibió el motivo"
    cur.execute("SELECT COUNT(*) FROM pagos WHERE oc_id = ?", oc_id)
    assert cur.fetchone()[0] == 0, "¡no debe llegar a pago!"


# ======================================================================= pago
@caso("CP-11", "CA-07", "Camino feliz: material + factura válida → expediente SHA-256 → banco confirma → PAGADA")
def cp11(cur, ctx):
    saldo_antes = banco_emulado.estado(cur)["saldo"]
    oc_id, folio = nueva_oc(cur)
    recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    res, cods = factura(cur, oc_id, folio)
    assert res == "VALIDA", cods
    cur.execute("SELECT ruta_pdf, sha256 FROM expedientes WHERE oc_id = ?", oc_id)
    ruta, sha = cur.fetchone()
    assert Path(ruta).exists() and len(sha) == 64
    assert estatus(cur, oc_id) == "PAGADA"
    cur.execute("SELECT referencia_banco, intentos FROM pagos WHERE oc_id = ?", oc_id)
    ref, intentos = cur.fetchone()
    assert ref.startswith("SPEI-") and intentos == 1
    assert banco_emulado.estado(cur)["saldo"] == saldo_antes - 600, "el banco no descontó el pago"
    for asunto in (f"Nuevo expediente para pago · {folio}", f"Pago confirmado · {folio}", f"Compra pagada · {folio}"):
        assert avisos_con(cur, asunto) >= 1, f"falta el aviso «{asunto}»"
    ctx["oc_pagada"] = (oc_id, folio)


@caso("CP-12", "CA-08", "La factura puede llegar antes que el material: al confirmar el material se paga solo")
def cp12(cur, ctx):
    oc_id, folio = nueva_oc(cur)
    res, _ = factura(cur, oc_id, folio)
    assert res == "VALIDA" and estatus(cur, oc_id) == "ESPERANDO_MATERIAL"
    recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    assert estatus(cur, oc_id) == "PAGADA"
    assert avisos_con(cur, f"Envíe su factura · {folio}") == 0, "no debe pedir una factura que ya llegó"


@caso("CP-13", "CA-10", "Banco «error general»: 3 intentos automáticos → error a Finanzas → Finanzas reintenta")
def cp13(cur, ctx):
    banco_emulado.simular_falla(cur, "ERROR_GENERAL")
    oc_id, folio = nueva_oc(cur)
    recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    factura(cur, oc_id, folio)
    cur.execute("SELECT estatus, intentos FROM pagos WHERE oc_id = ?", oc_id)
    assert tuple(cur.fetchone()) == ("REINTENTO", 1)
    pagos.reintentar_pendientes(cur)                      # vuelta del robot (intento 2)
    pagos.reintentar_pendientes(cur)                      # vuelta del robot (intento 3)
    cur.execute("SELECT estatus, intentos, codigo_error FROM pagos WHERE oc_id = ?", oc_id)
    assert tuple(cur.fetchone()) == ("ERROR", 3, "ERROR_GENERAL")
    assert estatus(cur, oc_id) == "PAGO_CON_ERROR"
    assert avisos_con(cur, f"Error del banco · {folio}") >= 1, "Finanzas no fue avisada"
    assert avisos_con(cur, "Pago en proceso · PAG-") >= 1, "el proveedor no recibió «pago en proceso»"
    banco_emulado.simular_falla(cur, "NINGUNA")
    assert pagos.reintentar(cur, u(cur, "finanzas"), oc_id) == "CONFIRMADO"
    assert estatus(cur, oc_id) == "PAGADA"


@caso("CP-14", "CA-10", "Banco «saldo insuficiente»: no reintenta; Finanzas cancela con motivo y se avisa")
def cp14(cur, ctx):
    cur.execute("UPDATE banco_cuenta SET saldo = 100 WHERE id = 1")
    oc_id, folio = nueva_oc(cur)
    recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    factura(cur, oc_id, folio)
    cur.execute("SELECT estatus, codigo_error FROM pagos WHERE oc_id = ?", oc_id)
    assert tuple(cur.fetchone()) == ("ERROR", "SALDO_INSUFICIENTE")
    assert pagos.reintentar_pendientes(cur) == 0, "este error no se reintenta solo"
    fin = u(cur, "finanzas")
    debe_fallar(lambda: pagos.cancelar_pago(cur, fin, oc_id, ""), "razón")
    pagos.cancelar_pago(cur, fin, oc_id, "Sin presupuesto disponible en la partida")
    cur.execute("SELECT estatus, tipo_cancelacion, material_por_devolver FROM ordenes_compra WHERE id = ?", oc_id)
    assert tuple(cur.fetchone()) == ("CANCELADA", "PAGO_CANCELADO", True)
    assert avisos_con(cur, f"Compra cancelada · {folio}") >= 2, "faltó avisar al proveedor o a Adquisiciones"
    banco_emulado.depositar(cur, Decimal("250000"))


@caso("CP-15", "CA-10", "Banco «CLABE inválida»: se le pide al proveedor; Finanzas la corrige y reintenta")
def cp15(cur, ctx):
    cur.execute("UPDATE proveedores SET clabe = '014700009876543210' WHERE rfc = ?", RFC_PROV)  # dígito malo
    oc_id, folio = nueva_oc(cur)
    recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    factura(cur, oc_id, folio)
    cur.execute("SELECT codigo_error FROM pagos WHERE oc_id = ?", oc_id)
    assert cur.fetchone()[0] == "CUENTA_INVALIDA"
    assert avisos_con(cur, "Pago detenido · PAG-") >= 1, "no se le pidió la CLABE al proveedor"
    fin = u(cur, "finanzas")
    debe_fallar(lambda: pagos.corregir_clabe(cur, fin, oc_id, "123"), "18 dígitos")
    base = "01470000987654321"
    pagos.corregir_clabe(cur, fin, oc_id, base + banco_emulado.digito_verificador(base))
    assert pagos.reintentar(cur, fin, oc_id) == "CONFIRMADO"


@caso("CP-16", "CA-10", "Banco «divisa equivocada»: factura en USD → error para Finanzas (no se paga)")
def cp16(cur, ctx):
    oc_id, folio = nueva_oc(cur)
    recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    factura(cur, oc_id, folio, moneda="USD")
    cur.execute("SELECT estatus, codigo_error FROM pagos WHERE oc_id = ?", oc_id)
    assert tuple(cur.fetchone()) == ("ERROR", "DIVISA_INCORRECTA")
    assert estatus(cur, oc_id) == "PAGO_CON_ERROR"


@caso("CP-17", "CA-10", "Banco «monto equivocado»: pasa el límite por operación → error para Finanzas")
def cp17(cur, ctx):
    oc_id, folio = nueva_oc(cur, [("Servidor de cómputo", "Pieza", 1, 150000)])
    recepcion.confirmar_recepcion(cur, u(cur, "almacen"), oc_id)
    factura(cur, oc_id, folio)
    cur.execute("SELECT codigo_error FROM pagos WHERE oc_id = ?", oc_id)
    assert cur.fetchone()[0] == "MONTO_INCORRECTO"


@caso("CP-18", "CA-10", "Banco «pago duplicado»: la misma OC no se paga dos veces (no descuenta saldo)")
def cp18(cur, ctx):
    oc_id, folio = ctx["oc_pagada"]
    saldo = banco_emulado.estado(cur)["saldo"]
    cur.execute("SELECT referencia_banco FROM pagos WHERE oc_id = ?", oc_id)
    clave = cur.fetchone()[0]
    cur.execute("SELECT clabe FROM proveedores WHERE rfc = ?", RFC_PROV)
    r = banco_emulado.transferir(cur, folio, cur.fetchone()[0], Decimal("600"), "MXN")
    assert r.codigo == "PAGO_DUPLICADO" and r.clave_rastreo == clave and r.confirmado
    assert banco_emulado.estado(cur)["saldo"] == saldo


# ======================================================================= consulta y controles
@caso("CP-19", "CA-12", "Seguimiento por folio (OC y PAG): «Pagada» con línea de tiempo; cancelada con motivo")
def cp19(cur, ctx):
    oc_id, folio = ctx["oc_pagada"]
    for f in (folio, "PAG-" + folio[3:]):
        s = consultas.seguimiento(cur, f)
        assert s and s["estatus"] == "Pagada" and s["etapa"] == 4, (f, s and s["estatus"])
        assert len(s["eventos"]) >= 6, len(s["eventos"])
    s = consultas.seguimiento(cur, ctx["oc_plazos"][1])
    assert s["etapa"] is None and "días" in s["motivo_cancelacion"]
    assert consultas.seguimiento(cur, "OC-2026-9999") is None


@caso("CP-20", "CA-16", "La bitácora no se puede modificar ni borrar")
def cp20(cur, ctx):
    try:
        cur.execute("DELETE FROM bitacora")
    except Exception:  # noqa: BLE001
        return
    raise AssertionError("se pudo borrar la bitácora")


@caso("CP-22", "RNF-02", "Consulta de folio con 1,000 órdenes simuladas en ≤ 2 s")
def cp22(cur, ctx):
    cur.execute("SELECT id FROM proveedores WHERE rfc = 'PDA010101AA1'")
    pid = cur.fetchone()[0]
    for i in range(1000):
        cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, area_solicitante, total, estatus) "
                    "VALUES (?, ?, 'Carga', 100, 'PAGADA')", f"OC-1999-{i:04d}", pid)
        cur.execute("INSERT INTO bitacora (actor, entidad, entidad_id, accion) VALUES ('CARGA', 'OC', SCOPE_IDENTITY(), 'VOLUMEN')")
    t0 = time.perf_counter()
    s = consultas.seguimiento(cur, ctx["oc_pagada"][1])
    seg = time.perf_counter() - t0
    assert s and seg <= 2, f"{seg:.3f} s"
    cur.execute("DELETE FROM ordenes_compra WHERE folio LIKE 'OC-1999-%'")


def main():
    print("Reiniciando la base con datos simulados ...")
    generar_datos.main()
    print()
    ctx = {}
    for c in (cp01, cp02, cp03, cp04, cp05, cp06, cp07, cp08, cp09, cp10, cp11, cp12, cp13, cp14, cp15, cp16,
              cp17, cp18, cp19, cp20):
        c(ctx)
    r6 = notificador.enviar_pendientes()
    ok6 = r6["SIMULADA"] > 0 and r6["FALLIDA"] == 0
    RESULTADOS.append(["CP-21", "CA-12", "Robot R6 procesa la cola de avisos por correo y Telegram (modo simulado)",
                       "APROBADO" if ok6 else "FALLIDO", "", str(r6)])
    print(f"{'✔' if ok6 else '✘'} CP-21  avisos: {r6}")
    cp22(ctx)

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
