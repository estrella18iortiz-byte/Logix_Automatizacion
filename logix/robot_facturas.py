"""Robot R3 · Recibe facturas, las valida contra la OC y decide si avanza o se detiene.

Flujo (paso 9 del instructivo, sin captura humana):
  1. El proveedor manda el XML (y PDF) con el folio de la OC en el asunto.
  2. Logix lee el CFDI y aplica las reglas de validacion.py.
  3a. Si todo cuadra: guarda la factura, la OC pasa a FACTURA_VALIDADA y avisa
      al proveedor (acuse) y a Almacén (ya puede recibir el bien).
  3b. Si algo no cuadra: guarda la factura como RECHAZADA, abre una excepción
      para Adquisiciones y le explica al proveedor exactamente qué corregir.

Los avisos solo se ponen en la cola (tabla notificaciones); el robot R5 los envía.
"""
import email
import imaplib
import re
import shutil
from datetime import datetime
from email.header import decode_header
from pathlib import Path

from . import avisos, config, db
from .cfdi import CfdiInvalido, leer_cfdi
from .validacion import OrdenParaValidar, validar_factura

ACTOR = "ROBOT-R3"
PATRON_OC = re.compile(r"OC-\d{4}-\d{4}", re.IGNORECASE)


# ---------------------------------------------------------------- utilidades
_encolar = avisos.encolar
_avisar_rol = avisos.a_rol


def _guardar_archivo(contenido: bytes, folio_oc: str, nombre: str) -> Path:
    carpeta = config.DOCUMENTOS / "facturas" / (folio_oc or "SIN_OC")
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{datetime.now():%Y%m%d_%H%M%S}_{Path(nombre).name}"
    destino.write_bytes(contenido)
    return destino


# ---------------------------------------------------------------- lo central
def procesar_factura(cur, contenido: bytes, nombre_archivo: str, folio_oc: str | None,
                     correo_remitente: str | None = None) -> tuple[str, list[str]]:
    """Procesa UNA factura. Regresa ('VALIDA' | 'RECHAZADA', [códigos de problema])."""
    folio_oc = (folio_oc or "").upper() or None
    ruta = _guardar_archivo(contenido, folio_oc, nombre_archivo)

    # 1. Leer el CFDI
    try:
        factura = leer_cfdi(contenido)
    except CfdiInvalido as e:
        mensaje = f"No se pudo leer su factura «{nombre_archivo}»: {e} Envíe el archivo XML original del SAT."
        cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES "
                    "((SELECT id FROM ordenes_compra WHERE folio = ?), 'CFDI_INVALIDO', ?)", folio_oc, mensaje)
        db.bitacora(cur, ACTOR, "FACTURA", None, "RECHAZADA", detalle=mensaje)
        _encolar(cur, "CORREO", correo_remitente, f"Factura no válida · {folio_oc or 'sin folio'}", mensaje)
        return "RECHAZADA", ["CFDI_INVALIDO"]

    # 2. Consultar lo necesario para validar
    cur.execute("""SELECT oc.id, oc.folio, oc.estatus, oc.total, p.rfc, p.razon_social, p.correo, p.id
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   WHERE oc.folio = ?""", folio_oc)
    fila = cur.fetchone()
    oc = None
    if fila:
        oc_id, folio, estatus, total, rfc_prov, razon, correo_prov, prov_id = fila
        oc = OrdenParaValidar(folio, estatus, total, rfc_prov, razon)
    cur.execute("SELECT COUNT(*) FROM facturas WHERE uuid = ? AND resultado = 'VALIDA'", factura.uuid)
    uuid_repetido = cur.fetchone()[0] > 0
    cur.execute("SELECT situacion FROM sat_lista_69b WHERE rfc = ?", factura.rfc_emisor)
    s = cur.fetchone()
    situacion_69b = s[0] if s else None

    hallazgos = validar_factura(factura, oc, db.parametro(cur, "RFC_INSTITUCION"),
                                uuid_repetido, situacion_69b)
    resultado = "RECHAZADA" if hallazgos else "VALIDA"
    detalle = " | ".join(h.mensaje for h in hallazgos) or "Coincide con la OC"

    # 3. Guardar la factura (válida o no: todo queda registrado)
    cur.execute("""INSERT INTO facturas (oc_id, uuid, rfc_emisor, rfc_receptor, serie_folio, total, fecha_cfdi,
                                         ruta_xml, resultado, detalle)
                   OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                oc_id if oc else None, factura.uuid, factura.rfc_emisor, factura.rfc_receptor,
                factura.serie_folio, factura.total, factura.fecha, str(ruta), resultado, detalle[:1000])
    factura_id = cur.fetchone()[0]
    db.bitacora(cur, ACTOR, "FACTURA", factura_id, resultado, nuevo=factura.uuid, detalle=detalle)

    destino_proveedor = correo_remitente or (correo_prov if oc else None)

    if resultado == "VALIDA":
        cur.execute("UPDATE ordenes_compra SET estatus = 'FACTURA_VALIDADA' WHERE id = ?", oc_id)
        db.bitacora(cur, ACTOR, "OC", oc_id, "CAMBIO_ESTATUS", oc.estatus, "FACTURA_VALIDADA")
        acuse = (f"Hola, {oc.nombre_proveedor}. Recibimos y validamos su factura {factura.serie_folio} "
                 f"(folio fiscal {factura.uuid}) por ${factura.total:,.2f} para la OC {oc.folio}. "
                 f"Siguiente paso: entrega del bien en Almacén. Consulte su avance con el folio {oc.folio}.")
        avisos.a_proveedor(cur, prov_id, f"Factura validada · {oc.folio}", acuse, destino_proveedor)
        _avisar_rol(cur, "ALMACEN", f"Factura validada · {oc.folio}",
                    f"La factura de la OC {oc.folio} ({oc.nombre_proveedor}) ya fue validada. "
                    "Cuando llegue el bien, confirme la recepción en Logix.")
    else:
        for h in hallazgos:
            cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES (?, ?, ?)",
                        oc_id if oc else None, h.codigo, h.mensaje)
        texto = (f"Su factura {factura.serie_folio} para la OC {folio_oc or '(sin folio)'} NO fue aceptada:\n- "
                 + "\n- ".join(h.mensaje for h in hallazgos)
                 + "\nPor favor envíe la factura corregida respondiendo a este correo.")
        if oc:
            avisos.a_proveedor(cur, prov_id, f"Factura rechazada · {folio_oc}", texto, destino_proveedor)
        else:
            _encolar(cur, "CORREO", destino_proveedor, "Factura rechazada · sin folio", texto)
        _avisar_rol(cur, "ADQUISICIONES", f"Excepción en factura · {folio_oc or 'sin folio'}",
                    f"Logix detuvo una factura de {factura.nombre_emisor} (RFC {factura.rfc_emisor}):\n- "
                    + "\n- ".join(h.mensaje for h in hallazgos))
    return resultado, [h.codigo for h in hallazgos]


# ---------------------------------------------------------------- buzones
def revisar_buzon_carpeta(carpeta_entrada: Path | None = None) -> list[tuple[str, str, list[str]]]:
    """Modo simulado: cada archivo de buzon/entrada es un «correo».
    El nombre debe empezar con el folio de la OC, p. ej. «OC-2026-0001 factura.xml»."""
    entrada = carpeta_entrada or (config.RAIZ / "buzon" / "entrada")
    procesados = entrada.parent / "procesados"
    entrada.mkdir(parents=True, exist_ok=True)
    procesados.mkdir(parents=True, exist_ok=True)
    resultados = []
    for archivo in sorted(entrada.glob("*.xml")):
        m = PATRON_OC.search(archivo.name)
        with db.conexion() as con:
            cur = con.cursor()
            res, codigos = procesar_factura(cur, archivo.read_bytes(), archivo.name,
                                            m.group(0) if m else None)
        shutil.move(str(archivo), procesados / f"{datetime.now():%H%M%S}_{archivo.name}")
        resultados.append((archivo.name, res, codigos))
    return resultados


def _texto(h) -> str:
    partes = decode_header(h or "")
    return "".join(p.decode(c or "utf-8", errors="replace") if isinstance(p, bytes) else p for p, c in partes)


def revisar_buzon_correo() -> list[tuple[str, str, list[str]]]:
    """Modo real: lee los correos NO leídos del buzón de facturas (IMAP)."""
    resultados = []
    imap = imaplib.IMAP4_SSL(config.CORREO_IMAP)
    imap.login(config.CORREO_USUARIO, config.CORREO_PASSWORD)
    try:
        imap.select("INBOX")
        _, ids = imap.search(None, "UNSEEN")
        for num in ids[0].split():
            _, datos = imap.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(datos[0][1])
            asunto = _texto(msg.get("Subject"))
            remitente = email.utils.parseaddr(msg.get("From"))[1]
            m = PATRON_OC.search(asunto)
            for parte in msg.walk():
                nombre = _texto(parte.get_filename())
                if nombre.lower().endswith(".xml"):
                    with db.conexion() as con:
                        res, codigos = procesar_factura(con.cursor(), parte.get_payload(decode=True), nombre,
                                                        m.group(0) if m else None, remitente)
                    resultados.append((nombre, res, codigos))
    finally:
        imap.logout()
    return resultados
