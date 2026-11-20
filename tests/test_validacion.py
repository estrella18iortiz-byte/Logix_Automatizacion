"""Pruebas unitarias del robot R2 y del banco emulado (no necesitan base de datos).

    python -m unittest discover -s tests -v
"""
import unittest
from decimal import Decimal

from logix.cfdi import CfdiInvalido, leer_cfdi
from logix.cfdi_simulado import generar_xml
from logix.banco_emulado import clabe_valida, digito_verificador
from logix.validacion import OrdenParaValidar, cancela_la_compra, validar_factura

RFC_INST = "ITM990101AB1"
RFC_PROV = "PDA010101AA1"
LINEAS = [("Plumones", Decimal("10"), Decimal("95")), ("Hojas", Decimal("5"), Decimal("120"))]
TOTAL_OC = Decimal("1550.00")


def oc(estatus="ESPERANDO_MATERIAL", total=TOTAL_OC, rfc=RFC_PROV, ya_tiene=False):
    return OrdenParaValidar("OC-2026-0001", estatus, total, rfc, "Papelería Demo", ya_tiene)


def factura(**kw):
    datos = dict(rfc_emisor=RFC_PROV, nombre_emisor="Papelería Demo", rfc_receptor=RFC_INST,
                 conceptos=LINEAS)
    datos.update(kw)
    return leer_cfdi(generar_xml(**datos))


def codigos(f, o=None, repetido=False):
    return [h.codigo for h in validar_factura(f, o if o is not None else oc(), RFC_INST, repetido)]


class LecturaCfdi(unittest.TestCase):
    def test_lee_los_datos_principales(self):
        f = factura()
        self.assertEqual(f.rfc_emisor, RFC_PROV)
        self.assertEqual(f.rfc_receptor, RFC_INST)
        self.assertEqual(f.total, TOTAL_OC)
        self.assertEqual(len(f.conceptos), 2)
        self.assertEqual(len(f.uuid), 36)

    def test_rechaza_lo_que_no_es_xml(self):
        with self.assertRaises(CfdiInvalido):
            leer_cfdi(b"no soy un xml")

    def test_rechaza_xml_sin_timbre(self):
        xml = generar_xml(RFC_PROV, "X", RFC_INST, LINEAS).replace(b'UUID="', b'XUUID="')
        with self.assertRaises(CfdiInvalido):
            leer_cfdi(xml)


class Reglas(unittest.TestCase):
    """Un caso por regla (criterios de aceptación del robot R2)."""

    def test_factura_correcta_no_tiene_hallazgos(self):
        self.assertEqual(codigos(factura()), [])

    def test_importe_distinto_se_detiene(self):
        self.assertEqual(codigos(factura(total_forzado=Decimal("1650"))), ["IMPORTE_DISTINTO"])

    def test_un_centavo_de_diferencia_tambien_se_detiene(self):
        self.assertEqual(codigos(factura(total_forzado=Decimal("1550.01"))), ["IMPORTE_DISTINTO"])

    def test_otro_proveedor(self):
        self.assertIn("RFC_EMISOR", codigos(factura(rfc_emisor="COD030303CC3")))

    def test_receptor_equivocado(self):
        self.assertEqual(codigos(factura(rfc_receptor="XAXX010101000")), ["RFC_RECEPTOR"])

    def test_uuid_repetido(self):
        self.assertEqual(codigos(factura(), repetido=True), ["UUID_DUPLICADO"])

    def test_factura_antes_o_despues_del_material(self):
        self.assertEqual(codigos(factura(), oc(estatus="MATERIAL_RECIBIDO")), [])

    def test_oc_que_ya_tiene_factura_valida(self):
        self.assertEqual(codigos(factura(), oc(ya_tiene=True)), ["OC_NO_ESPERA_FACTURA"])

    def test_lee_la_moneda(self):
        self.assertEqual(factura(moneda="USD").moneda, "USD")

    def test_oc_que_ya_no_espera_factura(self):
        self.assertEqual(codigos(factura(), oc(estatus="PAGADA")), ["OC_NO_ESPERA_FACTURA"])

    def test_oc_inexistente(self):
        r = validar_factura(factura(), None, RFC_INST, False)
        self.assertEqual([h.codigo for h in r], ["OC_INEXISTENTE"])

    def test_nota_de_credito_no_es_factura(self):
        self.assertIn("TIPO_COMPROBANTE", codigos(factura(tipo="E")))

    def test_mensaje_explica_la_diferencia(self):
        r = validar_factura(factura(total_forzado=Decimal("1650")), oc(), RFC_INST, False)
        self.assertIn("$1,550.00", r[0].mensaje)
        self.assertIn("$1,650.00", r[0].mensaje)


class CancelaLaCompra(unittest.TestCase):
    """Regla del diagrama: factura inválida = compra cancelada (salvo que no haya compra en curso)."""

    def _h(self, *cods):
        from logix.validacion import Hallazgo
        return [Hallazgo(c, c) for c in cods]

    def test_importe_distinto_cancela(self):
        self.assertTrue(cancela_la_compra(self._h("IMPORTE_DISTINTO")))

    def test_oc_inexistente_no_cancela(self):
        self.assertFalse(cancela_la_compra(self._h("OC_INEXISTENTE")))

    def test_oc_que_ya_no_espera_no_cancela(self):
        self.assertFalse(cancela_la_compra(self._h("OC_NO_ESPERA_FACTURA", "UUID_DUPLICADO")))

    def test_factura_valida_no_cancela(self):
        self.assertFalse(cancela_la_compra([]))


class ClabeDelBanco(unittest.TestCase):
    """El banco emulado valida la CLABE con el dígito verificador oficial (pesos 3-7-1)."""

    def test_clabe_correcta(self):
        base = "01270000123456789"
        self.assertTrue(clabe_valida(base + digito_verificador(base)))

    def test_digito_equivocado(self):
        base = "01270000123456789"
        malo = str((int(digito_verificador(base)) + 1) % 10)
        self.assertFalse(clabe_valida(base + malo))

    def test_longitud_y_letras(self):
        self.assertFalse(clabe_valida("12345"))
        self.assertFalse(clabe_valida("01270000123456789X"))


if __name__ == "__main__":
    unittest.main()
