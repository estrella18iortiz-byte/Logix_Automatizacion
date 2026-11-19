"""Crea la base logix_db desde cero y la llena con DATOS SIMULADOS.

    python generar_datos.py

1. Corre sql/01_esquema.sql (borra y crea logix_db).
2. Carga parámetros, áreas, usuarios, proveedores y la lista 69-B simulada.
3. Crea 3 compras YA aprobadas, con su OC enviada al proveedor y «esperando factura».
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
    # Confirmado con la Jefa de Adquisiciones: a mediados de diciembre (15 o 16).
    ("FECHA_LIMITE_PAGOS", f"{date.today().year}-12-15", "Último día para pagar con el presupuesto del ejercicio"),
    ("DIAS_SEMAFORO_ROJO", "15", "Días antes del cierre para marcar en rojo"),
    ("DIAS_SEMAFORO_AMARILLO", "30", "Días antes del cierre para marcar en amarillo"),
    ("HORAS_RECORDATORIO_FINANZAS", "48", "Horas con un expediente en Finanzas sin fecha de pago para recordar"),
    ("HORAS_RECORDATORIO_ADQUISICIONES", "24", "Horas con un expediente devuelto sin corregir para recordar"),
]

AREAS = ["Departamento de Sistemas y Computación", "Departamento de Ciencias Básicas",
         "Recursos Materiales y Servicios", "Recursos Financieros"]

# (usuario, nombre simulado, rol, área)
USUARIOS = [
    ("adquisiciones", "Patricia Demo Adquisiciones", "ADQUISICIONES", "Recursos Materiales y Servicios"),
    ("almacen", "Luis Alberto Demo Almacén", "ALMACEN", "Recursos Materiales y Servicios"),
    ("finanzas", "Gabriela Demo Finanzas", "FINANZAS", "Recursos Financieros"),
    ("admin", "Administrador Logix", "ADMIN", None),
]

# (razón social, RFC)
PROVEEDORES = [
    ("Papelería Demo del Altiplano S.A. de C.V.", "PDA010101AA1"),
    ("Cómputo Demo S.A. de C.V.", "CDE020202BB2"),
    ("Comercial Demo S.A. de C.V.", "COD030303CC3"),
    ("Eléctrica Demo S.A. de C.V.", "ELD040404DD4"),
    ("Distribuidora Fantasma S.A. de C.V.", "DFA050505EE5"),      # en lista 69-B (para probar el rechazo)
]
LISTA_69B = [("DFA050505EE5", "Definitivo")]

# Compras ya aprobadas, con OC esperando factura:
# (folio OC, RFC proveedor, área solicitante, [(descripción, unidad, cantidad, precio con IVA)])
COMPRAS = [
    ("OC-2026-0001", "PDA010101AA1", "Departamento de Sistemas y Computación",
     [("Plumones para pizarrón blanco (caja con 4)", "Caja", 10, 95),
      ("Hojas blancas tamaño carta (paquete 500)", "Paquete", 5, 120)]),
    ("OC-2026-0002", "CDE020202BB2", "Departamento de Sistemas y Computación",
     [("Mouse óptico USB", "Pieza", 2, 150), ("Tóner para impresora láser", "Pieza", 1, 1450)]),
    ("OC-2026-0003", "DFA050505EE5", "Departamento de Ciencias Básicas",
     [("Cable HDMI 2 m", "Pieza", 3, 180)]),
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
    for razon, rfc in PROVEEDORES:
        correo = f"facturacion@{rfc.lower()}.demo"
        cur.execute("INSERT INTO proveedores (razon_social, rfc, correo, codigo_telegram) VALUES (?, ?, ?, ?)",
                    razon, rfc, correo, codigo_telegram())
    cur.executemany("INSERT INTO sat_lista_69b VALUES (?, ?)", LISTA_69B)


def crear_compras(cur) -> dict:
    """Crea compras ya aprobadas con su OC esperando factura. Regresa {folio_oc: datos}."""
    print("3/4  Creando órdenes de compra ya aprobadas ...")
    ocs = {}
    cur.execute("SELECT id FROM usuarios WHERE usuario = 'adquisiciones'")
    adq_id = cur.fetchone()[0]
    hace = datetime.now() - timedelta(days=4)
    for folio_oc, rfc, area, lineas in COMPRAS:
        cur.execute("SELECT id, razon_social FROM proveedores WHERE rfc = ?", rfc)
        prov_id, razon = cur.fetchone()
        total = sum(Decimal(c) * Decimal(p) for _, _, c, p in lineas)
        cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, area_solicitante, total, estatus, fecha, "
                    "registrada_por) OUTPUT INSERTED.id VALUES (?, ?, ?, ?, 'ESPERANDO_FACTURA', ?, ?)",
                    folio_oc, prov_id, area, total, hace, adq_id)
        oc_id = cur.fetchone()[0]
        detalle = []
        for desc, unidad, cant, precio in lineas:
            cur.execute("INSERT INTO oc_detalle (oc_id, descripcion, unidad, cantidad, precio_unitario) "
                        "VALUES (?, ?, ?, ?, ?)", oc_id, desc, unidad, cant, precio)
            detalle.append((desc, Decimal(cant), Decimal(precio)))
        cur.execute("INSERT INTO bitacora (fecha, actor, entidad, entidad_id, accion, valor_nuevo, detalle) "
                    "VALUES (?, 'GENERADOR', 'OC', ?, 'DATOS_SIMULADOS', 'ESPERANDO_FACTURA', ?)",
                    hace, oc_id, f"{folio_oc} registrada para pruebas (compra ya aprobada)")
        ocs[folio_oc] = {"rfc": rfc, "razon": razon, "total": total, "detalle": detalle}
    return ocs


def fabricar_facturas(ocs: dict):
    """Facturas de prueba: una por cada caso que el robot R2 debe detectar."""
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
