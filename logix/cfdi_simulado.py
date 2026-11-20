"""Genera facturas CFDI 4.0 de PRUEBA (datos simulados, sin sello ni validez fiscal).

Sirven para probar el robot R2 con casos buenos y malos sin usar facturas reales.
"""
import uuid as uuidlib
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

IVA = Decimal("0.16")


def _r(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generar_xml(rfc_emisor: str, nombre_emisor: str, rfc_receptor: str,
                conceptos: list[tuple[str, Decimal, Decimal]],
                folio: str = "1", total_forzado: Decimal | None = None,
                uuid: str | None = None, tipo: str = "I", moneda: str = "MXN") -> bytes:
    """conceptos = [(descripcion, cantidad, precio_unitario_CON_IVA), ...]

    En la OC los precios incluyen IVA (instructivo del formato 001-05); en el CFDI
    el valor unitario va SIN IVA y el IVA se suma aparte. Aquí se hace la conversión.
    total_forzado permite fabricar una factura con importe equivocado.
    """
    uuid = uuid or str(uuidlib.uuid4()).upper()
    subtotal = Decimal("0")
    lineas = []
    for desc, cant, precio_con_iva in conceptos:
        unitario = _r(Decimal(precio_con_iva) / (1 + IVA))
        importe = _r(unitario * Decimal(cant))
        subtotal += importe
        lineas.append(
            f'    <cfdi:Concepto ClaveProdServ="01010101" Cantidad="{cant}" ClaveUnidad="H87" '
            f'Unidad="Pieza" Descripcion="{desc}" ValorUnitario="{unitario}" Importe="{importe}" ObjetoImp="02"/>'
        )
    subtotal = _r(subtotal)
    total_conceptos = sum(_r(Decimal(c) * Decimal(p)) for _, c, p in conceptos)
    total = _r(total_forzado if total_forzado is not None else total_conceptos)
    iva = _r(total - subtotal)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
  Version="4.0" Serie="A" Folio="{folio}" Fecha="{datetime.now().replace(microsecond=0).isoformat()}"
  SubTotal="{subtotal}" Moneda="{moneda}" Total="{total}" TipoDeComprobante="{tipo}" Exportacion="01"
  MetodoPago="PPD" FormaPago="99" LugarExpedicion="78700">
  <cfdi:Emisor Rfc="{rfc_emisor}" Nombre="{nombre_emisor}" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="{rfc_receptor}" Nombre="INSTITUCION SIMULADA" DomicilioFiscalReceptor="78700"
    RegimenFiscalReceptor="603" UsoCFDI="G03"/>
  <cfdi:Conceptos>
{chr(10).join(lineas)}
  </cfdi:Conceptos>
  <cfdi:Impuestos TotalImpuestosTrasladados="{iva}"/>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="{uuid}" FechaTimbrado="{datetime.now().replace(microsecond=0).isoformat()}"/>
  </cfdi:Complemento>
</cfdi:Comprobante>
"""
    return xml.encode("utf-8")
