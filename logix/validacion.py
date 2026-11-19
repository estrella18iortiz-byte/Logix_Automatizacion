"""Robot R3 · Reglas para aceptar o rechazar una factura.

Son reglas deterministas (siempre dan el mismo resultado con los mismos datos),
para que el resultado sea predecible y auditable. La política es ESTRICTA:
el importe de la factura debe ser exactamente igual al de la Orden de Compra.

Las funciones de aquí no tocan la base de datos: reciben los datos ya consultados.
Así se pueden probar solas (tests/test_validacion.py).
"""
from dataclasses import dataclass
from decimal import Decimal

from .cfdi import Factura

# Estatus de la OC en los que se espera recibir la factura.
ESTATUS_QUE_ESPERAN_FACTURA = {"ESPERANDO_FACTURA"}


@dataclass
class OrdenParaValidar:
    """Lo mínimo de la OC que se necesita para validar su factura."""
    folio: str
    estatus: str
    total: Decimal
    rfc_proveedor: str
    nombre_proveedor: str


@dataclass
class Hallazgo:
    codigo: str        # se guarda en excepciones.tipo
    mensaje: str       # se le manda tal cual al proveedor y a Adquisiciones


def _pesos(x: Decimal) -> str:
    return f"${x:,.2f}"


def validar_factura(
    factura: Factura,
    oc: OrdenParaValidar | None,
    rfc_institucion: str,
    uuid_ya_registrado: bool,
    situacion_69b: str | None,
) -> list[Hallazgo]:
    """Regresa la lista de problemas encontrados. Lista vacía = factura válida."""
    h: list[Hallazgo] = []

    if oc is None:
        h.append(Hallazgo("OC_INEXISTENTE",
                          "No se encontró la Orden de Compra indicada. "
                          "Escriba el folio de la OC (por ejemplo OC-2026-0001) en el asunto del correo."))
        return h  # sin OC no se puede comparar nada más

    if factura.tipo != "I":
        h.append(Hallazgo("TIPO_COMPROBANTE",
                          f"El comprobante es de tipo «{factura.tipo}»; se esperaba una factura de ingreso (I)."))

    if oc.estatus not in ESTATUS_QUE_ESPERAN_FACTURA:
        h.append(Hallazgo("OC_NO_ESPERA_FACTURA",
                          f"La OC {oc.folio} no está esperando factura (estatus actual: {oc.estatus})."))

    if uuid_ya_registrado:
        h.append(Hallazgo("UUID_DUPLICADO",
                          f"La factura con folio fiscal {factura.uuid} ya se había registrado."))

    if factura.rfc_receptor != rfc_institucion.upper():
        h.append(Hallazgo("RFC_RECEPTOR",
                          f"La factura está a nombre del RFC {factura.rfc_receptor}; "
                          f"debe emitirse al RFC de la institución {rfc_institucion.upper()}."))

    if factura.rfc_emisor != oc.rfc_proveedor.upper():
        h.append(Hallazgo("RFC_EMISOR",
                          f"La factura la emite el RFC {factura.rfc_emisor}, pero la OC {oc.folio} "
                          f"es para {oc.nombre_proveedor} (RFC {oc.rfc_proveedor.upper()})."))

    if factura.total.quantize(Decimal("0.01")) != oc.total.quantize(Decimal("0.01")):
        h.append(Hallazgo("IMPORTE_DISTINTO",
                          f"El importe no coincide. OC {oc.folio}: {_pesos(oc.total)} / "
                          f"Factura: {_pesos(factura.total)}. Se requiere una factura corregida."))

    if situacion_69b:
        h.append(Hallazgo("SAT_69B",
                          f"El RFC {factura.rfc_emisor} aparece en la lista 69-B del SAT "
                          f"(situación: {situacion_69b}). No se puede continuar el trámite."))

    return h
