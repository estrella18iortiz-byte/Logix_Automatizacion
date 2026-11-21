"""Pruebas del bot de Telegram (R7) con un Telegram FALSO: no necesitan internet ni token.
Usan la base logix_db (corre antes generar_datos.py). Todo se deshace al final (rollback).

    python -m unittest tests.test_bot_telegram -v
"""
import unittest

import pyodbc
from decimal import Decimal

from logix import compras, config
from logix.bot_telegram import atender
from logix.cfdi_simulado import generar_xml

CHAT_PROVEEDOR, CHAT_ADQ, CHAT_DESCONOCIDO = 111, 222, 999


class TelegramFalso:
    def __init__(self):
        self.archivos = {}

    def descargar(self, file_id):
        return self.archivos[file_id]


def msg(chat, texto=None, documento=None, pie=None):
    m = {"chat": {"id": chat}}
    if texto:
        m["text"] = texto
    if documento:
        m["document"] = documento
        m["caption"] = pie
    return m


class BotTelegram(unittest.TestCase):
    def setUp(self):
        self.con = pyodbc.connect(config.cadena_conexion(), autocommit=False)
        self.cur = self.con.cursor()
        self.api = TelegramFalso()
        self.cur.execute("SELECT codigo_telegram FROM proveedores WHERE rfc = 'PDA010101AA1'")
        self.cod_prov = self.cur.fetchone()[0]
        self.cur.execute("SELECT codigo_telegram FROM usuarios WHERE usuario = 'almacen'")
        self.cod_adq = self.cur.fetchone()[0]

    def tearDown(self):
        self.con.rollback()
        self.con.close()

    def decir(self, m):
        return atender(self.cur, m, self.api)

    def test_sin_vincular_no_da_informacion(self):
        r = self.decir(msg(CHAT_DESCONOCIDO, "OC-2026-0001"))
        self.assertIn("vincula", r.lower())
        self.assertNotIn("Estatus", r)

    def test_codigo_invalido(self):
        self.assertIn("no es válido", self.decir(msg(CHAT_DESCONOCIDO, "/vincular 000000x")))

    def test_vincular_y_codigo_de_un_solo_uso(self):
        self.assertIn("Listo", self.decir(msg(CHAT_PROVEEDOR, f"/vincular {self.cod_prov}")))
        self.assertIn("no es válido", self.decir(msg(CHAT_DESCONOCIDO, f"/vincular {self.cod_prov}")))

    def test_consulta_de_folio(self):
        self.decir(msg(CHAT_ADQ, f"/vincular {self.cod_adq}"))
        r = self.decir(msg(CHAT_ADQ, "¿cómo va la OC-2026-0002?"))
        self.assertIn("OC-2026-0002", r)
        self.assertIn("Esperando el material", r)

    def test_proveedor_no_ve_ordenes_ajenas(self):
        self.decir(msg(CHAT_PROVEEDOR, f"/vincular {self.cod_prov}"))
        self.assertIn("OC-2026-0001", self.decir(msg(CHAT_PROVEEDOR, "OC-2026-0001")))   # es suya
        self.assertIn("no corresponde", self.decir(msg(CHAT_PROVEEDOR, "OC-2026-0002")))  # es de otro

    def test_proveedor_envia_factura_por_telegram(self):
        self.decir(msg(CHAT_PROVEEDOR, f"/vincular {self.cod_prov}"))
        self.cur.execute("SELECT id FROM ordenes_compra WHERE folio = 'OC-2026-0001'")
        oc_id = self.cur.fetchone()[0]
        lineas = [(l["descripcion"], l["cantidad"], l["precio_unitario"]) for l in compras.lineas_oc(self.cur, oc_id)]
        self.api.archivos["bueno"] = generar_xml("PDA010101AA1", "Papelería Demo", "ITM990101AB1", lineas)
        r = self.decir(msg(CHAT_PROVEEDOR, documento={"file_id": "bueno", "file_name": "factura.xml"},
                           pie="OC-2026-0001"))
        self.assertIn("validada", r)

    def test_factura_invalida_por_telegram_cancela_la_compra(self):
        self.decir(msg(CHAT_PROVEEDOR, f"/vincular {self.cod_prov}"))
        self.cur.execute("SELECT id FROM ordenes_compra WHERE folio = 'OC-2026-0005'")   # también de Papelería
        oc_id = self.cur.fetchone()[0]
        lineas = [(l["descripcion"], l["cantidad"], l["precio_unitario"]) for l in compras.lineas_oc(self.cur, oc_id)]
        self.api.archivos["malo"] = generar_xml("PDA010101AA1", "Papelería Demo", "ITM990101AB1", lineas,
                                                total_forzado=Decimal("1.00"))
        r = self.decir(msg(CHAT_PROVEEDOR, documento={"file_id": "malo", "file_name": "factura.xml"},
                           pie="OC-2026-0005"))
        self.assertIn("IMPORTE_DISTINTO", r)
        self.assertIn("canceló", r)
        self.cur.execute("SELECT estatus FROM ordenes_compra WHERE id = ?", oc_id)
        self.assertEqual(self.cur.fetchone()[0], "CANCELADA")

    def test_pdf_en_lugar_de_xml(self):
        self.decir(msg(CHAT_PROVEEDOR, f"/vincular {self.cod_prov}"))
        r = self.decir(msg(CHAT_PROVEEDOR, documento={"file_id": "x", "file_name": "factura.pdf"}, pie="OC-2026-0001"))
        self.assertIn("XML", r)

    def test_avisos_van_al_chat_vinculado(self):
        self.decir(msg(CHAT_ADQ, f"/vincular {self.cod_adq}"))
        from logix import avisos
        self.cur.execute("SELECT id FROM usuarios WHERE usuario = 'almacen'")
        avisos.a_usuario(self.cur, self.cur.fetchone()[0], "Prueba", "Hola")
        self.cur.execute("SELECT COUNT(*) FROM notificaciones WHERE canal = 'TELEGRAM' AND destinatario = ?",
                         str(CHAT_ADQ))
        self.assertEqual(self.cur.fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
