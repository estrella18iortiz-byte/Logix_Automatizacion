"""Robot R2 · Reglas para aceptar o rechazar una factura ANTES de pagar.

Son reglas deterministas (siempre dan el mismo resultado con los mismos datos),
para que el resultado sea predecible y auditable. La política es ESTRICTA:
el importe de la factura debe ser exactamente igual al de la Orden de Compra.
Como los proveedores son fijos y ya avalados, ya no se consulta la lista 69-B del SAT.

Si la factura de una compra en curso NO pasa, la compra se CANCELA (decisión del
diagrama del 19-nov-2026). Excepciones: si la OC no existe o ya no espera factura,
solo se rechaza el archivo (no hay compra en curso que cancelar).

Las funciones de aquí no tocan la base de datos: reciben los datos ya consultados.
Así se pueden probar solas (tests/test_validacion.py).
"""
from dataclasses import dataclass
from decimal import Decimal

from .cfdi import Factura

# Estatus de la OC en los que se acepta la factura (puede llegar antes o después del material).
ESTATUS_QUE_ESPERAN_FACTURA = {"ESPERANDO_MATERIAL", "MATERIAL_RECIBIDO"}
# Hallazgos que NO cancelan la compra (solo se rechaza el archivo).
NO_CANCELAN = {"OC_INEXISTENTE", "OC_NO_ESPERA_FACTURA"}


@dataclass
class OrdenParaValidar:
    """Lo mínimo de la OC que se necesita para validar su factura."""
    folio: str
    estatus: str
    total: Decimal
    rfc_proveedor: str
    nombre_proveedor: str
    ya_tiene_factura_valida: bool = False


@dataclass
class Hallazgo:
    codigo: str        # código de la regla (p. ej. IMPORTE_DISTINTO)
    mensaje: str       # se le manda tal cual al proveedor y a Adquisiciones


def _pesos(x: Decimal) -> str:
    return f"${x:,.2f}"


def validar_factura(
    factura: Factura,
    oc: OrdenParaValidar | None,
    rfc_institucion: str,
    uuid_ya_registrado: bool,
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
    elif oc.ya_tiene_factura_valida:
        h.append(Hallazgo("OC_NO_ESPERA_FACTURA",
                          f"La OC {oc.folio} ya tiene una factura validada; no se necesita otra."))

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

    return h


def cancela_la_compra(hallazgos: list[Hallazgo]) -> bool:
    """¿Estos problemas obligan a cancelar la compra? (sí, salvo que no haya compra en curso)."""
    return bool(hallazgos) and not any(x.codigo in NO_CANCELAN for x in hallazgos)
