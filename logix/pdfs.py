"""Documentos PDF con la identidad de Logix: Orden de Compra (001-05) y expediente + memorándum."""
from datetime import datetime
from pathlib import Path

import qrcode
from fpdf import FPDF

from . import config

MARINO = (11, 37, 69)       # #0B2545
CIAN = (0, 168, 232)        # #00A8E8
ACENTO = (141, 169, 196)    # #8DA9C4
FONDO = (238, 244, 248)     # #EEF4F8
LOGO = config.RAIZ / "recursos" / "logo_logix.png"
FUENTES = Path("C:/Windows/Fonts")


class DocLogix(FPDF):
    def __init__(self, titulo: str, subtitulo: str = ""):
        super().__init__(format="Letter")
        self.titulo, self.subtitulo = titulo, subtitulo
        if (FUENTES / "arial.ttf").exists():
            self.add_font("L", "", str(FUENTES / "arial.ttf"))
            self.add_font("L", "B", str(FUENTES / "arialbd.ttf"))
            self.f = "L"
        else:
            self.f = "helvetica"
        self.set_auto_page_break(True, 20)
        self.set_margins(15, 15, 15)

    def header(self):
        self.set_fill_color(*MARINO)
        self.rect(0, 0, 216, 24, "F")
        if LOGO.exists():
            self.image(str(LOGO), 12, 3, h=18)
        self.set_text_color(255, 255, 255)
        self.set_font(self.f, "B", 14)
        self.set_xy(40, 5)
        self.cell(160, 7, self.titulo, align="R")
        self.set_font(self.f, "", 9)
        self.set_xy(40, 13)
        self.cell(160, 5, self.subtitulo, align="R")
        self.set_fill_color(*CIAN)
        self.rect(0, 24, 216, 1.2, "F")
        self.set_text_color(0, 0, 0)
        self.set_y(32)

    def footer(self):
        self.set_y(-14)
        self.set_font(self.f, "", 7.5)
        self.set_text_color(*ACENTO)
        self.cell(0, 5, "Logix · Automatización y Sistematización de Procesos · DATOS SIMULADOS · "
                        f"Generado {datetime.now():%d/%m/%Y %H:%M} · Página {self.page_no()}", align="C")

    def seccion(self, texto: str):
        self.ln(2)
        self.set_fill_color(*FONDO)
        self.set_text_color(*MARINO)
        self.set_font(self.f, "B", 11)
        self.cell(0, 7, texto, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def dato(self, etiqueta: str, valor):
        self.set_font(self.f, "B", 9)
        self.cell(48, 5.5, etiqueta)
        self.set_font(self.f, "", 9)
        self.multi_cell(0, 5.5, str(valor if valor is not None else "—"), new_x="LMARGIN", new_y="NEXT")

    def tabla(self, encabezados: list[str], anchos: list[float], filas: list[list]):
        self.set_font(self.f, "B", 8.5)
        self.set_fill_color(*MARINO)
        self.set_text_color(255, 255, 255)
        for h, w in zip(encabezados, anchos):
            self.cell(w, 6, h, border=0, fill=True)
        self.ln()
        self.set_text_color(0, 0, 0)
        self.set_font(self.f, "", 8.5)
        for i, fila in enumerate(filas):
            self.set_fill_color(*(FONDO if i % 2 else (255, 255, 255)))
            for v, w in zip(fila, anchos):
                self.cell(w, 5.5, str(v)[:int(w / 1.6)], fill=True)
            self.ln()


def _carpeta(folio: str) -> Path:
    c = config.DOCUMENTOS / "expedientes" / folio
    c.mkdir(parents=True, exist_ok=True)
    return c


def _qr(texto: str, ruta: Path) -> Path:
    qrcode.make(texto).save(ruta)
    return ruta


def pdf_orden_compra(cur, oc_id: int) -> Path:
    from .compras import lineas_oc
    cur.execute("""SELECT oc.folio, oc.total, oc.fecha, oc.area_solicitante, p.razon_social, p.rfc, u.nombre
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   LEFT JOIN usuarios u ON u.id = oc.registrada_por WHERE oc.id = ?""", oc_id)
    folio, total, fecha, area, prov, rfc, registro = cur.fetchone()
    pdf = DocLogix("ORDEN DE COMPRA DEL BIEN O SERVICIO", f"Formato TecNM-AD-IT-001-05 · {folio}")
    pdf.add_page()
    carpeta = _carpeta(folio)
    pdf.image(str(_qr(folio, carpeta / "qr.png")), 175, 30, w=26)
    pdf.dato("No. de orden de compra:", folio)
    pdf.dato("Fecha:", f"{fecha:%d/%m/%Y}")
    pdf.dato("Proveedor:", f"{prov} (RFC {rfc})")
    pdf.dato("Área solicitante:", area)
    pdf.dato("Registró (Adquisiciones):", registro)
    pdf.ln(4)
    filas = [[i, f"{l['cantidad']:g}", l["unidad"], l["descripcion"], f"${l['precio_unitario']:,.2f}",
              f"${l['importe']:,.2f}"] for i, l in enumerate(lineas_oc(cur, oc_id), 1)]
    pdf.tabla(["No.", "Cant.", "Unidad", "Descripción", "P. unitario", "Importe"],
              [10, 16, 20, 90, 25, 25], filas)
    pdf.set_font(pdf.f, "B", 10)
    pdf.cell(0, 8, f"IMPORTE TOTAL (IVA incluido): ${total:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(pdf.f, "", 8.5)
    pdf.multi_cell(0, 5, "Compra autorizada previamente conforme al Instructivo TecNM-AD-IT-001.",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.seccion("Instrucciones para facturar")
    pdf.set_font(pdf.f, "", 9)
    pdf.multi_cell(0, 5, f"Envíe el XML y el PDF de su CFDI al buzón de facturas con «{folio}» en el asunto. "
                         "El importe debe coincidir exactamente con esta orden. Logix validará su factura "
                         "en automático y le responderá por correo o Telegram.")
    ruta = carpeta / f"{folio}_orden_de_compra.pdf"
    pdf.output(str(ruta))
    return ruta


def pdf_expediente(cur, oc_id: int, memorandum: str) -> Path:
    from .compras import lineas_oc
    cur.execute("""SELECT oc.folio, oc.total, oc.area_solicitante, p.razon_social, p.rfc FROM ordenes_compra oc
                   JOIN proveedores p ON p.id = oc.proveedor_id WHERE oc.id = ?""", oc_id)
    folio, total, area, prov, rfc = cur.fetchone()
    cur.execute("SELECT TOP 1 uuid, serie_folio, total, fecha_cfdi, ruta_xml FROM facturas "
                "WHERE oc_id = ? AND resultado = 'VALIDA'", oc_id)
    uuid, serie, total_f, fecha_f, ruta_xml = cur.fetchone()
    cur.execute("""SELECT rc.folio_entrada, rc.folio_salida, rc.fecha_recepcion, rc.fds_entregada,
                          rc.observaciones, ua.nombre
                   FROM recepciones rc JOIN usuarios ua ON ua.id = rc.almacen_id WHERE rc.oc_id = ?""", oc_id)
    ent, sal, f_rec, fds, obs, almacen = cur.fetchone()

    pdf = DocLogix("EXPEDIENTE DIGITAL DE COMPRA DIRECTA", f"{folio} · Memorándum {memorandum}")
    # Página 1: memorándum para Recursos Financieros
    pdf.add_page()
    pdf.set_font(pdf.f, "B", 12)
    pdf.cell(0, 8, f"MEMORÁNDUM {memorandum}", new_x="LMARGIN", new_y="NEXT")
    pdf.dato("Para:", "Departamento de Recursos Financieros")
    pdf.dato("De:", "Departamento de Recursos Materiales · Adquisiciones (generado por Logix)")
    pdf.dato("Fecha:", f"{datetime.now():%d/%m/%Y}")
    pdf.dato("Asunto:", f"Envío de expediente para programar el pago de la OC {folio}")
    pdf.ln(3)
    pdf.set_font(pdf.f, "", 10)
    pdf.multi_cell(0, 6, f"Se remite el expediente de la orden de compra {folio} del proveedor {prov} "
                         f"por ${total:,.2f}, integrado por la orden de compra (formato 001-05), la factura "
                         f"con folio fiscal {uuid} y la entrada y salida de almacén ({ent}/{sal}), para que se "
                         "programe o realice el pago correspondiente, conforme al Instructivo TecNM-AD-IT-001.")
    pdf.seccion("Revisión automática del expediente")
    for ok, texto in [(True, f"Orden de compra {folio} registrada y enviada al proveedor"),
                      (total_f == total, f"Importe de la factura ${total_f:,.2f} = importe de la OC ${total:,.2f}"),
                      (bool(ent), f"Material recibido en almacén: entrada {ent}")]:
        pdf.set_font(pdf.f, "", 9.5)
        pdf.cell(0, 6, f"{'[OK]' if ok else '[X]'}  {texto}", new_x="LMARGIN", new_y="NEXT")

    # Página 2: contenido del expediente
    pdf.add_page()
    pdf.seccion("1. Orden de compra (001-05)")
    pdf.dato("Folio / proveedor:", f"{folio} · {prov} (RFC {rfc})")
    pdf.dato("Área solicitante:", area)
    pdf.tabla(["Cant.", "Unidad", "Descripción", "P. unitario", "Importe"], [16, 22, 88, 30, 30],
              [[f"{l['cantidad']:g}", l["unidad"], l["descripcion"], f"${l['precio_unitario']:,.2f}",
                f"${l['importe']:,.2f}"] for l in lineas_oc(cur, oc_id)])
    pdf.seccion("2. Factura CFDI (validada por el robot R2)")
    pdf.dato("Folio fiscal (UUID):", uuid)
    pdf.dato("Serie y folio:", serie)
    pdf.dato("Total:", f"${total_f:,.2f}")
    pdf.dato("Fecha:", f"{fecha_f:%d/%m/%Y %H:%M}" if fecha_f else None)
    pdf.dato("Archivo XML:", Path(ruta_xml).name)
    pdf.seccion("3. Entrada y salida de almacén")
    pdf.dato("Entrada / salida:", f"{ent} / {sal}  ({f_rec:%d/%m/%Y %H:%M})")
    pdf.dato("Recibió en almacén:", almacen)
    pdf.dato("Hoja de seguridad (FDS):", "Entregada" if fds else "No aplica / no entregada")
    pdf.dato("Observaciones:", obs or "Sin observaciones")

    ruta = _carpeta(folio) / f"{folio}_expediente.pdf"
    pdf.output(str(ruta))
    return ruta
