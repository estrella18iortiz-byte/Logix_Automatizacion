"""Panel Logix (CustomTkinter): lo único que usan las personas.

    python panel.py

Cada rol ve solo sus pantallas. La compra YA viene aprobada y los proveedores son fijos:
las personas solo registran la compra (Adquisiciones), revisan el material físico
(Jefe de Almacén) y resuelven los errores del banco (Finanzas). Mandar la OC, vigilar
plazos, validar la factura, armar el expediente, PAGAR y avisar lo hacen los robots.
"""
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from PIL import Image

import robot
from logix import banco_emulado, cancelacion, compras, config, consultas, db, pagos, recepcion, usuarios
from logix.cfdi_simulado import generar_xml
from logix.errores import ReglaNegocio
from logix.robot_facturas import PATRON_OC, procesar_factura

MARINO, CIAN, ACENTO, FONDO = "#0B2545", "#00A8E8", "#8DA9C4", "#EEF4F8"
VERDE, AMARILLO, ROJO = "#2E9E5B", "#E0A800", "#C0392B"
FUENTE = "Century Gothic"

MENUS = {
    "ADQUISICIONES": ["Inicio", "Registrar compra", "Buzón de facturas", "Compras canceladas", "Proveedores",
                      "Consultar folio"],
    "ALMACEN": ["Inicio", "Recepción", "Consultar folio"],
    "FINANZAS": ["Inicio", "Pagos", "Banco emulado", "Consultar folio"],
    "ADMIN": ["Inicio", "Robots y avisos", "Banco emulado", "Indicadores", "Bitácora", "Consultar folio"],
}
CAUSAS = {"DEVOLUCION_ALMACEN": "Devolución de almacén", "MATERIAL_NO_LLEGO": "Material no llegó (7 días)",
          "FACTURA_INVALIDA": "Factura no válida", "FACTURA_NO_LLEGO": "Factura no llegó (48 h)",
          "PAGO_CANCELADO": "Pago cancelado por Finanzas"}


def pesos(x) -> str:
    return f"${Decimal(x or 0):,.2f}"


def fecha(x) -> str:
    return x.strftime("%d/%m/%Y %H:%M") if isinstance(x, datetime) else (x.strftime("%d/%m/%Y") if x else "")


class Tabla(ttk.Treeview):
    """Tabla con el estilo de Logix. columnas = [(titulo, ancho)]."""

    def __init__(self, padre, columnas, alto=10):
        marco = ctk.CTkFrame(padre, fg_color="white")
        marco.pack(fill="both", expand=True, pady=(4, 8))
        super().__init__(marco, columns=[c[0] for c in columnas], show="headings", height=alto, style="Logix.Treeview")
        for titulo, ancho in columnas:
            self.heading(titulo, text=titulo)
            self.column(titulo, width=ancho, anchor="w")
        barra = ttk.Scrollbar(marco, orient="vertical", command=self.yview)
        self.configure(yscrollcommand=barra.set)
        self.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.tag_configure("par", background=FONDO)
        self.tag_configure("ROJO", foreground=ROJO)
        self.tag_configure("AMARILLO", foreground="#9A7400")
        self.tag_configure("VERDE", foreground=VERDE)
        self.datos = {}

    def llenar(self, filas, valores, etiqueta=None):
        self.delete(*self.get_children())
        self.datos = {}
        for i, f in enumerate(filas):
            tags = ["par"] if i % 2 else []
            if etiqueta:
                tags.append(etiqueta(f))
            iid = self.insert("", "end", values=valores(f), tags=tags)
            self.datos[iid] = f

    def seleccion(self):
        return [self.datos[i] for i in self.selection()]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        self.title("Logix · Compras repetitivas con proveedores fijos")
        self.geometry("1280x760")
        self.minsize(1100, 680)
        self.configure(fg_color=FONDO)
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("Logix.Treeview", font=("Segoe UI", 10), rowheight=26, background="white",
                         fieldbackground="white")
        estilo.configure("Logix.Treeview.Heading", font=("Segoe UI", 10, "bold"), background=MARINO,
                         foreground="white", relief="flat")
        estilo.map("Logix.Treeview", background=[("selected", CIAN)])
        estilo.map("Logix.Treeview.Heading", background=[("active", MARINO)])
        self.usuario = None
        self.logo = ctk.CTkImage(Image.open(config.RAIZ / "recursos" / "logo_logix.png"), size=(150, 110))
        self.iso = ctk.CTkImage(Image.open(config.RAIZ / "recursos" / "isotipo_logix.png"), size=(70, 48))
        self.pantalla_login()

    # ------------------------------------------------------------ utilidades
    def ejecutar(self, fn, exito=None):
        """Corre una operación en una transacción y muestra el error de negocio si lo hay."""
        try:
            with db.conexion() as con:
                r = fn(con.cursor())
            if exito:
                messagebox.showinfo("Logix", exito if isinstance(exito, str) else exito(r))
            return r
        except ReglaNegocio as e:
            messagebox.showwarning("Logix · No se puede continuar", str(e))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Logix · Error", f"{type(e).__name__}: {e}")
        return None

    def consultar(self, fn):
        with db.conexion() as con:
            return fn(con.cursor())

    def limpiar(self, marco):
        for w in marco.winfo_children():
            w.destroy()

    def titulo(self, texto, sub=""):
        ctk.CTkLabel(self.contenido, text=texto, font=(FUENTE, 24, "bold"), text_color=MARINO).pack(anchor="w")
        if sub:
            ctk.CTkLabel(self.contenido, text=sub, font=("Segoe UI", 12), text_color="#4A5D73",
                         wraplength=950, justify="left").pack(anchor="w", pady=(0, 8))

    def boton(self, padre, texto, comando, color=MARINO, **kw):
        return ctk.CTkButton(padre, text=texto, command=comando, fg_color=color, hover_color=CIAN,
                             font=("Segoe UI", 12, "bold"), corner_radius=8, **kw)

    def fila_botones(self):
        f = ctk.CTkFrame(self.contenido, fg_color="transparent")
        f.pack(fill="x", pady=4)
        return f

    # ------------------------------------------------------------ login
    def pantalla_login(self):
        self.limpiar(self)
        caja = ctk.CTkFrame(self, fg_color="white", corner_radius=16)
        caja.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(caja, image=self.logo, text="").pack(padx=60, pady=(30, 4))
        ctk.CTkLabel(caja, text="«Conectando eficiencia y control en cada flujo de trabajo.»",
                     font=("Segoe UI", 11, "italic"), text_color="#4A5D73").pack(padx=30)
        self.e_usuario = ctk.CTkEntry(caja, placeholder_text="Usuario", width=280, height=36)
        self.e_usuario.pack(pady=(20, 8))
        self.e_pass = ctk.CTkEntry(caja, placeholder_text="Contraseña", show="•", width=280, height=36)
        self.e_pass.pack(pady=4)
        self.e_pass.bind("<Return>", lambda _: self.entrar())
        self.boton(caja, "Iniciar sesión", self.entrar, width=280, height=38).pack(pady=(14, 6))
        ctk.CTkLabel(caja, text="Datos simulados · contraseña de prueba: logix2026",
                     font=("Segoe UI", 10), text_color=ACENTO).pack(pady=(4, 26))
        self.e_usuario.focus()

    def entrar(self):
        u = self.ejecutar(lambda cur: usuarios.iniciar_sesion(cur, self.e_usuario.get(), self.e_pass.get()))
        if u:
            self.usuario = u
            self.pantalla_principal()

    # ------------------------------------------------------------ estructura
    def pantalla_principal(self):
        self.limpiar(self)
        lateral = ctk.CTkFrame(self, fg_color=MARINO, corner_radius=0, width=230)
        lateral.pack(side="left", fill="y")
        lateral.pack_propagate(False)
        ctk.CTkLabel(lateral, image=self.iso, text="").pack(pady=(18, 0))
        ctk.CTkLabel(lateral, text="LOGIX", font=(FUENTE, 22, "bold"), text_color="white").pack()
        ctk.CTkLabel(lateral, text=f"{self.usuario['nombre']}\n{self.usuario['rol'].replace('_', ' ').title()}",
                     font=("Segoe UI", 11), text_color=ACENTO, wraplength=200).pack(pady=(6, 14))
        self.botones_menu = {}
        for opcion in MENUS[self.usuario["rol"]]:
            b = ctk.CTkButton(lateral, text=opcion, anchor="w", fg_color="transparent", hover_color="#13315C",
                              text_color="white", font=("Segoe UI", 13), height=36,
                              command=lambda o=opcion: self.ir(o))
            b.pack(fill="x", padx=12, pady=2)
            self.botones_menu[opcion] = b
        ctk.CTkButton(lateral, text="Cerrar sesión", fg_color="transparent", border_width=1, border_color=ACENTO,
                      text_color=ACENTO, hover_color="#13315C", command=self.pantalla_login).pack(side="bottom",
                                                                                                    pady=16)
        ctk.CTkLabel(lateral, text="DATOS SIMULADOS", font=("Segoe UI", 9, "bold"),
                     text_color=CIAN).pack(side="bottom")
        self.contenido = ctk.CTkScrollableFrame(self, fg_color=FONDO)
        self.contenido.pack(side="left", fill="both", expand=True, padx=24, pady=18)
        self.ir("Inicio")

    def ir(self, opcion):
        for o, b in self.botones_menu.items():
            b.configure(fg_color=CIAN if o == opcion else "transparent")
        self.limpiar(self.contenido)
        vistas = {
            "Inicio": self.v_inicio, "Registrar compra": self.v_registrar_compra,
            "Buzón de facturas": self.v_buzon, "Compras canceladas": self.v_canceladas,
            "Proveedores": self.v_proveedores, "Recepción": self.v_recepcion, "Pagos": self.v_pagos,
            "Banco emulado": self.v_banco, "Consultar folio": self.v_folio, "Robots y avisos": self.v_robots,
            "Indicadores": self.v_indicadores, "Bitácora": self.v_bitacora,
        }
        vistas[opcion]()

    # ------------------------------------------------------------ vistas
    def tarjeta(self, padre, numero, texto, color=MARINO):
        t = ctk.CTkFrame(padre, fg_color="white", corner_radius=12, width=200, height=92)
        t.pack(side="left", padx=(0, 12))
        t.pack_propagate(False)
        ctk.CTkLabel(t, text=str(numero), font=(FUENTE, 30, "bold"), text_color=color).pack(pady=(10, 0))
        ctk.CTkLabel(t, text=texto, font=("Segoe UI", 11), text_color="#4A5D73").pack()

    def v_inicio(self):
        self.titulo(f"Hola, {self.usuario['nombre'].split()[0]}",
                    "Logix manda la orden de compra, vigila que el material llegue en 7 días, valida la factura, "
                    "arma el expediente para Recursos Financieros y paga en automático con el banco emulado. "
                    "Lo que necesita tu atención aparece aquí.")
        t = self.consultar(consultas.tablero)
        o = t["ordenes"]
        rol = self.usuario["rol"]
        fila = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila.pack(fill="x", pady=8)
        self.tarjeta(fila, o.get("ESPERANDO_MATERIAL", 0), "Esperando material",
                     CIAN if rol == "ALMACEN" and o.get("ESPERANDO_MATERIAL") else MARINO)
        self.tarjeta(fila, o.get("MATERIAL_RECIBIDO", 0), "Esperando factura (48 h)")
        self.tarjeta(fila, o.get("EN_FINANZAS", 0), "Pago en proceso")
        self.tarjeta(fila, o.get("PAGO_CON_ERROR", 0), "Errores del banco", ROJO if o.get("PAGO_CON_ERROR") else VERDE)
        fila2 = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila2.pack(fill="x", pady=(0, 8))
        self.tarjeta(fila2, o.get("PAGADA", 0), "Compras pagadas", VERDE)
        self.tarjeta(fila2, o.get("CANCELADA", 0), "Compras canceladas", ROJO if o.get("CANCELADA") else VERDE)
        self.tarjeta(fila2, t["por_devolver"], "Material por devolver", ROJO if t["por_devolver"] else VERDE)
        if not self.usuario.get("telegram_chat_id") and self.usuario.get("codigo_telegram"):
            aviso = ctk.CTkFrame(self.contenido, fg_color="white", corner_radius=12)
            aviso.pack(fill="x", pady=(10, 0))
            ctk.CTkLabel(aviso, text=f"📲 Recibe tus avisos en Telegram: abre el bot de Logix y envía  "
                                     f"/vincular {self.usuario['codigo_telegram']}",
                         font=("Segoe UI", 13, "bold"), text_color=MARINO).pack(anchor="w", padx=14, pady=10)
        ctk.CTkLabel(self.contenido, text="Plazo del material (robot R3 · máximo 7 días)", font=(FUENTE, 16, "bold"),
                     text_color=MARINO).pack(anchor="w", pady=(14, 0))
        self._tabla_plazos(self.contenido)

    def _tabla_plazos(self, padre, alto=8):
        filas = self.consultar(recepcion.por_recibir)
        tabla = Tabla(padre, [("Plazo", 90), ("Folio", 120), ("Proveedor", 260), ("Área", 230), ("Importe", 110),
                              ("Vence", 130), ("Horas restantes", 110), ("Factura", 90)], alto=alto)

        def semaforo(f):
            return "ROJO" if f["horas_restantes"] <= 24 else ("AMARILLO" if f["horas_restantes"] <= 96 else "VERDE")
        tabla.llenar(filas, lambda f: ["● " + semaforo(f).title(), f["folio"], f["proveedor"], f["area_solicitante"],
                                       pesos(f["total"]), fecha(f["vence"]), f["horas_restantes"],
                                       "✔ Validada" if f["factura_valida"] else "Pendiente"],
                     etiqueta=semaforo)
        return tabla

    def _ver_folio(self, tabla):
        sel = tabla.seleccion()
        if sel:
            self.ir("Consultar folio")
            self.e_folio.insert(0, sel[0]["folio"])
            self._buscar_folio()

    # --- Adquisiciones: registrar una compra ya aprobada (robot R1)
    def v_registrar_compra(self):
        self.titulo("Registrar compra aprobada",
                    "La petición ya fue aceptada y validada. Elige al proveedor fijo y escribe qué se compró: Logix "
                    "le pone folio, genera la orden de compra (001-05) en PDF con QR y se la manda al proveedor por "
                    "correo y Telegram. Desde ese momento el material tiene 7 días para llegar.")
        self.provs = self.consultar(compras.proveedores_activos)
        self.lineas = []
        caja = ctk.CTkFrame(self.contenido, fg_color="white", corner_radius=12)
        caja.pack(fill="x", pady=6)
        ctk.CTkLabel(caja, text="Proveedor").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 0))
        self.cb_prov = ctk.CTkComboBox(caja, values=[f"{p['razon_social']} · {p['rfc']}" for p in self.provs],
                                       width=420)
        self.cb_prov.grid(row=1, column=0, columnspan=3, sticky="w", padx=12)
        ctk.CTkLabel(caja, text="Área que pidió el material").grid(row=0, column=3, sticky="w", padx=12, pady=(12, 0))
        self.e_area = ctk.CTkEntry(caja, width=320, placeholder_text="Departamento de Sistemas y Computación")
        self.e_area.grid(row=1, column=3, columnspan=2, sticky="w", padx=12)
        self.e_desc = ctk.CTkEntry(caja, placeholder_text="Descripción (ej. Mouse óptico USB)", width=330)
        self.e_desc.grid(row=3, column=0, padx=12, pady=12)
        self.e_unidad = ctk.CTkEntry(caja, placeholder_text="Unidad", width=90)
        self.e_unidad.grid(row=3, column=1, padx=4)
        self.e_cant = ctk.CTkEntry(caja, placeholder_text="Cantidad", width=90)
        self.e_cant.grid(row=3, column=2, padx=4)
        self.e_precio = ctk.CTkEntry(caja, placeholder_text="Precio con IVA", width=120)
        self.e_precio.grid(row=3, column=3, padx=4, sticky="w")
        self.boton(caja, "Agregar", self._agregar_linea, width=100).grid(row=3, column=4, padx=12)
        self.t_lineas = Tabla(self.contenido, [("Descripción", 360), ("Unidad", 90), ("Cantidad", 90),
                                               ("Precio", 110), ("Importe", 120)], alto=6)
        self.l_total = ctk.CTkLabel(self.contenido, text="Total: $0.00", font=(FUENTE, 16, "bold"), text_color=MARINO)
        self.l_total.pack(anchor="e")
        f = self.fila_botones()
        self.boton(f, "Quitar renglón", self._quitar_linea, color=ACENTO).pack(side="left")
        self.boton(f, "Registrar y enviar al proveedor", self._registrar_compra, color=CIAN).pack(side="right")
        if self.provs:
            self.cb_prov.set(f"{self.provs[0]['razon_social']} · {self.provs[0]['rfc']}")

    def _prov_actual(self):
        return next((p for p in self.provs if f"{p['razon_social']} · {p['rfc']}" == self.cb_prov.get()), None)

    def _agregar_linea(self):
        try:
            cant, precio = Decimal(self.e_cant.get()), Decimal(self.e_precio.get())
        except InvalidOperation:
            messagebox.showwarning("Logix", "Escribe la cantidad y el precio con números.")
            return
        desc = self.e_desc.get().strip()
        if not desc:
            messagebox.showwarning("Logix", "Escribe la descripción de lo que se compró.")
            return
        self.lineas.append((desc, self.e_unidad.get().strip() or "Pieza", cant, precio))
        self._refrescar_lineas()
        for e in (self.e_desc, self.e_unidad, self.e_cant, self.e_precio):
            e.delete(0, "end")

    def _quitar_linea(self):
        sel = self.t_lineas.selection()
        if sel:
            self.lineas.pop(self.t_lineas.index(sel[0]))
            self._refrescar_lineas()

    def _refrescar_lineas(self):
        self.t_lineas.llenar(self.lineas, lambda l: [l[0], l[1], f"{l[2]:g}", pesos(l[3]), pesos(l[2] * l[3])])
        self.l_total.configure(text=f"Total: {pesos(sum(c * p for _, _, c, p in self.lineas))}")

    def _registrar_compra(self):
        p = self._prov_actual()
        if not p:
            messagebox.showinfo("Logix", "Elige un proveedor.")
            return
        folio = self.ejecutar(lambda cur: compras.registrar_compra(cur, self.usuario, p["id"], self.e_area.get(),
                                                                   self.lineas),
                              lambda f: f"Compra registrada con el folio {f}. Logix generó la orden de compra en "
                                        "PDF y ya se la mandó al proveedor por correo y Telegram.")
        if folio:
            self.ir("Registrar compra")

    # --- Adquisiciones: compras canceladas (con su causa y la razón que se le mandó al proveedor)
    def v_canceladas(self):
        self.titulo("Compras canceladas",
                    "Cada cancelación ya se le avisó al proveedor y a ti por correo y Telegram, con la razón. "
                    "Causas: devolución del Jefe de Almacén, material que no llegó en 7 días, factura no válida, "
                    "factura que no llegó en 48 h o pago cancelado por Finanzas.")
        filas = self.consultar(consultas.canceladas)
        tabla = Tabla(self.contenido, [("OC", 110), ("Proveedor", 230), ("Importe", 100), ("Cancelada", 130),
                                       ("Causa", 190), ("Material", 110), ("Razón", 420)], alto=14)
        tabla.llenar(filas, lambda f: [f["folio"], f["proveedor"], pesos(f["total"]), fecha(f["fecha_cancelacion"]),
                                       CAUSAS.get(f["tipo_cancelacion"], f["tipo_cancelacion"]),
                                       ("Devuelto" if f["material_devuelto"] else "Por devolver")
                                       if f["material_por_devolver"] else "—",
                                       (f["motivo_cancelacion"] or "").replace("\n", " ")],
                     etiqueta=lambda f: "ROJO")
        f = self.fila_botones()
        self.boton(f, "Ver seguimiento", lambda: self._ver_folio(tabla), color=ACENTO).pack(side="right")

    def v_buzon(self):
        self.titulo("Buzón de facturas (robot R2)",
                    "Los proveedores envían su XML por Telegram o por correo con el folio de la OC y el robot lo "
                    "valida solo ANTES de pagar. Si la factura no es válida, la compra se cancela y se le explica "
                    "al proveedor por qué. Para la demostración, aquí puedes simular la llegada de una factura.")
        f = self.fila_botones()
        self.e_oc_buzon = ctk.CTkEntry(f, placeholder_text="Folio de la OC (asunto del correo)", width=260)
        self.e_oc_buzon.pack(side="left")
        self.boton(f, "Simular correo con XML…", self._simular_correo, color=CIAN).pack(side="left", padx=8)
        self.boton(f, "Revisar buzón ahora", self._robots_ahora, color=ACENTO).pack(side="left")
        f2 = self.fila_botones()
        ctk.CTkLabel(f2, text="Simular al proveedor de esa OC:").pack(side="left")
        self.boton(f2, "Factura correcta", lambda: self._factura_simulada(False), color=VERDE).pack(side="left", padx=6)
        self.boton(f2, "Factura con importe equivocado (cancela)", lambda: self._factura_simulada(True),
                   color=ROJO).pack(side="left")

        def cargar(cur):
            cur.execute("""SELECT TOP 100 f.recibida, oc.folio, f.rfc_emisor, f.total, f.resultado, f.detalle
                           FROM facturas f LEFT JOIN ordenes_compra oc ON oc.id = f.oc_id ORDER BY f.id DESC""")
            return db.filas(cur)
        tabla = Tabla(self.contenido, [("Recibida", 130), ("OC", 110), ("RFC emisor", 130), ("Total", 100),
                                       ("Resultado", 100), ("Detalle", 560)], alto=14)
        tabla.llenar(self.consultar(cargar), lambda f: [fecha(f["recibida"]), f["folio"] or "", f["rfc_emisor"],
                                                        pesos(f["total"]), f["resultado"], f["detalle"]],
                     etiqueta=lambda f: "VERDE" if f["resultado"] == "VALIDA" else "ROJO")

    def _simular_correo(self):
        ruta = filedialog.askopenfilename(title="Factura XML", filetypes=[("CFDI XML", "*.xml")],
                                          initialdir=config.RAIZ / "datos_prueba" / "facturas")
        if not ruta:
            return
        folio = self.e_oc_buzon.get().strip() or (PATRON_OC.search(os.path.basename(ruta)) or [None])[0]
        with open(ruta, "rb") as fh:
            contenido = fh.read()
        r = self.ejecutar(lambda cur: procesar_factura(cur, contenido, os.path.basename(ruta), folio))
        if r:
            res, cods = r
            messagebox.showinfo("Robot R2", f"Resultado: {res}" + (f"\nReglas: {', '.join(cods)}" if cods else ""))
            self.ir("Buzón de facturas")

    def _factura_simulada(self, con_error: bool):
        """Fabrica el XML que mandaría el proveedor de la OC y se lo da al robot R2."""
        folio = self.e_oc_buzon.get().strip().upper()

        def accion(cur):
            cur.execute("SELECT oc.id, oc.total, p.rfc, p.razon_social FROM ordenes_compra oc "
                        "JOIN proveedores p ON p.id = oc.proveedor_id WHERE oc.folio = ?", folio)
            fila = cur.fetchone()
            if not fila:
                raise ReglaNegocio("Escribe el folio de una OC existente (por ejemplo OC-2026-0001).")
            oc_id, total, rfc, razon = fila
            lineas = [(l["descripcion"], l["cantidad"], l["precio_unitario"]) for l in compras.lineas_oc(cur, oc_id)]
            xml = generar_xml(rfc, razon, db.parametro(cur, "RFC_INSTITUCION"), lineas,
                              total_forzado=total + 250 if con_error else None)
            return procesar_factura(cur, xml, f"{folio}_{'error' if con_error else 'correcta'}.xml", folio)
        r = self.ejecutar(accion)
        if r:
            messagebox.showinfo("Robot R2", f"Resultado: {r[0]}" + (f"\nReglas: {', '.join(r[1])}" if r[1] else ""))
            self.ir("Buzón de facturas")

    def v_proveedores(self):
        self.titulo("Proveedores fijos (ya avalados)", "Solo se compra a estos proveedores. Comparte el código de "
                                                       "Telegram con cada uno para que se vincule con el bot "
                                                       "(/vincular código): así recibe su orden de compra, manda su "
                                                       "factura y recibe la confirmación del pago.")
        provs = self.consultar(compras.proveedores_activos)
        t = Tabla(self.contenido, [("Proveedor", 320), ("RFC", 130), ("Correo", 250), ("CLABE (pago)", 170),
                                   ("Telegram", 130)], alto=8)
        t.llenar(provs, lambda p: [p["razon_social"], p["rfc"], p["correo"] or "", p["clabe"],
                                   "✔ Vinculado" if p["telegram_chat_id"] else f"Código {p['codigo_telegram']}"],
                 etiqueta=lambda p: "VERDE")

    # --- Jefe de Almacén: confirmar que el material llegó (máximo 7 días) o devolverlo
    def v_recepcion(self):
        self.titulo("Recepción en almacén · Jefe de Almacén",
                    "Revisa el material físico. Si llegó bien, confírmalo: si la factura ya está validada, Logix "
                    "manda el expediente a Finanzas y paga en ese momento; si no, le pide la factura al proveedor "
                    "(48 h). Si no llegó o llegó en mal estado, presiona «Devolución» y escribe la razón: la compra "
                    "se cancela y Logix se la manda a Adquisiciones y al proveedor por correo y Telegram.")
        tabla = self._tabla_plazos(self.contenido)
        f = self.fila_botones()

        def confirmar():
            sel = tabla.seleccion()
            if not sel:
                messagebox.showinfo("Logix", "Selecciona primero una orden de la tabla.")
                return
            self.ejecutar(lambda cur: recepcion.confirmar_recepcion(cur, self.usuario, sel[0]["id"]),
                          lambda r: f"Recepción registrada (entrada {r[0]}, salida {r[1]}). "
                                    + ("La factura ya estaba validada: Logix mandó el expediente a Finanzas y el pago "
                                       "al banco." if sel[0]["factura_valida"] else
                                       "Logix le pidió la factura al proveedor (tiene 48 horas)."))
            self.ir("Recepción")

        def devolver():
            sel = tabla.seleccion()
            if not sel:
                messagebox.showinfo("Logix", "Selecciona primero una orden de la tabla.")
                return
            d = ctk.CTkInputDialog(title="Devolución",
                                   text=f"Razón de la devolución de {sel[0]['folio']} (no llegó, llegó dañado, "
                                        "incompleto…). Se le enviará a Adquisiciones y al proveedor:").get_input()
            if d is not None:
                self.ejecutar(lambda cur: recepcion.devolucion(cur, self.usuario, sel[0]["id"], d),
                              "Compra cancelada por devolución. Logix avisó a Adquisiciones y al proveedor "
                              "por correo y Telegram.")
                self.ir("Recepción")
        self.boton(f, "✔ Llegó bien: confirmar", confirmar, color=VERDE).pack(side="right")
        self.boton(f, "↩ Devolución (escribir razón)", devolver, color=ROJO).pack(side="right", padx=8)

        ctk.CTkLabel(self.contenido, text="Material por devolver al proveedor (compras canceladas)",
                     font=(FUENTE, 16, "bold"), text_color=MARINO).pack(anchor="w", pady=(16, 0))
        t2 = Tabla(self.contenido, [("OC", 120), ("Proveedor", 260), ("Causa", 200), ("Razón", 520)], alto=5)
        t2.llenar(self.consultar(recepcion.por_devolver),
                  lambda x: [x["folio"], x["proveedor"], CAUSAS.get(x["tipo_cancelacion"], ""),
                             (x["motivo_cancelacion"] or "").replace("\n", " ")], etiqueta=lambda x: "ROJO")
        f2 = self.fila_botones()

        def devuelto():
            sel = t2.seleccion()
            if sel:
                self.ejecutar(lambda cur: cancelacion.marcar_material_devuelto(cur, self.usuario, sel[0]["id"]),
                              "Material marcado como devuelto al proveedor.")
                self.ir("Recepción")
        self.boton(f2, "Marcar como devuelto", devuelto, color=ACENTO).pack(side="right")

    # --- Recursos Financieros: pago automático y errores del banco
    def v_pagos(self):
        self.titulo("Pagos · Recursos Financieros",
                    "Aquí llegan los expedientes completos (factura validada + confirmación del Jefe de Almacén). "
                    "Logix manda el pago al banco en automático. Solo tienes que intervenir si el banco responde con "
                    "un error: «Reintentar pago» o «Cancelar pago» con motivo (se avisa al proveedor y a Adquisiciones).")
        t = Tabla(self.contenido, [("OC", 110), ("Proveedor", 220), ("Importe", 100), ("Llegó", 130),
                                   ("Estado del pago", 120), ("Intentos", 70), ("Error del banco", 170),
                                   ("Detalle", 330)], alto=7)
        t.llenar(self.consultar(pagos.en_finanzas),
                 lambda f: [f["folio"], f["proveedor"], pesos(f["total"]), fecha(f["fecha_turno"]), f["estatus_pago"],
                            f["intentos"], f["codigo_error"] or "—", f["detalle_error"] or ""],
                 etiqueta=lambda f: "ROJO" if f["estatus"] == "PAGO_CON_ERROR" else "AMARILLO")
        f = self.fila_botones()

        def sel():
            s = t.seleccion()
            if not s:
                messagebox.showinfo("Logix", "Selecciona primero un expediente de la tabla.")
            return s[0] if s else None

        def abrir():
            s = sel()
            if s and s["ruta_pdf"]:
                os.startfile(s["ruta_pdf"])

        def reintentar():
            s = sel()
            if s:
                r = self.ejecutar(lambda cur: pagos.reintentar(cur, self.usuario, s["id"]))
                if r:
                    messagebox.showinfo("Banco emulado", "✔ El banco confirmó el pago." if r == "CONFIRMADO"
                                        else f"El banco volvió a responder: {r}")
                self.ir("Pagos")

        def cancelar():
            s = sel()
            if s:
                m = ctk.CTkInputDialog(title="Cancelar pago", text=f"Motivo de la cancelación de {s['folio']} "
                                       "(se le enviará al proveedor y a Adquisiciones):").get_input()
                if m is not None:
                    self.ejecutar(lambda cur: pagos.cancelar_pago(cur, self.usuario, s["id"], m),
                                  "Compra cancelada. Logix avisó al proveedor y a Adquisiciones.")
                    self.ir("Pagos")

        def clabe():
            s = sel()
            if s:
                c = ctk.CTkInputDialog(title="Corregir CLABE", text=f"CLABE correcta del proveedor {s['proveedor']} "
                                       f"(actual: {s['clabe']}):").get_input()
                if c:
                    self.ejecutar(lambda cur: pagos.corregir_clabe(cur, self.usuario, s["id"], c),
                                  "CLABE corregida. Ahora presiona «Reintentar pago».")
                    self.ir("Pagos")
        self.boton(f, "Abrir expediente PDF", abrir, color=ACENTO).pack(side="left")
        self.boton(f, "Corregir CLABE", clabe, color=ACENTO).pack(side="left", padx=6)
        self.boton(f, "↻ Reintentar pago", reintentar, color=CIAN).pack(side="left", padx=6)
        self.boton(f, "✖ Cancelar pago", cancelar, color=ROJO).pack(side="right")

        ctk.CTkLabel(self.contenido, text="Pagos confirmados por el banco", font=(FUENTE, 16, "bold"),
                     text_color=MARINO).pack(anchor="w", pady=(16, 0))
        t2 = Tabla(self.contenido, [("OC", 120), ("Proveedor", 280), ("Monto", 110), ("Clave de rastreo", 220),
                                    ("Fecha de pago", 140), ("Intentos", 80)], alto=6)
        t2.llenar(self.consultar(pagos.pagados), lambda f: [f["folio"], f["proveedor"], pesos(f["monto"]),
                                                            f["referencia_banco"], fecha(f["fecha_pago"]), f["intentos"]],
                  etiqueta=lambda f: "VERDE")

    # --- Banco emulado (Finanzas y administración)
    def v_banco(self):
        e = self.consultar(banco_emulado.estado)
        self.titulo("Banco emulado", "Simula al banco del Tec (no es un banco real). Aquí se ve el saldo, cada "
                                     "transferencia que Logix le pidió y su respuesta. Para la demostración puedes "
                                     "forzar una falla y ver cómo responde Logix.")
        fila = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila.pack(fill="x", pady=8)
        self.tarjeta(fila, pesos(e["saldo"]), "Saldo de la cuenta", VERDE)
        self.tarjeta(fila, pesos(e["limite"]), "Límite por operación")
        self.tarjeta(fila, e["falla"].replace("_", " ").title(), "Falla simulada", ROJO if e["falla"] != "NINGUNA"
                     else VERDE)
        f = self.fila_botones()
        ctk.CTkLabel(f, text="Forzar respuesta del banco:").pack(side="left")
        cb = ctk.CTkComboBox(f, values=banco_emulado.FALLAS_SIMULABLES, width=230)
        cb.set(e["falla"])
        cb.pack(side="left", padx=6)

        def aplicar():
            self.ejecutar(lambda cur: banco_emulado.simular_falla(cur, cb.get()), f"Falla simulada: {cb.get()}")
            self.ir("Banco emulado")

        def depositar():
            m = ctk.CTkInputDialog(title="Depositar", text="Monto a depositar (simulado):").get_input()
            if m:
                try:
                    monto = Decimal(m.replace(",", "").replace("$", ""))
                except InvalidOperation:
                    messagebox.showwarning("Logix", "Escribe el monto con números.")
                    return
                self.ejecutar(lambda cur: banco_emulado.depositar(cur, monto), "Depósito simulado registrado.")
                self.ir("Banco emulado")
        self.boton(f, "Aplicar", aplicar, color=CIAN).pack(side="left")
        self.boton(f, "Depositar saldo…", depositar, color=ACENTO).pack(side="right")
        t = Tabla(self.contenido, [("Fecha", 140), ("Referencia (OC)", 130), ("CLABE destino", 170), ("Monto", 110),
                                   ("Moneda", 70), ("Respuesta del banco", 180), ("Clave de rastreo", 210)], alto=14)
        t.llenar(e["movimientos"], lambda m: [fecha(m["fecha"]), m["referencia"], m["clabe_destino"], pesos(m["monto"]),
                                              m["moneda"], m["resultado"], m["clave_rastreo"] or ""],
                 etiqueta=lambda m: "VERDE" if m["resultado"] == "CONFIRMADO" else "ROJO")

    # --- Seguimiento (todos)
    def v_folio(self):
        self.titulo("Consultar folio", "Escribe un folio de orden de compra (OC-) o un ticket de pago (PAG-).")
        f = self.fila_botones()
        self.e_folio = ctk.CTkEntry(f, placeholder_text="OC-2026-0001 / PAG-2026-0001", width=340)
        self.e_folio.pack(side="left")
        self.e_folio.bind("<Return>", lambda _: self._buscar_folio())
        self.boton(f, "Buscar", self._buscar_folio).pack(side="left", padx=8)
        self.res_folio = ctk.CTkFrame(self.contenido, fg_color="transparent")
        self.res_folio.pack(fill="both", expand=True)

    def _buscar_folio(self):
        self.limpiar(self.res_folio)
        s = self.consultar(lambda c: consultas.seguimiento(c, self.e_folio.get()))
        if not s:
            ctk.CTkLabel(self.res_folio, text="No se encontró ese folio.", text_color=ROJO).pack(anchor="w")
            return
        ctk.CTkLabel(self.res_folio, text=f"{s['folio']} · {s['estatus']} · {pesos(s['total'])}",
                     font=(FUENTE, 18, "bold"), text_color=MARINO).pack(anchor="w", pady=6)
        pasos = ctk.CTkFrame(self.res_folio, fg_color="white", corner_radius=12)
        pasos.pack(fill="x", pady=4)
        for i, nombre in enumerate(consultas.ETAPAS):
            hecho = s["etapa"] is not None and i <= s["etapa"]
            actual = s["etapa"] == i
            color = CIAN if actual else (MARINO if hecho else "#C9D6E3")
            c = ctk.CTkFrame(pasos, fg_color="transparent")
            c.pack(side="left", expand=True, pady=10)
            ctk.CTkLabel(c, text="●", font=("Segoe UI", 26), text_color=color).pack()
            ctk.CTkLabel(c, text=nombre, font=("Segoe UI", 10, "bold" if actual else "normal"),
                         text_color=MARINO if hecho else "#8A9BB0").pack()
        if s["etapa"] is None:
            ctk.CTkLabel(self.res_folio, text=f"✖ Compra cancelada: {s['motivo_cancelacion']}",
                         text_color=ROJO, wraplength=950, justify="left").pack(anchor="w")
        tabla = Tabla(self.res_folio, [("Fecha", 140), ("Quién", 200), ("Qué pasó", 200), ("Detalle", 520)], alto=12)
        tabla.llenar(s["eventos"], lambda e: [fecha(e["fecha"]), e["actor"], e["accion"].replace("_", " ").title(),
                                              e["detalle"] or e["valor_nuevo"] or ""])

    # --- Administración
    def _robots_ahora(self):
        res = robot.vuelta()
        messagebox.showinfo("Robots", "\n".join(f"{k}: {v}" for k, v in res.items()))
        self.ir(self._vista_actual())

    def _vista_actual(self):
        for o, b in self.botones_menu.items():
            if b.cget("fg_color") == CIAN:
                return o
        return "Inicio"

    def v_robots(self):
        self.titulo("Robots y avisos", f"Modo: {'SIMULADO (no se envía nada)' if config.MODO_SIMULADO else 'envíos reales'}. "
                                       "El robot corre solo cada minuto con «python robot.py»; aquí puedes forzar una vuelta.")
        f = self.fila_botones()
        self.boton(f, "Ejecutar todos los robots ahora", self._robots_ahora, color=CIAN).pack(side="left")
        tabla = Tabla(self.contenido, [("Creado", 130), ("Canal", 80), ("Destinatario", 220), ("Asunto", 280),
                                       ("Estatus", 90), ("Intentos", 70)], alto=16)
        tabla.llenar(self.consultar(consultas.notificaciones), lambda n: [fecha(n["creada"]), n["canal"],
                     n["destinatario"], n["asunto"] or n["mensaje"][:40], n["estatus"], n["intentos"]])
        tabla.bind("<Double-1>", lambda _: tabla.seleccion() and messagebox.showinfo(
            "Aviso", tabla.seleccion()[0]["mensaje"]))

    def v_indicadores(self):
        self.titulo("Indicadores", "Se calculan solos desde la base y la bitácora (métricas de la E4).")
        ind = self.consultar(consultas.indicadores)
        fila = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila.pack(fill="x", pady=8)
        self.tarjeta(fila, ind["ordenes_pagadas"], "Compras pagadas", VERDE)
        self.tarjeta(fila, ind["ordenes_canceladas"], "Compras canceladas", ROJO)
        self.tarjeta(fila, f"{ind['pct_canceladas']}%", "Órdenes canceladas")
        fila2 = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila2.pack(fill="x", pady=8)
        self.tarjeta(fila2, ind["facturas_procesadas"], "Facturas procesadas")
        self.tarjeta(fila2, ind["facturas_rechazadas"], "Facturas rechazadas", ROJO)
        self.tarjeta(fila2, ind["errores_del_banco"], "Respuestas de error del banco")
        fila3 = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila3.pack(fill="x", pady=8)
        seg = ind["segundos_promedio_pago"]
        self.tarjeta(fila3, seg if seg is not None else "—", "Seg. de Finanzas al pago", VERDE)
        horas = ind["horas_promedio_hasta_material"]
        self.tarjeta(fila3, horas if horas is not None else "—", "Horas hasta el material")
        self.tarjeta(fila3, ind["hojas_impresas"], "Hojas impresas", VERDE)
        if ind["cancelaciones_por_tipo"]:
            ctk.CTkLabel(self.contenido, text="Cancelaciones por causa", font=(FUENTE, 16, "bold"),
                         text_color=MARINO).pack(anchor="w", pady=(12, 0))
            t = Tabla(self.contenido, [("Causa", 320), ("Compras", 100)], alto=5)
            t.llenar(list(ind["cancelaciones_por_tipo"].items()), lambda x: [CAUSAS.get(x[0], x[0]), x[1]])

    def v_bitacora(self):
        self.titulo("Bitácora de auditoría", "Quién hizo qué y cuándo. No se puede editar ni borrar.")
        tabla = Tabla(self.contenido, [("Fecha", 140), ("Actor", 130), ("Entidad", 80), ("Id", 50), ("Acción", 170),
                                       ("Antes", 120), ("Después", 140), ("Detalle", 330)], alto=20)
        tabla.llenar(self.consultar(consultas.bitacora), lambda b: [fecha(b["fecha"]), b["actor"], b["entidad"],
                     b["entidad_id"] or "", b["accion"], b["valor_anterior"] or "", b["valor_nuevo"] or "",
                     b["detalle"] or ""])


if __name__ == "__main__":
    App().mainloop()
