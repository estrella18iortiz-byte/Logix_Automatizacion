"""Crea la base logix_db desde cero y la llena con DATOS SIMULADOS.

    python generar_datos.py

1. Corre sql/01_esquema.sql (borra y crea logix_db).
2. Carga parámetros, áreas, usuarios, partidas, conceptos, proveedores y la lista 69-B simulada.
3. Crea 3 requisiciones ya firmadas con su OC «esperando factura».
4. Fabrica facturas XML de prueba (buenas y malas) en datos_prueba/facturas/.

Todos los nombres, RFC e importes son ficticios (regla de la guía: no usar datos reales).
Contraseña de todos los usuarios de prueba: logix2026
"""
import csv
import secrets
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyodbc

from logix import config
from logix.cfdi_simulado import generar_xml
from logix.seguridad import generar_hash

RAIZ = Path(__file__).resolve().parent
PASSWORD_DEMO = "logix2026"
RFC_INSTITUCION = "ITM990101AB1"      # simulado

PARAMETROS = [
    ("RFC_INSTITUCION", RFC_INSTITUCION, "RFC al que deben emitirse las facturas (simulado)"),
    ("FECHA_LIMITE_PAGOS", f"{date.today().year}-12-11", "Último día para pagar con el presupuesto del ejercicio"),
    ("DIAS_SEMAFORO_ROJO", "15", "Días antes del cierre para marcar en rojo"),
    ("DIAS_SEMAFORO_AMARILLO", "30", "Días antes del cierre para marcar en amarillo"),
    ("HORAS_RECORDATORIO", "24", "Horas sin firmar para mandar recordatorio"),
    ("HORAS_ESCALAMIENTO", "48", "Horas sin firmar para avisar al jefe inmediato"),
    ("UMBRAL_COTIZACIONES", "300000", "Monto a partir del cual se exigen cotizaciones"),
    ("PUNTAJE_MINIMO", "70", "Puntaje mínimo de evaluación del proveedor (001-02)"),
]

AREAS = ["Departamento de Sistemas y Computación", "Departamento de Ciencias Básicas",
         "Planeación y Presupuestos", "Subdirección Académica", "Dirección",
         "Recursos Materiales y Servicios", "Subdirección de Servicios Administrativos",
         "Recursos Financieros"]

# (usuario, nombre simulado, rol, área)
USUARIOS = [
    ("solicitante", "Ana Demo Solicitante", "SOLICITANTE", "Departamento de Sistemas y Computación"),
    ("jefe.area", "Luis Demo Jefe de Área", "JEFE_AREA", "Departamento de Sistemas y Computación"),
    ("presupuestos", "Marta Demo Presupuestos", "PRESUPUESTOS", "Planeación y Presupuestos"),
    ("subdirector", "Jorge Demo Subdirector", "SUBDIRECTOR", "Subdirección Académica"),
    ("director", "Elena Demo Directora", "DIRECTOR", "Dirección"),
    ("adquisiciones", "Patricia Demo Adquisiciones", "ADQUISICIONES", "Recursos Materiales y Servicios"),
    ("jefe.rm", "Raúl Demo Jefe RM", "JEFE_RM", "Recursos Materiales y Servicios"),
    ("subdir.admin", "Sofía Demo Subdirectora Adm.", "SUBDIR_ADMIN", "Subdirección de Servicios Administrativos"),
    ("almacen", "Luis Alberto Demo Almacén", "ALMACEN", "Recursos Materiales y Servicios"),
    ("finanzas", "Gabriela Demo Finanzas", "FINANZAS", "Recursos Financieros"),
    ("admin", "Administrador Logix", "ADMIN", None),
]

PARTIDAS = [("21101", "Materiales y útiles de oficina", 50000),
            ("21401", "Materiales y útiles para tecnologías de la información", 60000),
            ("24601", "Material eléctrico y electrónico", 20000)]

# (descripción, unidad, partida, precio de referencia con IVA)
CONCEPTOS = [("Plumones para pizarrón blanco (caja con 4)", "Caja", "21101", 95),
             ("Hojas blancas tamaño carta (paquete 500)", "Paquete", "21101", 120),
             ("Mouse óptico USB", "Pieza", "21401", 150),
             ("Tóner para impresora láser", "Pieza", "21401", 1450),
             ("Cable HDMI 2 m", "Pieza", "21401", 180),
             ("Foco LED 9 W", "Pieza", "24601", 45)]

hoy = date.today()
# (razón social, RFC, puntaje selección, puntaje evaluación, fecha evaluación)
PROVEEDORES = [
    ("Papelería Demo del Altiplano S.A. de C.V.", "PDA010101AA1", 85, 88, hoy - timedelta(days=200)),
    ("Cómputo Demo S.A. de C.V.", "CDE020202BB2", 90, 91, hoy - timedelta(days=120)),
    ("Comercial Demo S.A. de C.V.", "COD030303CC3", 75, 62, hoy - timedelta(days=90)),      # no apto (62)
    ("Eléctrica Demo S.A. de C.V.", "ELD040404DD4", 80, 85, hoy - timedelta(days=400)),     # evaluación vencida
    ("Distribuidora Fantasma S.A. de C.V.", "DFA050505EE5", 78, 80, hoy - timedelta(days=60)),  # en lista 69-B
]
LISTA_69B = [("DFA050505EE5", "Definitivo")]

FLUJOS = [("REQ", 1, "JEFE_AREA"), ("REQ", 2, "PRESUPUESTOS"), ("REQ", 3, "SUBDIRECTOR"), ("REQ", 4, "DIRECTOR"),
          ("OC", 1, "ADQUISICIONES"), ("OC", 2, "JEFE_RM"), ("OC", 3, "SUBDIR_ADMIN"),
          ("PAGO", 1, "ADQUISICIONES"), ("PAGO", 2, "JEFE_RM"), ("PAGO", 3, "SUBDIR_ADMIN")]

# Compras ya firmadas, con OC esperando factura: (folio REQ, folio OC, RFC proveedor, [(concepto, cantidad)])
COMPRAS = [
    ("REQ-2026-0001", "OC-2026-0001", "PDA010101AA1",
     [("Plumones para pizarrón blanco (caja con 4)", 10), ("Hojas blancas tamaño carta (paquete 500)", 5)]),
    ("REQ-2026-0002", "OC-2026-0002", "CDE020202BB2",
     [("Mouse óptico USB", 2), ("Tóner para impresora láser", 1)]),
    ("REQ-2026-0003", "OC-2026-0003", "DFA050505EE5",
     [("Cable HDMI 2 m", 3)]),
]


def crear_esquema():
    """Corre sql/01_esquema.sql por lotes (separados por GO) con pyodbc; no necesita sqlcmd."""
    print("1/4  Creando la base logix_db ...")
    texto = (RAIZ / "sql" / "01_esquema.sql").read_text(encoding="utf-8")
    lotes = [l.strip() for l in re.split(r"^\s*GO\s*$", texto, flags=re.MULTILINE | re.IGNORECASE) if l.strip()]
    try:
        con = pyodbc.connect(config.cadena_conexion("master"), autocommit=True)
    except pyodbc.Error as e:
        sys.exit(f"No pude conectarme a SQL Server «{config.SQL_SERVER}» con el driver «{config.SQL_DRIVER}».\n"
                 f"Revisa LOGIX_SQL_SERVER en .env (o corre verificar_instalacion.py).\n{e}")
    cur = con.cursor()
    cur.execute("SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON;")   # válido para toda la sesión
    for lote in lotes:
        try:
            cur.execute(lote)
            while cur.nextset():
                pass
        except pyodbc.Error as e:
            con.close()
            sys.exit(f"Error al crear el esquema en el lote:\n{lote[:300]}\n{e}")
    con.close()


_usados = set()


def codigo_telegram() -> str:
    """Código de 6 dígitos para vincular un chat de Telegram (se usa una sola vez)."""
    while True:
        c = f"{secrets.randbelow(1_000_000):06d}"
        if c not in _usados:
            _usados.add(c)
            return c


def cargar_catalogos(cur):
    print("2/4  Cargando catálogos ...")
    cur.executemany("INSERT INTO parametros VALUES (?, ?, ?)", PARAMETROS)
    for a in AREAS:
        cur.execute("INSERT INTO areas (nombre) VALUES (?)", a)
    for usuario, nombre, rol, area in USUARIOS:
        h, sal = generar_hash(PASSWORD_DEMO)
        cur.execute("INSERT INTO usuarios (nombre, usuario, hash_password, sal, rol, area_id, codigo_telegram) "
                    "VALUES (?, ?, ?, ?, ?, (SELECT id FROM areas WHERE nombre = ?), ?)",
                    nombre, usuario, h, sal, rol, area, codigo_telegram())
    cur.executemany("INSERT INTO partidas (clave, descripcion, saldo) VALUES (?, ?, ?)", PARTIDAS)
    for desc, unidad, partida, precio in CONCEPTOS:
        cur.execute("INSERT INTO conceptos (descripcion, unidad, partida_id, precio_referencia) "
                    "VALUES (?, ?, (SELECT id FROM partidas WHERE clave = ?), ?)", desc, unidad, partida, precio)
    for razon, rfc, sel, ev, fecha in PROVEEDORES:
        correo = f"facturacion@{rfc.lower()}.demo"
        cur.execute("INSERT INTO proveedores (razon_social, rfc, correo, puntaje_seleccion, puntaje_evaluacion, "
                    "fecha_evaluacion, codigo_telegram) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    razon, rfc, correo, sel, ev, fecha, codigo_telegram())
    cur.executemany("INSERT INTO sat_lista_69b VALUES (?, ?)", LISTA_69B)
    cur.executemany("INSERT INTO flujos_aprobacion VALUES (?, ?, ?)", FLUJOS)


def crear_compras(cur) -> dict:
    """Crea requisiciones firmadas y su OC esperando factura. Regresa {folio_oc: datos}."""
    print("3/4  Creando requisiciones y órdenes de compra ...")
    ocs = {}
    cur.execute("SELECT id, area_id FROM usuarios WHERE usuario = 'solicitante'")
    sol_id, area_id = cur.fetchone()
    hace = datetime.now() - timedelta(days=6)
    for folio_req, folio_oc, rfc, lineas in COMPRAS:
        cur.execute("INSERT INTO requisiciones (folio, area_id, solicitante_id, justificacion, estatus, fecha) "
                    "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, 'EN_OC', ?)",
                    folio_req, area_id, sol_id, "Material para el semestre (dato simulado)", hace)
        req_id = cur.fetchone()[0]
        total = Decimal("0")
        detalle = []
        for concepto, cant in lineas:
            cur.execute("SELECT id, precio_referencia FROM conceptos WHERE descripcion = ?", concepto)
            c_id, precio = cur.fetchone()
            cur.execute("INSERT INTO requisicion_detalle (requisicion_id, concepto_id, cantidad, precio_unitario) "
                        "VALUES (?, ?, ?, ?)", req_id, c_id, cant, precio)
            total += Decimal(cant) * Decimal(precio)
            detalle.append((concepto, Decimal(cant), Decimal(precio)))
        cur.execute("UPDATE requisiciones SET total = ? WHERE id = ?", total, req_id)

        cur.execute("SELECT id, razon_social FROM proveedores WHERE rfc = ?", rfc)
        prov_id, razon = cur.fetchone()
        cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, total, estatus, fecha) "
                    "OUTPUT INSERTED.id VALUES (?, ?, ?, 'ESPERANDO_FACTURA', ?)",
                    folio_oc, prov_id, total, hace + timedelta(days=2))
        oc_id = cur.fetchone()[0]
        cur.execute("INSERT INTO oc_requisiciones VALUES (?, ?)", oc_id, req_id)

        # Firmas ya completas (se crearon «en el pasado» para la demo).
        for tipo, ref in (("REQ", req_id), ("OC", oc_id)):
            cur.execute("SELECT nivel, rol FROM flujos_aprobacion WHERE tipo = ? ORDER BY nivel", tipo)
            for nivel, rol in cur.fetchall():
                cur.execute("INSERT INTO aprobaciones (tipo, referencia_id, nivel, rol, estatus, usuario_id, "
                            "fecha_asignacion, fecha_respuesta) VALUES (?, ?, ?, ?, 'APROBADA', "
                            "(SELECT TOP 1 id FROM usuarios WHERE rol = ?), ?, ?)",
                            tipo, ref, nivel, rol, rol, hace, hace + timedelta(hours=nivel * 3))
        cur.execute("INSERT INTO bitacora (actor, entidad, entidad_id, accion, valor_nuevo, detalle) "
                    "VALUES ('GENERADOR', 'OC', ?, 'DATOS_SIMULADOS', 'ESPERANDO_FACTURA', ?)",
                    oc_id, f"{folio_oc} creada para pruebas")
        ocs[folio_oc] = {"rfc": rfc, "razon": razon, "total": total, "detalle": detalle}
    return ocs


def fabricar_facturas(ocs: dict):
    """Facturas de prueba: una por cada caso que el robot R3 debe detectar."""
    print("4/4  Fabricando facturas XML de prueba ...")
    carpeta = RAIZ / "datos_prueba" / "facturas"
    carpeta.mkdir(parents=True, exist_ok=True)
    for f in carpeta.glob("*"):
        f.unlink()

    oc1, oc2, oc3 = ocs["OC-2026-0001"], ocs["OC-2026-0002"], ocs["OC-2026-0003"]
    uuid_repetido = "11111111-2222-4333-8444-555555555555"
    casos = [
        # (archivo, folio OC que pone el proveedor en el asunto, xml, resultado esperado, regla)
        ("01_correcta.xml", "OC-2026-0001",
         generar_xml(oc1["rfc"], oc1["razon"], RFC_INSTITUCION, oc1["detalle"], "101", uuid=uuid_repetido),
         "VALIDA", "—"),
        ("02_importe_distinto.xml", "OC-2026-0002",
         generar_xml(oc2["rfc"], oc2["razon"], RFC_INSTITUCION, oc2["detalle"], "202",
                     total_forzado=oc2["total"] + 100), "RECHAZADA", "IMPORTE_DISTINTO"),
        ("03_otro_proveedor.xml", "OC-2026-0002",
         generar_xml("COD030303CC3", "Comercial Demo S.A. de C.V.", RFC_INSTITUCION, oc2["detalle"], "303"),
         "RECHAZADA", "RFC_EMISOR"),
        ("04_receptor_equivocado.xml", "OC-2026-0002",
         generar_xml(oc2["rfc"], oc2["razon"], "XAXX010101000", oc2["detalle"], "404"),
         "RECHAZADA", "RFC_RECEPTOR"),
        ("05_proveedor_69b.xml", "OC-2026-0003",
         generar_xml(oc3["rfc"], oc3["razon"], RFC_INSTITUCION, oc3["detalle"], "505"),
         "RECHAZADA", "SAT_69B"),
        ("06_duplicada.xml", "OC-2026-0001",
         generar_xml(oc1["rfc"], oc1["razon"], RFC_INSTITUCION, oc1["detalle"], "101", uuid=uuid_repetido),
         "RECHAZADA", "UUID_DUPLICADO / OC_NO_ESPERA_FACTURA"),
        ("07_oc_inexistente.xml", "OC-2026-9999",
         generar_xml(oc2["rfc"], oc2["razon"], RFC_INSTITUCION, oc2["detalle"], "707"),
         "RECHAZADA", "OC_INEXISTENTE"),
        ("08_no_es_cfdi.xml", "OC-2026-0002", b"esto no es una factura", "RECHAZADA", "CFDI_INVALIDO"),
        ("09_correcta_oc2.xml", "OC-2026-0002",
         generar_xml(oc2["rfc"], oc2["razon"], RFC_INSTITUCION, oc2["detalle"], "909"), "VALIDA", "—"),
    ]
    with open(carpeta / "casos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["orden", "archivo", "folio_oc", "resultado_esperado", "regla"])
        for i, (archivo, folio, xml, esperado, regla) in enumerate(casos, 1):
            (carpeta / archivo).write_bytes(xml)
            w.writerow([i, archivo, folio, esperado, regla])
    print(f"     {len(casos)} facturas en {carpeta}")


def main():
    crear_esquema()
    con = pyodbc.connect(config.cadena_conexion(), autocommit=False)
    cur = con.cursor()
    try:
        cargar_catalogos(cur)
        ocs = crear_compras(cur)
        con.commit()
    finally:
        con.close()
    fabricar_facturas(ocs)
    print(f"\nListo. Usuarios de prueba (contraseña «{PASSWORD_DEMO}»): "
          + ", ".join(u[0] for u in USUARIOS))


if __name__ == "__main__":
    main()
