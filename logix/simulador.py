"""Robot R0 · Simulador de requisiciones validadas (EVENTOS SIMULADOS).

Adquisiciones ya no usa Logix. Lo que necesitamos de ese lado son los EVENTOS:
cada cierto tiempo un departamento del Tec pide material y su requisición llega
YA VALIDADA. Este módulo los simula, siguiendo cómo viene reglamentado en el Tec:

  · Requisición de bienes y servicios (formato 001-03) con folio REQ-2026-0001.
  · Partida presupuestal del Clasificador por Objeto del Gasto, según lo que se pide:
        21101 Materiales y útiles de oficina        (hojas, bolígrafos, folders...)
        21401 Materiales y útiles de tecnologías de la información (mouse, tóner...)
        21601 Material de limpieza                  (jabón, detergente, cloro...)
        24601 Material eléctrico y electrónico      (focos, extensiones...)
  · Justificación del área y las 4 firmas que la validan:
        1. Jefe(a) del área solicitante
        2. Planeación y Presupuestos (suficiencia presupuestal en la partida)
        3. Subdirección correspondiente (Académica o de Servicios Administrativos)
        4. Dirección
  · Proveedor FIJO ya avalado para esa partida.

En cuanto llega la requisición, el robot R1 (compras.py) genera la orden de compra
(formato 001-05) y se la manda al proveedor. Nadie captura nada.

El robot corre el simulador en cada vuelta: si ya pasaron MINUTOS_ENTRE_REQUISICIONES
desde la última, llega una nueva (0 = simulador apagado).

Para las compras de cómputo (partida 21401, proveedor Cómputo Demo, el que está vinculado a
Telegram) se deja lista la factura XML correcta en datos_prueba/facturas_telegram/, para que
el proveedor simulado solo tenga que mandarla por el chat.
"""
import random
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from . import compras, db
from .cfdi_simulado import generar_xml

CARPETA_FACTURAS = Path(__file__).resolve().parent.parent / "datos_prueba" / "facturas_telegram"
PARTIDA_CON_FACTURA = "21401"    # Cómputo Demo

ACTOR = "SIMULADOR-R0"

PARTIDAS = {
    "21101": "Materiales y útiles de oficina",
    "21401": "Materiales y útiles para tecnologías de la información",
    "21601": "Material de limpieza",
    "24601": "Material eléctrico y electrónico",
}
# Proveedor fijo (ya avalado) que surte cada partida.
PROVEEDOR_DE_PARTIDA = {
    "21101": "PDA010101AA1",     # Papelería Demo del Altiplano
    "21401": "CDE020202BB2",     # Cómputo Demo
    "21601": "LDA050505EE5",     # Limpieza Demo del Altiplano
    "24601": "ELD040404DD4",     # Eléctrica Demo
}

ACADEMICAS = "Subdirección Académica"
ADMINISTRATIVAS = "Subdirección de Servicios Administrativos"

# Departamento → (subdirección que firma, partida, justificación, [(artículo, unidad, precio con IVA, cant. mín, cant. máx)])
DEPARTAMENTOS = {
    "Departamento de Recursos Humanos": (ADMINISTRATIVAS, "21101",
        "Papelería para la integración de expedientes del personal y trámites del periodo.",
        [("Hojas blancas tamaño carta (paquete 500)", "Paquete", 120, 5, 20),
         ("Bolígrafos tinta azul (caja con 12)", "Caja", 65, 2, 10),
         ("Folders tamaño carta (paquete 100)", "Paquete", 210, 1, 4),
         ("Clips estándar (caja con 100)", "Caja", 25, 2, 10),
         ("Engrapadora de escritorio", "Pieza", 180, 1, 3)]),
    "Servicios Generales (limpieza)": (ADMINISTRATIVAS, "21601",
        "Reposición de insumos de limpieza para sanitarios, aulas y oficinas del campus.",
        [("Jabón líquido para manos (garrafa 4 L)", "Garrafa", 140, 2, 8),
         ("Detergente en polvo (bolsa 1 kg)", "Bolsa", 48, 5, 20),
         ("Cloro (botella 1 L)", "Botella", 22, 10, 30),
         ("Bolsas negras para basura (paquete 10)", "Paquete", 38, 5, 20),
         ("Papel higiénico jumbo (caja con 6 rollos)", "Caja", 320, 2, 6),
         ("Desinfectante multiusos (botella 1 L)", "Botella", 45, 5, 15)]),
    "Departamento de Sistemas y Computación": (ACADEMICAS, "21401",
        "Reposición de periféricos e insumos para los laboratorios de cómputo.",
        [("Mouse óptico USB", "Pieza", 150, 2, 10),
         ("Teclado USB", "Pieza", 260, 1, 6),
         ("Tóner para impresora láser", "Pieza", 1450, 1, 2),
         ("Memoria USB 32 GB", "Pieza", 120, 2, 8)]),
    "Departamento de Ciencias Básicas": (ACADEMICAS, "21101",
        "Material didáctico para las aulas durante el semestre.",
        [("Plumones para pizarrón blanco (caja con 4)", "Caja", 95, 3, 12),
         ("Borrador para pizarrón blanco", "Pieza", 35, 3, 10),
         ("Hojas blancas tamaño carta (paquete 500)", "Paquete", 120, 2, 6)]),
    "Departamento de Mantenimiento de Equipo": (ADMINISTRATIVAS, "24601",
        "Mantenimiento correctivo de la iluminación y conexiones de edificios.",
        [("Foco LED 12 W", "Pieza", 45, 10, 40),
         ("Extensión eléctrica 5 m", "Pieza", 160, 2, 6),
         ("Contacto doble polarizado", "Pieza", 55, 4, 12)]),
}


def firmas_de(area: str, subdireccion: str) -> str:
    """Las 4 firmas con las que la requisición ya viene validada."""
    return (f"1. Jefe(a) de {area} · 2. Planeación y Presupuestos (suficiencia presupuestal) · "
            f"3. {subdireccion} · 4. Dirección")


def generar_requisicion(cur, area: str | None = None, lineas: list | None = None,
                        azar: random.Random | None = None) -> tuple[str, str]:
    """Llega una requisición validada y R1 genera su orden de compra.
    area/lineas permiten fijar el evento (pruebas); si no, se elige al azar.
    lineas = [(artículo, unidad, cantidad, precio con IVA)]. Regresa (folio REQ, folio OC)."""
    azar = azar or random
    area = area or azar.choice(list(DEPARTAMENTOS))
    subdireccion, partida, justificacion, catalogo = DEPARTAMENTOS[area]
    if lineas is None:
        elegidos = azar.sample(catalogo, k=azar.randint(1, min(3, len(catalogo))))
        lineas = [(art, uni, azar.randint(cmin, cmax), Decimal(precio)) for art, uni, precio, cmin, cmax in elegidos]

    folio_req = db.siguiente_folio(cur, "requisiciones", "REQ")
    firmas = firmas_de(area, subdireccion)
    cur.execute("INSERT INTO requisiciones (folio, area_solicitante, partida, partida_nombre, justificacion, firmas) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)",
                folio_req, area, partida, PARTIDAS[partida], justificacion, firmas)
    req_id = cur.fetchone()[0]
    db.bitacora(cur, ACTOR, "REQ", req_id, "LLEGA_REQUISICION_VALIDADA", nuevo=folio_req,
                detalle=f"{area} · partida {partida} · validada con 4 firmas")

    cur.execute("SELECT id FROM proveedores WHERE rfc = ? AND activo = 1", PROVEEDOR_DE_PARTIDA[partida])
    proveedor_id = cur.fetchone()[0]
    folio_oc = compras.generar_oc(cur, proveedor_id, area, lineas, requisicion_id=req_id)
    if partida == PARTIDA_CON_FACTURA:
        guardar_factura_correcta(cur, folio_oc)
    return folio_req, folio_oc


def guardar_factura_correcta(cur, folio_oc: str) -> Path | None:
    """Deja lista la factura XML correcta de la orden (lo que mandaría el proveedor).
    Si no se puede escribir el archivo, la compra sigue igual (solo es apoyo para la demostración)."""
    try:
        cur.execute("""SELECT oc.id, p.rfc, p.razon_social FROM ordenes_compra oc
                       JOIN proveedores p ON p.id = oc.proveedor_id WHERE oc.folio = ?""", folio_oc)
        oc_id, rfc, razon = cur.fetchone()
        lineas = [(l["descripcion"], l["cantidad"], l["precio_unitario"]) for l in compras.lineas_oc(cur, oc_id)]
        xml = generar_xml(rfc, razon, db.parametro(cur, "RFC_INSTITUCION"), lineas, folio=f"F{folio_oc[-4:]}")
        CARPETA_FACTURAS.mkdir(parents=True, exist_ok=True)
        ruta = CARPETA_FACTURAS / f"{folio_oc}_factura_correcta.xml"
        ruta.write_bytes(xml)
        return ruta
    except Exception as e:  # noqa: BLE001
        print(f"[R0] No se pudo guardar la factura de {folio_oc}: {e}")
        return None


def tal_vez_generar(cur, ahora: datetime | None = None) -> int:
    """Vuelta del robot: si ya pasó el intervalo desde la última requisición, llega una nueva."""
    minutos = int(db.parametro(cur, "MINUTOS_ENTRE_REQUISICIONES"))
    if minutos <= 0:
        return 0
    ahora = ahora or datetime.now()
    cur.execute("SELECT MAX(fecha) FROM requisiciones")
    ultima = cur.fetchone()[0]
    if ultima and ahora - ultima < timedelta(minutes=minutos):
        return 0
    generar_requisicion(cur)
    return 1


def recientes(cur, limite: int = 100) -> list[dict]:
    """Requisiciones que han llegado, con la OC que generó cada una y cómo va."""
    cur.execute(f"""SELECT TOP {int(limite)} r.id, r.folio, r.fecha, r.area_solicitante, r.partida,
                           r.partida_nombre, r.justificacion, r.firmas, oc.folio AS folio_oc, oc.total,
                           oc.estatus, p.razon_social AS proveedor
                    FROM requisiciones r LEFT JOIN ordenes_compra oc ON oc.requisicion_id = r.id
                    LEFT JOIN proveedores p ON p.id = oc.proveedor_id ORDER BY r.id DESC""")
    return db.filas(cur)
