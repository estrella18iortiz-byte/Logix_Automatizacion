"""Genera los diagramas de Logix 3.0 en dos formatos a la vez:
  · .drawio  → se abre y se edita en draw.io (app o https://app.diagrams.net)
  · .png     → imagen lista para pegar en los documentos

    python diagramas/generar_diagramas.py

Diagramas:
  1. 01_flujo_proceso      diagrama de flujo del proceso (basado en el de Angela del 19-nov-2026)
  2. 02_estados_oc         estados por los que pasa una orden de compra
  3. 03_modelo_datos       tablas de la base logix_db y sus relaciones
"""
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

CARPETA = Path(__file__).resolve().parent
ESCALA = 2                     # el PNG sale al doble de tamaño para que se vea nítido
FUENTE = "C:/Windows/Fonts/arial.ttf"
FUENTE_B = "C:/Windows/Fonts/arialbd.ttf"

# Colores por actor (relleno, borde)
COLOR = {
    "inicio": ("#0B2545", "#0B2545"),
    "adq": ("#DCEBFA", "#2F6DB5"),       # Adquisiciones
    "robot": ("#D8F3FC", "#00A8E8"),     # robots de Logix
    "almacen": ("#DDF3E4", "#2E9E5B"),   # Jefe de Almacén
    "finanzas": ("#FFF1CC", "#C48A00"),  # Recursos Financieros / banco
    "cancela": ("#FBE0DD", "#C0392B"),   # cancelación
    "decision": ("#FFFFFF", "#0B2545"),
    "estado": ("#EEF4F8", "#0B2545"),
    "tabla": ("#FFFFFF", "#0B2545"),
}


class Diagrama:
    def __init__(self, nombre, ancho, alto, titulo):
        self.nombre, self.ancho, self.alto, self.titulo = nombre, ancho, alto, titulo
        self.nodos, self.aristas, self.textos = {}, [], []

    # forma: proceso | decision | terminal | estado | inicio | fin | tabla
    def nodo(self, id_, texto, x, y, w=260, h=64, forma="proceso", color="robot"):
        self.nodos[id_] = dict(texto=texto, x=x, y=y, w=w, h=h, forma=forma, color=color)

    def arista(self, a, b, texto="", sale=(0.5, 1), entra=(0.5, 0), puntos=(), pos_texto=None, punteada=False):
        self.aristas.append(dict(a=a, b=b, texto=texto, sale=sale, entra=entra, puntos=list(puntos),
                                 pos_texto=pos_texto, punteada=punteada))

    def texto(self, t, x, y, tam=13, negrita=False, color="#0B2545"):
        self.textos.append((t, x, y, tam, negrita, color))

    # ------------------------------------------------------------ geometría
    def _punto(self, id_, frac):
        n = self.nodos[id_]
        return (n["x"] - n["w"] / 2 + frac[0] * n["w"], n["y"] - n["h"] / 2 + frac[1] * n["h"])

    def _ruta(self, e):
        p1, p2 = self._punto(e["a"], e["sale"]), self._punto(e["b"], e["entra"])
        if e["puntos"]:
            return [p1, *e["puntos"], p2]
        if abs(p1[0] - p2[0]) < 1 or abs(p1[1] - p2[1]) < 1:
            return [p1, p2]
        vertical_sale = e["sale"][1] in (0, 1)
        vertical_entra = e["entra"][1] in (0, 1)
        if vertical_sale and vertical_entra:
            m = (p1[1] + p2[1]) / 2
            return [p1, (p1[0], m), (p2[0], m), p2]
        if not vertical_sale and not vertical_entra:
            m = (p1[0] + p2[0]) / 2
            return [p1, (m, p1[1]), (m, p2[1]), p2]
        if vertical_sale:
            return [p1, (p1[0], p2[1]), p2]
        return [p1, (p2[0], p1[1]), p2]

    # ------------------------------------------------------------ draw.io
    def drawio(self):
        celdas = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
        estilos = {
            "proceso": "rounded=1;whiteSpace=wrap;html=1;arcSize=12;",
            "decision": "rhombus;whiteSpace=wrap;html=1;",
            "terminal": "rounded=1;whiteSpace=wrap;html=1;arcSize=50;fontColor=#FFFFFF;fontStyle=1;",
            "estado": "rounded=1;whiteSpace=wrap;html=1;arcSize=30;fontStyle=1;",
            "inicio": "ellipse;html=1;fillColor=#0B2545;",
            "fin": "ellipse;shape=doubleEllipse;html=1;fillColor=#0B2545;",
            "tabla": "rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacingLeft=6;",
        }
        if self.titulo:
            celdas.append(f'<mxCell id="titulo" value="{escape(self.titulo)}" style="text;html=1;fontSize=20;'
                          f'fontStyle=1;fontColor=#0B2545;" vertex="1" parent="1"><mxGeometry x="20" y="10" '
                          f'width="{self.ancho - 40}" height="30" as="geometry"/></mxCell>')
        for i, (t, x, y, tam, neg, col) in enumerate(self.textos):
            celdas.append(f'<mxCell id="t{i}" value="{escape(t)}" style="text;html=1;fontSize={tam};'
                          f'fontStyle={1 if neg else 0};fontColor={col};align=left;" vertex="1" parent="1">'
                          f'<mxGeometry x="{x}" y="{y - tam}" width="420" height="{tam + 8}" as="geometry"/></mxCell>')
        for id_, n in self.nodos.items():
            relleno, borde = COLOR.get(n["color"], COLOR["robot"])
            valor = escape(n["texto"]).replace("\n", "&lt;br&gt;")
            celdas.append(f'<mxCell id="{id_}" value="{valor}" style="{estilos[n["forma"]]}fillColor={relleno};'
                          f'strokeColor={borde};fontSize=12;" vertex="1" parent="1"><mxGeometry '
                          f'x="{n["x"] - n["w"] / 2}" y="{n["y"] - n["h"] / 2}" width="{n["w"]}" height="{n["h"]}" '
                          'as="geometry"/></mxCell>')
        for i, e in enumerate(self.aristas):
            pts = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in e["puntos"])
            estilo = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeColor=#0B2545;"
                      f"exitX={e['sale'][0]};exitY={e['sale'][1]};entryX={e['entra'][0]};entryY={e['entra'][1]};"
                      f"fontSize=11;labelBackgroundColor=#FFFFFF;" + ("dashed=1;" if e["punteada"] else ""))
            celdas.append(f'<mxCell id="e{i}" value="{escape(e["texto"])}" style="{estilo}" edge="1" parent="1" '
                          f'source="{e["a"]}" target="{e["b"]}"><mxGeometry relative="1" as="geometry">'
                          + (f'<Array as="points">{pts}</Array>' if pts else "") + '</mxGeometry></mxCell>')
        xml = (f'<mxfile host="Logix"><diagram name="{escape(self.nombre)}"><mxGraphModel dx="0" dy="0" grid="1" '
               f'gridSize="10" page="1" pageWidth="{self.ancho}" pageHeight="{self.alto}"><root>'
               + "".join(celdas) + "</root></mxGraphModel></diagram></mxfile>")
        (CARPETA / f"{self.nombre}.drawio").write_text(xml, encoding="utf-8")

    # ------------------------------------------------------------ PNG
    def png(self):
        S = ESCALA
        img = Image.new("RGB", (self.ancho * S, self.alto * S), "white")
        d = ImageDraw.Draw(img)

        def f(tam, negrita=False):
            return ImageFont.truetype(FUENTE_B if negrita else FUENTE, int(tam * S))

        def esc(p):
            return (p[0] * S, p[1] * S)

        def envolver(texto, ancho, fuente):
            lineas = []
            for parrafo in texto.split("\n"):
                actual = ""
                for palabra in parrafo.split():
                    prueba = (actual + " " + palabra).strip()
                    if d.textlength(prueba, font=fuente) <= ancho:
                        actual = prueba
                    else:
                        if actual:
                            lineas.append(actual)
                        actual = palabra
                lineas.append(actual)
            return lineas

        if self.titulo:
            d.text((20 * S, 14 * S), self.titulo, font=f(20, True), fill="#0B2545")
        for t, x, y, tam, neg, col in self.textos:
            d.text((x * S, (y - tam) * S), t, font=f(tam, neg), fill=col)

        # aristas primero (debajo de los nodos)
        for e in self.aristas:
            ruta = [esc(p) for p in self._ruta(e)]
            for p, q in zip(ruta, ruta[1:]):
                if e["punteada"]:
                    largo = ((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) ** 0.5
                    pasos = max(1, int(largo / (8 * S)))
                    for k in range(0, pasos, 2):
                        a = (p[0] + (q[0] - p[0]) * k / pasos, p[1] + (q[1] - p[1]) * k / pasos)
                        b = (p[0] + (q[0] - p[0]) * (k + 1) / pasos, p[1] + (q[1] - p[1]) * (k + 1) / pasos)
                        d.line([a, b], fill="#0B2545", width=int(1.6 * S))
                else:
                    d.line([p, q], fill="#0B2545", width=int(1.6 * S))
            (x1, y1), (x2, y2) = ruta[-2], ruta[-1]
            t = 9 * S
            if abs(x2 - x1) > abs(y2 - y1):
                s = 1 if x2 > x1 else -1
                pts = [(x2, y2), (x2 - s * t, y2 - t / 2), (x2 - s * t, y2 + t / 2)]
            else:
                s = 1 if y2 > y1 else -1
                pts = [(x2, y2), (x2 - t / 2, y2 - s * t), (x2 + t / 2, y2 - s * t)]
            d.polygon(pts, fill="#0B2545")
            if e["texto"]:
                if e["pos_texto"]:
                    cx, cy = esc(e["pos_texto"])
                else:
                    (ax, ay), (bx, by) = ruta[0], ruta[1]
                    cx, cy = (ax + bx) / 2, (ay + by) / 2
                fuente = f(11)
                lineas = envolver(e["texto"], 170 * S, fuente)
                alto = len(lineas) * 14 * S
                ancho = max(d.textlength(l, font=fuente) for l in lineas)
                d.rectangle([cx - ancho / 2 - 3 * S, cy - alto / 2 - 2 * S, cx + ancho / 2 + 3 * S, cy + alto / 2 + 2 * S],
                            fill="white")
                for k, l in enumerate(lineas):
                    w = d.textlength(l, font=fuente)
                    d.text((cx - w / 2, cy - alto / 2 + k * 14 * S), l, font=fuente, fill="#0B2545")

        for n in self.nodos.values():
            relleno, borde = COLOR.get(n["color"], COLOR["robot"])
            x0, y0 = (n["x"] - n["w"] / 2) * S, (n["y"] - n["h"] / 2) * S
            x1, y1 = (n["x"] + n["w"] / 2) * S, (n["y"] + n["h"] / 2) * S
            cx, cy = n["x"] * S, n["y"] * S
            forma = n["forma"]
            color_texto = "#0B2545"
            if forma == "decision":
                d.polygon([(cx, y0), (x1, cy), (cx, y1), (x0, cy)], fill=relleno, outline=borde, width=int(2 * S))
                ancho_txt = n["w"] * 0.62
            elif forma == "terminal":
                d.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) / 2, fill=relleno, outline=borde, width=int(2 * S))
                color_texto, ancho_txt = "white", n["w"] - 20
            elif forma in ("inicio", "fin"):
                d.ellipse([x0, y0, x1, y1], fill="#0B2545")
                if forma == "fin":
                    d.ellipse([x0 - 4 * S, y0 - 4 * S, x1 + 4 * S, y1 + 4 * S], outline="#0B2545", width=int(2 * S))
                continue
            elif forma == "tabla":
                d.rectangle([x0, y0, x1, y1], fill="white", outline=borde, width=int(2 * S))
                lineas = n["texto"].split("\n")
                d.rectangle([x0, y0, x1, y0 + 24 * S], fill="#0B2545")
                d.text((x0 + 8 * S, y0 + 5 * S), lineas[0], font=f(12, True), fill="white")
                for k, l in enumerate(lineas[1:]):
                    d.text((x0 + 8 * S, y0 + (30 + k * 16) * S), l, font=f(11), fill="#0B2545")
                continue
            else:
                radio = (y1 - y0) / 2.4 if forma == "estado" else 10 * S
                d.rounded_rectangle([x0, y0, x1, y1], radius=radio, fill=relleno, outline=borde, width=int(2 * S))
                ancho_txt = n["w"] - 18
            negrita = forma in ("terminal", "estado")
            fuente = f(12, negrita)
            lineas = envolver(n["texto"], ancho_txt * S, fuente)
            alto = len(lineas) * 15 * S
            for k, l in enumerate(lineas):
                w = d.textlength(l, font=fuente)
                d.text((cx - w / 2, cy - alto / 2 + k * 15 * S), l, font=fuente, fill=color_texto)
        img.save(CARPETA / f"{self.nombre}.png")

    def guardar(self):
        self.drawio()
        self.png()
        print("✔", self.nombre, "(.drawio y .png)")


def leyenda(dg, x, y):
    dg.texto("Quién hace cada paso:", x, y, 13, True)
    for k, (clave, texto) in enumerate([("adq", "Adquisiciones"), ("almacen", "Jefe de Almacén (persona)"),
                                        ("robot", "Robots de Logix (automático)"),
                                        ("finanzas", "Recursos Financieros / banco emulado"),
                                        ("cancela", "Cancelación (aviso por correo y Telegram)")]):
        dg.nodo(f"ley{k}", "", x + 12, y + 22 + k * 26, 22, 16, "proceso", clave)
        dg.texto(texto, x + 32, y + 34 + k * 26, 12)


# =============================================================================== 1. flujo
def flujo():
    dg = Diagrama("01_flujo_proceso", 1240, 1800, "Logix 3.0 · Diagrama de flujo del proceso (19-nov-2026)")
    C, I, D = 560, 190, 930             # columnas: centro, izquierda, derecha
    dg.nodo("ini", "Inicio", C, 70, 160, 46, "terminal", "inicio")
    dg.nodo("p1", "Petición aceptada y validada (compra aprobada, proveedor fijo)", C, 150, 280, 56, color="adq")
    dg.nodo("p2", "R1: orden de compra en PDF con QR al proveedor por Telegram y correo", C, 245, 280, 64)
    dg.nodo("d1", "Jefe de Almacén revisa el material (máx. 7 días)", C, 380, 240, 120, "decision", "almacen")
    dg.nodo("dev", "Devolución: el jefe escribe la razón → compra cancelada; aviso a Adquisiciones y al proveedor",
            I, 380, 260, 84, color="cancela")
    dg.nodo("fin1", "Fin", I, 490, 120, 40, "terminal", "inicio")
    dg.nodo("pl", "R3: día 3 recordatorio al proveedor · 5 h antes del día 7, último aviso", D, 380, 270, 64)
    dg.nodo("d7", "¿Ya pasaron 7 días?", D, 510, 200, 100, "decision")
    dg.nodo("c7", "Compra cancelada: el material no llegó; aviso al proveedor y a Adquisiciones",
            D, 650, 270, 70, color="cancela")
    dg.nodo("fin2", "Fin", D, 750, 120, 40, "terminal", "inicio")
    dg.nodo("ok", "Llegó bien: entrada y salida automáticas (ENT / SAL)", C, 530, 280, 56, color="almacen")
    dg.nodo("df", "¿Ya hay factura válida?", C, 660, 220, 110, "decision")
    dg.nodo("pide", "Pedir la factura al proveedor por Telegram y correo (48 h)", I, 660, 270, 60)
    dg.nodo("d48", "¿Llegó la factura en 48 h?", I, 800, 210, 110, "decision")
    dg.nodo("dv", "R2: ¿la factura es válida? (importe, RFC, UUID, tipo)", I, 960, 230, 130, "decision")
    dg.nodo("cf", "Compra cancelada y material devuelto; el motivo se le manda al proveedor por correo y Telegram",
            I, 1120, 280, 84, color="cancela")
    dg.nodo("fin3", "Fin", I, 1230, 120, 40, "terminal", "inicio")
    dg.nodo("exp", "R4: expediente PDF con SHA-256 llega a Recursos Financieros", C, 960, 280, 60)
    dg.nodo("pay", "R5: pago automático al banco emulado", C, 1070, 280, 56, color="finanzas")
    dg.nodo("db", "¿El banco confirma?", C, 1200, 210, 110, "decision", "finanzas")
    dg.nodo("conf", "Mensaje al proveedor: pago confirmado (clave SPEI); aviso a Adquisiciones y Finanzas",
            C, 1350, 280, 70)
    dg.nodo("fin4", "Fin", C, 1460, 120, 40, "terminal", "inicio")
    dg.nodo("dg", "¿Error general y menos de 3 intentos?", D, 1200, 230, 120, "decision", "finanzas")
    dg.nodo("err", "Aviso a Finanzas · proveedor: «pago en proceso» (o «corrija su CLABE»)", D, 1350, 270, 64)
    dg.nodo("dfin", "Finanzas decide", D, 1480, 190, 100, "decision", "finanzas")
    dg.nodo("cp", "Compra cancelada con motivo: aviso al proveedor y a Adquisiciones; material por devolver",
            D, 1630, 280, 76, color="cancela")
    dg.nodo("fin5", "Fin", D, 1740, 120, 40, "terminal", "inicio")

    dg.arista("ini", "p1")
    dg.arista("p1", "p2")
    dg.arista("p2", "d1")
    dg.arista("d1", "dev", "No llegó o mal estado", sale=(0, 0.5), entra=(1, 0.5), pos_texto=(385, 362))
    dg.arista("dev", "fin1")
    dg.arista("d1", "pl", "Aún no llega", sale=(1, 0.5), entra=(0, 0.5), pos_texto=(735, 362))
    dg.arista("pl", "d7")
    dg.arista("d7", "pl", "No: sigue esperando", sale=(1, 0.5), entra=(1, 0.5), puntos=[(1100, 510), (1100, 380)],
              pos_texto=(1120, 445))
    dg.arista("d7", "c7", "Sí", pos_texto=(948, 590))
    dg.arista("c7", "fin2")
    dg.arista("d1", "ok", "Llegó bien", pos_texto=(612, 466))
    dg.arista("ok", "df")
    dg.arista("df", "pide", "No", sale=(0, 0.5), entra=(1, 0.5), pos_texto=(390, 645))
    dg.arista("pide", "d48")
    dg.arista("d48", "dv", "Sí", pos_texto=(208, 872))
    dg.arista("d48", "cf", "No", sale=(0, 0.5), entra=(0, 0.5), puntos=[(40, 800), (40, 1120)], pos_texto=(40, 960))
    dg.arista("dv", "cf", "No", pos_texto=(208, 1050))
    dg.arista("dv", "exp", "Sí", sale=(1, 0.5), entra=(0, 0.5), pos_texto=(360, 945))
    dg.arista("df", "exp", "Sí (llegó antes que el material)", pos_texto=(620, 830))
    dg.arista("cf", "fin3")
    dg.arista("exp", "pay")
    dg.arista("pay", "db")
    dg.arista("db", "conf", "Sí (o pago duplicado)", pos_texto=(630, 1278))
    dg.arista("conf", "fin4")
    dg.arista("db", "dg", "No", sale=(1, 0.5), entra=(0, 0.5), pos_texto=(740, 1185))
    dg.arista("dg", "pay", "Sí: reintenta solo", sale=(0.5, 0), entra=(1, 0.5), puntos=[(930, 1070)],
              pos_texto=(860, 1110))
    dg.arista("dg", "err", "No", pos_texto=(948, 1285))
    dg.arista("err", "dfin")
    dg.arista("dfin", "pay", "Reintentar", sale=(1, 0.5), entra=(1, 0.3), puntos=[(1150, 1480), (1150, 1058.8)],
              pos_texto=(1150, 1300))
    dg.arista("dfin", "cp", "Cancelar (motivo)", pos_texto=(990, 1555))
    dg.arista("cp", "fin5")
    leyenda(dg, 40, 1500)
    dg.guardar()


# =============================================================================== 2. estados
def estados():
    dg = Diagrama("02_estados_oc", 1320, 800, "Logix 3.0 · Estados de una orden de compra")
    dg.nodo("ini", "", 80, 150, 26, 26, "inicio")
    dg.nodo("em", "ESPERANDO_MATERIAL\n(máx. 7 días)", 320, 150, 240, 64, "estado")
    dg.nodo("mr", "MATERIAL_RECIBIDO\n(factura en 48 h)", 320, 360, 240, 64, "estado")
    dg.nodo("ef", "EN_FINANZAS\n(pago en el banco)", 760, 360, 240, 64, "estado", "finanzas")
    dg.nodo("pe", "PAGO_CON_ERROR\n(Finanzas decide)", 1160, 360, 240, 64, "estado", "finanzas")
    dg.nodo("pa", "PAGADA", 760, 580, 200, 56, "estado", "almacen")
    dg.nodo("ca", "CANCELADA\n(aviso por correo y Telegram)", 320, 580, 240, 64, "estado", "cancela")
    dg.nodo("finp", "", 1000, 580, 26, 26, "fin")
    dg.nodo("finc", "", 320, 730, 26, 26, "fin")
    dg.arista("ini", "em", "R1 envía la OC", sale=(1, 0.5), entra=(0, 0.5), pos_texto=(140, 130))
    dg.arista("em", "mr", "Jefe de Almacén: llegó bien (falta factura)", pos_texto=(420, 255))
    dg.arista("em", "ef", "Llegó bien y la factura ya estaba validada", sale=(1, 0.5), entra=(0.5, 0),
              puntos=[(760, 150)], pos_texto=(600, 150))
    dg.arista("mr", "ef", "R2: factura válida", sale=(1, 0.5), entra=(0, 0.5), pos_texto=(540, 345))
    dg.arista("ef", "pe", "Error del banco (o 3 errores generales)", sale=(1, 0.3), entra=(0, 0.3),
              pos_texto=(960, 320))
    dg.arista("pe", "ef", "Finanzas: reintentar", sale=(0, 0.75), entra=(1, 0.75), pos_texto=(960, 400))
    dg.arista("ef", "pa", "Banco confirma (o duplicado)", pos_texto=(840, 470))
    dg.arista("pa", "finp", sale=(1, 0.5), entra=(0, 0.5))
    dg.arista("mr", "ca", "48 h sin factura o factura inválida", pos_texto=(420, 470))
    dg.arista("em", "ca", "Devolución · 7 días sin material · factura inválida", sale=(0, 0.8), entra=(0, 0.5),
              puntos=[(150, 169.2), (150, 580)], pos_texto=(150, 420))
    dg.arista("pe", "ca", "Finanzas: cancelar pago (motivo)", sale=(0.5, 1), entra=(1, 0.5),
              puntos=[(1160, 680), (520, 680), (520, 580)], pos_texto=(840, 680))
    dg.arista("ca", "finc")
    dg.guardar()


# =============================================================================== 3. modelo de datos
def modelo():
    dg = Diagrama("03_modelo_datos", 1320, 900, "Logix 3.0 · Modelo de datos (logix_db, 14 tablas)")
    T = lambda id_, txt, x, y, h: dg.nodo(id_, txt, x, y, 250, h, "tabla", "tabla")  # noqa: E731
    T("areas", "areas\nPK id\nnombre", 150, 140, 80)
    T("usuarios", "usuarios\nPK id\nusuario, rol, correo\ntelegram_chat_id\nFK area_id", 150, 330, 120)
    T("proveedores", "proveedores (fijos)\nPK id\nrazon_social, rfc, correo\nclabe\ntelegram_chat_id", 1160, 140, 120)
    T("oc", "ordenes_compra\nPK id\nfolio, total, estatus, fecha\nFK proveedor_id, registrada_por\ntipo/motivo_cancelacion\n"
            "material_por_devolver", 660, 330, 150)
    T("det", "oc_detalle\nPK id\nFK oc_id\ndescripcion, cantidad, precio", 660, 120, 100)
    T("fac", "facturas\nPK id\nFK oc_id\nuuid, total, moneda\nresultado, detalle", 420, 600, 120)
    T("rec", "recepciones\nPK id\nFK oc_id, almacen_id\nfolio_entrada / salida", 150, 600, 100)
    T("exp", "expedientes\nPK id\nFK oc_id\nruta_pdf, sha256, memorandum", 660, 780, 100)
    T("pag", "pagos\nPK id\nFK oc_id\nmonto, moneda, estatus, intentos\ncodigo_error, referencia_banco", 920, 600, 120)
    T("mov", "banco_movimientos (banco emulado)\nPK id\nreferencia (= folio OC)\nmonto, resultado, clave_rastreo",
      1160, 790, 100)
    T("cta", "banco_cuenta (banco emulado)\nPK id\nsaldo, limite_operacion\nfalla_simulada", 1160, 400, 100)
    T("otros", "Sin relaciones directas:\nparametros (plazos y reintentos)\nnotificaciones (correo/Telegram)\n"
               "bitacora (inmutable, trigger)", 400, 800, 100)
    dg.arista("usuarios", "areas", "N : 1", sale=(0.5, 0), entra=(0.5, 1))
    dg.arista("oc", "proveedores", "N : 1", sale=(1, 0.2), entra=(0.5, 1), puntos=[(1160, 285)])
    dg.arista("oc", "usuarios", "registra · N : 1", sale=(0, 0.5), entra=(1, 0.5))
    dg.arista("det", "oc", "N : 1")
    dg.arista("fac", "oc", "N : 1", sale=(0.5, 0), entra=(0.2, 1), puntos=[(420, 450), (585, 450)])
    dg.arista("rec", "oc", "1 : 1", sale=(0.5, 0), entra=(0, 0.85), puntos=[(150, 480), (470, 480), (470, 382.5)])
    dg.arista("rec", "usuarios", "Jefe de Almacén", sale=(0.3, 0), entra=(0.3, 1), punteada=True)
    dg.arista("exp", "oc", "1 : 1", sale=(0.5, 0), entra=(0.5, 1))
    dg.arista("pag", "oc", "1 : 1", sale=(0.5, 0), entra=(0.8, 1), puntos=[(920, 450), (735, 450)])
    dg.arista("mov", "pag", "por folio", sale=(0, 0.5), entra=(0.5, 1), puntos=[(920, 790)], punteada=True)
    dg.arista("mov", "cta", "descuenta saldo", sale=(0.5, 0), entra=(0.5, 1), punteada=True)
    dg.guardar()


if __name__ == "__main__":
    flujo()
    estados()
    modelo()
