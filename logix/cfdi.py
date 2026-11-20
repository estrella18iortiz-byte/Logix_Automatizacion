"""Robot R2 · Lector de facturas CFDI 4.0.

Toda factura electrónica en México es un archivo XML con el mismo formato (CFDI),
definido por el SAT. Por eso Logix puede leerla sin que nadie capture nada:
de ahí salen el RFC de quien factura, el RFC de quien recibe, el total y el UUID
(el «folio fiscal», único en todo el país).

Este módulo SOLO lee. Las reglas (¿coincide con la OC?) están en validacion.py.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET

NS = {
    "cfdi": "http://www.sat.gob.mx/cfd/4",
    "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
}


class CfdiInvalido(Exception):
    """El archivo no es un CFDI 4.0 que se pueda leer."""


@dataclass
class Concepto:
    descripcion: str
    cantidad: Decimal
    valor_unitario: Decimal
    importe: Decimal


@dataclass
class Factura:
    uuid: str
    rfc_emisor: str
    nombre_emisor: str
    rfc_receptor: str
    serie_folio: str
    fecha: datetime | None
    subtotal: Decimal
    total: Decimal
    tipo: str                       # I = ingreso (factura normal)
    moneda: str = "MXN"             # el banco solo acepta pagos en pesos (MXN)
    conceptos: list[Concepto] = field(default_factory=list)


def _dec(valor: str | None, campo: str) -> Decimal:
    try:
        return Decimal(valor)
    except (InvalidOperation, TypeError):
        raise CfdiInvalido(f"El campo {campo} no es un número válido: {valor!r}")


def leer_cfdi(contenido: bytes) -> Factura:
    """Convierte el XML de una factura en un objeto Factura.

    Lanza CfdiInvalido si el archivo no es XML, no es CFDI 4.0 o no está timbrado.
    """
    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError as e:
        raise CfdiInvalido(f"El archivo no es un XML válido ({e}).")

    if raiz.tag != f"{{{NS['cfdi']}}}Comprobante":
        raise CfdiInvalido("El XML no es un CFDI 4.0 (falta cfdi:Comprobante).")
    if raiz.get("Version") != "4.0":
        raise CfdiInvalido(f"Versión de CFDI no soportada: {raiz.get('Version')}.")

    emisor = raiz.find("cfdi:Emisor", NS)
    receptor = raiz.find("cfdi:Receptor", NS)
    timbre = raiz.find("cfdi:Complemento/tfd:TimbreFiscalDigital", NS)
    if emisor is None or receptor is None:
        raise CfdiInvalido("Faltan los datos del emisor o del receptor.")
    if timbre is None or not timbre.get("UUID"):
        raise CfdiInvalido("La factura no está timbrada (no tiene UUID).")

    fecha = None
    if raiz.get("Fecha"):
        try:
            fecha = datetime.fromisoformat(raiz.get("Fecha"))
        except ValueError:
            pass

    conceptos = [
        Concepto(
            descripcion=c.get("Descripcion", ""),
            cantidad=_dec(c.get("Cantidad"), "Cantidad"),
            valor_unitario=_dec(c.get("ValorUnitario"), "ValorUnitario"),
            importe=_dec(c.get("Importe"), "Importe"),
        )
        for c in raiz.findall("cfdi:Conceptos/cfdi:Concepto", NS)
    ]

    return Factura(
        uuid=timbre.get("UUID").upper(),
        rfc_emisor=emisor.get("Rfc", "").upper(),
        nombre_emisor=emisor.get("Nombre", ""),
        rfc_receptor=receptor.get("Rfc", "").upper(),
        serie_folio=f"{raiz.get('Serie', '')}{raiz.get('Folio', '')}",
        fecha=fecha,
        subtotal=_dec(raiz.get("SubTotal"), "SubTotal"),
        total=_dec(raiz.get("Total"), "Total"),
        tipo=raiz.get("TipoDeComprobante", ""),
        moneda=(raiz.get("Moneda") or "MXN").upper(),
        conceptos=conceptos,
    )
