"""Crea la base logix_db desde cero y la llena con DATOS SIMULADOS.

    python generar_datos.py

1. Corre sql/01_esquema.sql (borra y crea logix_db).
2. Carga parámetros, áreas, usuarios, proveedores fijos (con su CLABE) y el banco emulado.
3. Crea 6 requisiciones YA validadas (eventos simulados) con su OC enviada y «esperando material».
   Después, el robot sigue simulando requisiciones nuevas cada MINUTOS_ENTRE_REQUISICIONES.
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
from logix import simulador
from logix.banco_emulado import digito_verificador
from logix.cfdi_simulado import generar_xml
from logix.seguridad import generar_hash

RAIZ = Path(__file__).resolve().parent
PASSWORD_DEMO = "logix2026"
RFC_INSTITUCION = "ITM990101AB1"      # simulado

PARAMETROS = [
    ("RFC_INSTITUCION", RFC_INSTITUCION, "RFC al que deben emitirse las facturas (simulado)"),
    # Plazos del diagrama del 19-nov-2026 (se cambian aquí, sin tocar el código).
    ("DIAS_ESPERA_MATERIAL", "7", "Días máximos para que llegue el material; después se cancela"),
    ("DIAS_RECORDATORIO_MATERIAL", "3", "Día en que se le recuerda al proveedor mandar el material"),
    ("HORAS_AVISO_ANTES_DE_CANCELAR", "5", "Horas antes del día 7 en que se avisa que se va a cancelar"),
    ("HORAS_ESPERA_FACTURA", "48", "Horas para mandar la factura después de que llegó el material"),
    ("REINTENTOS_BANCO", "3", "Intentos automáticos cuando el banco responde «error general»"),
    ("MINUTOS_ENTRE_REQUISICIONES", "60",
     "Cada cuántos minutos llega una requisición validada simulada (0 = simulador apagado)"),
    ("MINUTOS_PAGO_MIN", "5", "Minutos mínimos que tarda el pago en salir al banco después del expediente"),
    ("MINUTOS_PAGO_MAX", "10", "Minutos máximos que tarda el pago en salir al banco (0 = inmediato)"),
]
SALDO_INICIAL_BANCO = Decimal("250000.00")      # saldo simulado de la cuenta del Tec
LIMITE_POR_OPERACION = Decimal("100000.00")

AREAS = list(simulador.DEPARTAMENTOS) + ["Recursos Materiales y Servicios", "Recursos Financieros"]

# (usuario, nombre simulado, rol, área). Adquisiciones ya no usa Logix (sus requisiciones son eventos simulados).
USUARIOS = [
    ("almacen", "Luis Alberto Demo · Jefe de Almacén", "ALMACEN", "Recursos Materiales y Servicios"),
    ("finanzas", "Gabriela Demo Finanzas", "FINANZAS", "Recursos Financieros"),
    ("admin", "Administrador Logix", "ADMIN", None),
]

# Proveedores FIJOS, ya avalados por el Tec: (razón social, RFC, primeros 17 dígitos de la CLABE simulada).
# El dígito 18 (verificador) se calcula con el algoritmo oficial de la CLABE.
PROVEEDORES = [
    ("Papelería Demo del Altiplano S.A. de C.V.", "PDA010101AA1", "01270000123456789"),
    ("Cómputo Demo S.A. de C.V.", "CDE020202BB2", "01470000987654321"),
    ("Eléctrica Demo S.A. de C.V.", "ELD040404DD4", "02170000111222333"),
    ("Limpieza Demo del Altiplano S.A. de C.V.", "LDA050505EE5", "03270000444555666"),
]

# Requisiciones ya validadas (eventos simulados) con su OC enviada y esperando el material.
# El proveedor sale de la partida del departamento (simulador.PROVEEDOR_DE_PARTIDA).
# (folio OC, departamento, días desde que se envió, [(descripción, unidad, cantidad, precio con IVA)])
COMPRAS = [
    ("OC-2026-0001", "Departamento de Recursos Humanos", 4,
     [("Hojas blancas tamaño carta (paquete 500)", "Paquete", 10, 120),
      ("Bolígrafos tinta azul (caja con 12)", "Caja", 5, 65)]),
    ("OC-2026-0002", "Departamento de Sistemas y Computación", 2,
     [("Mouse óptico USB", "Pieza", 2, 150), ("Tóner para impresora láser", "Pieza", 1, 1450)]),
    ("OC-2026-0003", "Servicios Generales (limpieza)", 1,
     [("Jabón líquido para manos (garrafa 4 L)", "Garrafa", 4, 140),
      ("Detergente en polvo (bolsa 1 kg)", "Bolsa", 10, 48)]),
    ("OC-2026-0004", "Departamento de Mantenimiento de Equipo", 1,
     [("Foco LED 12 W", "Pieza", 20, 45)]),
    ("OC-2026-0005", "Departamento de Ciencias Básicas", 0,
     [("Plumones para pizarrón blanco (caja con 4)", "Caja", 6, 95)]),
    ("OC-2026-0006", "Departamento de Sistemas y Computación", 0,
     [("Teclado USB", "Pieza", 3, 260)]),
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
    for razon, rfc, clabe17 in PROVEEDORES:
        correo = f"facturacion@{rfc.lower()}.demo"
        clabe = clabe17 + digito_verificador(clabe17)
        cur.execute("INSERT INTO proveedores (razon_social, rfc, correo, clabe, codigo_telegram) VALUES (?, ?, ?, ?, ?)",
                    razon, rfc, correo, clabe, codigo_telegram())
    # Banco emulado: la cuenta del Tec con saldo simulado.
    cur.execute("INSERT INTO banco_cuenta (id, titular, saldo, limite_operacion) VALUES (1, ?, ?, ?)",
                "Instituto Tecnológico (cuenta simulada)", SALDO_INICIAL_BANCO, LIMITE_POR_OPERACION)


def crear_compras(cur) -> dict:
    """Crea requisiciones validadas con su OC esperando material. Regresa {folio_oc: datos}."""
    print("3/4  Creando requisiciones validadas y sus órdenes de compra ...")
    ocs = {}
    for n, (folio_oc, area, dias, lineas) in enumerate(COMPRAS, 1):
        hace = datetime.now() - timedelta(days=dias)
        subdireccion, partida, justificacion, _ = simulador.DEPARTAMENTOS[area]
        rfc = simulador.PROVEEDOR_DE_PARTIDA[partida]
        # La requisición llegó validada un poco antes de que saliera la OC.
        cur.execute("INSERT INTO requisiciones (folio, area_solicitante, partida, partida_nombre, justificacion, "
                    "firmas, fecha) OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?)",
                    f"REQ-{date.today().year}-{n:04d}", area, partida, simulador.PARTIDAS[partida], justificacion,
                    simulador.firmas_de(area, subdireccion), hace - timedelta(minutes=5))
        req_id = cur.fetchone()[0]
        cur.execute("SELECT id, razon_social FROM proveedores WHERE rfc = ?", rfc)
        prov_id, razon = cur.fetchone()
        total = sum(Decimal(c) * Decimal(p) for _, _, c, p in lineas)
        cur.execute("INSERT INTO ordenes_compra (folio, proveedor_id, requisicion_id, area_solicitante, total, "
                    "estatus, fecha) OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, 'ESPERANDO_MATERIAL', ?)",
                    folio_oc, prov_id, req_id, area, total, hace)
        oc_id = cur.fetchone()[0]
        detalle = []
        for desc, unidad, cant, precio in lineas:
            cur.execute("INSERT INTO oc_detalle (oc_id, descripcion, unidad, cantidad, precio_unitario) "
                        "VALUES (?, ?, ?, ?, ?)", oc_id, desc, unidad, cant, precio)
            detalle.append((desc, Decimal(cant), Decimal(precio)))
        cur.execute("INSERT INTO bitacora (fecha, actor, entidad, entidad_id, accion, valor_nuevo, detalle) "
                    "VALUES (?, 'GENERADOR', 'OC', ?, 'DATOS_SIMULADOS', 'ESPERANDO_MATERIAL', ?)",
                    hace, oc_id, f"{folio_oc} de la requisición REQ-{date.today().year}-{n:04d} (validada)")
        ocs[folio_oc] = {"rfc": rfc, "razon": razon, "total": total, "detalle": detalle}
    return ocs


def fabricar_facturas(ocs: dict):
    """Facturas de prueba: una por cada caso que el robot R2 debe detectar."""
    print("4/4  Fabricando facturas XML de prueba ...")
    carpeta = RAIZ / "datos_prueba" / "facturas"
    carpeta.mkdir(parents=True, exist_ok=True)
    for f in carpeta.glob("*"):
        f.unlink()

    o = {n: ocs[f"OC-2026-000{n}"] for n in range(1, 7)}
    uuid_repetido = "11111111-2222-4333-8444-555555555555"

    def xml(n, folio, **kw):
        return generar_xml(o[n]["rfc"], o[n]["razon"], RFC_INSTITUCION, o[n]["detalle"], folio, **kw)

    # Regla nueva: una factura que no pasa la validación CANCELA su compra. Por eso cada
    # factura mala va a una OC distinta. «¿Cancela?» = la OC debe quedar CANCELADA.
    casos = [
        # (archivo, folio OC del asunto, xml, resultado esperado, regla, ¿cancela la compra?)
        ("01_correcta.xml", "OC-2026-0001", xml(1, "101", uuid=uuid_repetido), "VALIDA", "—", "NO"),
        ("02_importe_distinto.xml", "OC-2026-0002", xml(2, "202", total_forzado=o[2]["total"] + 100),
         "RECHAZADA", "IMPORTE_DISTINTO", "SI"),
        ("03_otro_proveedor.xml", "OC-2026-0003",
         generar_xml("PDA010101AA1", "Papelería Demo del Altiplano S.A. de C.V.", RFC_INSTITUCION,
                     o[3]["detalle"], "303"), "RECHAZADA", "RFC_EMISOR", "SI"),
        ("04_receptor_equivocado.xml", "OC-2026-0004",
         generar_xml(o[4]["rfc"], o[4]["razon"], "XAXX010101000", o[4]["detalle"], "404"),
         "RECHAZADA", "RFC_RECEPTOR", "SI"),
        ("05_nota_de_credito.xml", "OC-2026-0005", xml(5, "505", tipo="E"), "RECHAZADA", "TIPO_COMPROBANTE", "SI"),
        ("06_duplicada.xml", "OC-2026-0001", xml(1, "101", uuid=uuid_repetido),
         "RECHAZADA", "OC_NO_ESPERA_FACTURA / UUID_DUPLICADO", "NO"),
        ("07_oc_inexistente.xml", "OC-2026-9999", xml(6, "707"), "RECHAZADA", "OC_INEXISTENTE", "NO"),
        ("08_no_es_cfdi.xml", "OC-2026-0006", b"esto no es una factura", "RECHAZADA", "CFDI_INVALIDO", "NO"),
        ("09_correcta_oc6.xml", "OC-2026-0006", xml(6, "909"), "VALIDA", "—", "NO"),
        ("10_oc_ya_cancelada.xml", "OC-2026-0002", xml(2, "210"), "RECHAZADA", "OC_NO_ESPERA_FACTURA", "NO"),
    ]
    with open(carpeta / "casos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["orden", "archivo", "folio_oc", "resultado_esperado", "regla", "cancela_compra"])
        for i, (archivo, folio, contenido, esperado, regla, cancela) in enumerate(casos, 1):
            (carpeta / archivo).write_bytes(contenido)
            w.writerow([i, archivo, folio, esperado, regla, cancela])
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
