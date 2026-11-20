"""Robot R2 · Recibe facturas y las valida contra la OC ANTES de pagar.

Flujo (sin captura humana):
  1. El proveedor manda el XML por Telegram o por correo, con el folio de la OC.
  2. Logix lee el CFDI y aplica las reglas de validacion.py.
  3a. Si todo cuadra: guarda la factura como VALIDA y avisa al proveedor (acuse).
      Si el material ya está en almacén, el expediente se va a Finanzas y se paga (R4 y R5).
  3b. Si algo no cuadra: la factura queda RECHAZADA y la COMPRA SE CANCELA; se le explica
      al proveedor por qué (correo y Telegram) y, si el material ya llegó, se le devuelve.
      (Si la OC no existe o ya no espera factura, solo se rechaza el archivo.)

Los avisos solo se ponen en la cola (tabla notificaciones); el robot R6 los envía.
"""
import email
import imaplib
import re
import shutil
from datetime import datetime
from email.header import decode_header
from pathlib import Path

from . import avisos, cancelacion, config, db, expediente
from .cfdi import CfdiInvalido, leer_cfdi
from .validacion import OrdenParaValidar, cancela_la_compra, validar_factura

ACTOR = "ROBOT-R2"
PATRON_OC = re.compile(r"OC-\d{4}-\d{4}", re.IGNORECASE)


# ---------------------------------------------------------------- utilidades
_encolar = avisos.encolar


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

    # 1. Leer el CFDI. Si el archivo ni siquiera es una factura, se rechaza el archivo
    #    (no cuenta como factura recibida: el plazo de 48 h sigue corriendo).
    try:
        factura = leer_cfdi(contenido)
    except CfdiInvalido as e:
        mensaje = f"No se pudo leer su factura «{nombre_archivo}»: {e} Envíe el archivo XML original del SAT."
        db.bitacora(cur, ACTOR, "FACTURA", None, "ARCHIVO_RECHAZADO", detalle=mensaje)
        cur.execute("SELECT proveedor_id FROM ordenes_compra WHERE folio = ?", folio_oc)
        f = cur.fetchone()
        if f:
            avisos.a_proveedor(cur, f[0], f"Archivo no válido · {folio_oc}", mensaje, correo_remitente)
        else:
            _encolar(cur, "CORREO", correo_remitente, "Archivo no válido · sin folio", mensaje)
        return "RECHAZADA", ["CFDI_INVALIDO"]

    # 2. Consultar lo necesario para validar
    cur.execute("""SELECT oc.id, oc.folio, oc.estatus, oc.total, p.rfc, p.razon_social, p.id,
                          (SELECT COUNT(*) FROM facturas f WHERE f.oc_id = oc.id AND f.resultado = 'VALIDA')
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   WHERE oc.folio = ?""", folio_oc)
    fila = cur.fetchone()
    oc = None
    if fila:
        oc_id, folio, estatus, total, rfc_prov, razon, prov_id, n_validas = fila
        oc = OrdenParaValidar(folio, estatus, total, rfc_prov, razon, n_validas > 0)
    cur.execute("SELECT COUNT(*) FROM facturas WHERE uuid = ? AND resultado = 'VALIDA'", factura.uuid)
    uuid_repetido = cur.fetchone()[0] > 0

    hallazgos = validar_factura(factura, oc, db.parametro(cur, "RFC_INSTITUCION"), uuid_repetido)
    resultado = "RECHAZADA" if hallazgos else "VALIDA"
    detalle = " | ".join(h.mensaje for h in hallazgos) or "Coincide con la OC"

    # 3. Guardar la factura (válida o no: todo queda registrado)
    cur.execute("""INSERT INTO facturas (oc_id, uuid, rfc_emisor, rfc_receptor, serie_folio, total, moneda,
                                         fecha_cfdi, ruta_xml, resultado, detalle)
                   OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                oc_id if oc else None, factura.uuid, factura.rfc_emisor, factura.rfc_receptor,
                factura.serie_folio, factura.total, factura.moneda[:3], factura.fecha, str(ruta), resultado,
                detalle[:1000])
    factura_id = cur.fetchone()[0]
    db.bitacora(cur, ACTOR, "FACTURA", factura_id, resultado, nuevo=factura.uuid, detalle=detalle)

    if resultado == "VALIDA":
        db.bitacora(cur, ACTOR, "OC", oc_id, "FACTURA_VALIDADA", nuevo=factura.uuid,
                    detalle=f"{factura.serie_folio} ${factura.total:,.2f}")
        if oc.estatus == "MATERIAL_RECIBIDO":
            siguiente = "El material ya está en almacén: su expediente pasa a Recursos Financieros para el pago."
        else:
            siguiente = "Siguiente paso: entregar el material en nuestro Almacén."
        acuse = (f"Hola, {oc.nombre_proveedor}. Recibimos y validamos su factura {factura.serie_folio} "
                 f"(folio fiscal {factura.uuid}) por ${factura.total:,.2f} para la OC {oc.folio}. {siguiente}")
        avisos.a_proveedor(cur, prov_id, f"Factura validada · {oc.folio}", acuse, correo_remitente)
        if oc.estatus == "MATERIAL_RECIBIDO":
            # Ya están la factura y el material: R4 arma el expediente y R5 paga.
            expediente.armar_y_enviar(cur, oc_id)
        return resultado, []

    lista = "\n- " + "\n- ".join(h.mensaje for h in hallazgos)
    if oc and cancela_la_compra(hallazgos):
        # Regla del diagrama: factura que no pasa la validación = compra cancelada.
        cancelacion.cancelar(cur, oc_id, "FACTURA_INVALIDA",
                             f"La factura {factura.serie_folio} no pasó la validación:{lista}", ACTOR)
    elif oc:
        avisos.a_proveedor(cur, prov_id, f"Factura rechazada · {folio_oc}",
                           f"Su factura {factura.serie_folio} para la OC {folio_oc} no se aceptó:{lista}",
                           correo_remitente)
    else:
        _encolar(cur, "CORREO", correo_remitente, "Factura rechazada · sin folio",
                 f"Su factura {factura.serie_folio} no se aceptó:{lista}")
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
