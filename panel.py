"""Panel Logix (CustomTkinter): lo único que usan las personas.

    python panel.py

Cada rol ve solo sus pantallas. La compra YA viene aprobada: las personas solo registran
la compra (Adquisiciones), revisan el material físico (Almacén) y pagan (Finanzas);
mover los documentos y avisar entre departamentos lo hacen los robots (robot.py).
"""
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from PIL import Image

import robot
from logix import compras, config, consultas, db, pagos, recepcion, usuarios, vigilante
from logix.cfdi_simulado import generar_xml
from logix.errores import ReglaNegocio
from logix.robot_facturas import PATRON_OC, procesar_factura

MARINO, CIAN, ACENTO, FONDO = "#0B2545", "#00A8E8", "#8DA9C4", "#EEF4F8"
VERDE, AMARILLO, ROJO = "#2E9E5B", "#E0A800", "#C0392B"
FUENTE = "Century Gothic"

MENUS = {
    "ADQUISICIONES": ["Inicio", "Registrar compra", "Buzón de facturas", "Devueltas por Finanzas", "Excepciones",
                      "Proveedores", "Consultar folio"],
    "ALMACEN": ["Inicio", "Recepción", "Consultar folio"],
    "FINANZAS": ["Inicio", "Expedientes", "Consultar folio"],
    "ADMIN": ["Inicio", "Robots y avisos", "Indicadores", "Bitácora", "Consultar folio"],
}


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
        self.title("Logix · Adquisiciones ⇄ Recursos Financieros")
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
            "Buzón de facturas": self.v_buzon, "Devueltas por Finanzas": self.v_devueltas,
            "Excepciones": self.v_excepciones, "Proveedores": self.v_proveedores,
            "Recepción": self.v_recepcion, "Expedientes": self.v_pagos,
            "Consultar folio": self.v_folio, "Robots y avisos": self.v_robots, "Indicadores": self.v_indicadores,
            "Bitácora": self.v_bitacora,
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
                    "Logix mueve la orden de compra, la factura, la confirmación de almacén y el pago entre "
                    "Adquisiciones y Recursos Financieros. Lo que necesita tu atención aparece aquí.")
        t = self.consultar(consultas.tablero)
        o = t["ordenes"]
        fila = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila.pack(fill="x", pady=8)
        self.tarjeta(fila, o.get("ESPERANDO_FACTURA", 0), "Esperando factura")
        self.tarjeta(fila, o.get("FACTURA_VALIDADA", 0), "Por recibir en almacén",
                     CIAN if self.usuario["rol"] == "ALMACEN" and o.get("FACTURA_VALIDADA") else MARINO)
        self.tarjeta(fila, o.get("EN_FINANZAS", 0), "En Recursos Financieros",
                     CIAN if self.usuario["rol"] == "FINANZAS" and o.get("EN_FINANZAS") else MARINO)
        self.tarjeta(fila, o.get("DEVUELTA", 0), "Devueltas por Finanzas", ROJO if o.get("DEVUELTA") else VERDE)
        fila2 = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila2.pack(fill="x", pady=(0, 8))
        self.tarjeta(fila2, t["excepciones"], "Excepciones abiertas", ROJO if t["excepciones"] else VERDE)
        self.tarjeta(fila2, o.get("PAGADA", 0), "Compras pagadas", VERDE)
        if not self.usuario.get("telegram_chat_id") and self.usuario.get("codigo_telegram"):
            aviso = ctk.CTkFrame(self.contenido, fg_color="white", corner_radius=12)
            aviso.pack(fill="x", pady=(10, 0))
            ctk.CTkLabel(aviso, text=f"📲 Recibe tus avisos en Telegram: abre el bot de Logix y envía  "
                                     f"/vincular {self.usuario['codigo_telegram']}",
                         font=("Segoe UI", 13, "bold"), text_color=MARINO).pack(anchor="w", padx=14, pady=10)
        ctk.CTkLabel(self.contenido, text="Semáforo del cierre de ejercicio (robot R6)", font=(FUENTE, 16, "bold"),
                     text_color=MARINO).pack(anchor="w", pady=(14, 0))
        estado = self.consultar(vigilante.estado_cierre)
        tabla = Tabla(self.contenido, [("Semáforo", 90), ("Folio", 120), ("Proveedor", 260), ("Estatus", 280),
                                       ("Importe", 110), ("Días al cierre", 110)])
        tabla.llenar(estado, lambda f: ["● " + f["semaforo"].title(), f["folio"], f["proveedor"],
                                        consultas.ESTATUS_LEGIBLE.get(f["estatus"], f["estatus"]), pesos(f["total"]),
                                        f["dias"]], etiqueta=lambda f: f["semaforo"])

    def _ver_folio(self, tabla):
        sel = tabla.seleccion()
        if sel:
            self.ir("Consultar folio")
            self.e_folio.insert(0, sel[0]["folio"])
            self._buscar_folio()

    # --- Adquisiciones: registrar una compra ya aprobada (robot R1)
    def v_registrar_compra(self):
        self.titulo("Registrar compra aprobada",
                    "La compra ya fue autorizada. Escribe a quién se le compró y qué se compró: Logix le pone "
                    "folio, genera la orden de compra (001-05) con QR y se la manda al proveedor para que facture.")
        self.provs = self.consultar(compras.proveedores_activos)
        self.lineas = []
        caja = ctk.CTkFrame(self.contenido, fg_color="white", corner_radius=12)
        caja.pack(fill="x", pady=6)
        ctk.CTkLabel(caja, text="Proveedor").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 0))
        self.cb_prov = ctk.CTkComboBox(caja, values=[f"{p['razon_social']} · {p['rfc']}" for p in self.provs],
                                       width=420, command=self._prov_elegido)
        self.cb_prov.grid(row=1, column=0, columnspan=3, sticky="w", padx=12)
        ctk.CTkLabel(caja, text="Área que pidió el material").grid(row=0, column=3, sticky="w", padx=12, pady=(12, 0))
        self.e_area = ctk.CTkEntry(caja, width=320, placeholder_text="Departamento de Sistemas y Computación")
        self.e_area.grid(row=1, column=3, columnspan=2, sticky="w", padx=12)
        self.l_prov = ctk.CTkLabel(caja, text="", font=("Segoe UI", 11), text_color=ROJO)
        self.l_prov.grid(row=2, column=0, columnspan=5, sticky="w", padx=12)
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
            self._prov_elegido(self.cb_prov.get())

    def _prov_actual(self):
        return next((p for p in self.provs if f"{p['razon_social']} · {p['rfc']}" == self.cb_prov.get()), None)

    def _prov_elegido(self, _):
        p = self._prov_actual()
        self.l_prov.configure(text=f"⚠ Este proveedor aparece en la lista 69-B del SAT ({p['sat_69b']}): "
                                   "su factura será rechazada." if p and p["sat_69b"] else "")

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
                              lambda f: f"Compra registrada con el folio {f}. Logix generó la orden de compra "
                                        "y ya se la mandó al proveedor con las instrucciones para facturar.")
        if folio:
            self.ir("Registrar compra")

    # --- Adquisiciones: lo que Finanzas regresó (comunicación de ida y vuelta)
    def v_devueltas(self):
        self.titulo("Devueltas por Finanzas",
                    "Recursos Financieros te regresó estos expedientes explicando qué falta o qué está mal. "
                    "Corrígelo (con el proveedor si hace falta) y reenvíalo con tu respuesta: Logix le avisa a Finanzas.")
        filas = self.consultar(pagos.devueltas)
        tabla = Tabla(self.contenido, [("OC", 120), ("Proveedor", 260), ("Importe", 110), ("Devuelta", 130),
                                       ("Motivo de Finanzas", 460)])
        tabla.llenar(filas, lambda f: [f["folio"], f["proveedor"], pesos(f["total"]), fecha(f["fecha"]), f["motivo"]],
                     etiqueta=lambda f: "ROJO")
        f = self.fila_botones()

        def abrir():
            s = tabla.seleccion()
            if s and s[0]["ruta_pdf"]:
                os.startfile(s[0]["ruta_pdf"])

        def reenviar():
            s = tabla.seleccion()
            if not s:
                messagebox.showinfo("Logix", "Selecciona un expediente devuelto.")
                return
            r = ctk.CTkInputDialog(title="Reenviar a Finanzas",
                                   text=f"¿Qué se corrigió en {s[0]['folio']}? (Finanzas lo leerá)").get_input()
            if r is not None:
                self.ejecutar(lambda cur: pagos.reenviar(cur, self.usuario, s[0]["id"], r),
                              f"{s[0]['folio']} reenviado a Recursos Financieros.")
                self.ir("Devueltas por Finanzas")
        self.boton(f, "Abrir expediente PDF", abrir, color=ACENTO).pack(side="left")
        self.boton(f, "↪ Reenviar a Finanzas", reenviar, color=CIAN).pack(side="left", padx=8)
        self.boton(f, "Ver seguimiento", lambda: self._ver_folio(tabla), color=ACENTO).pack(side="right")

    def v_excepciones(self):
        self.titulo("Excepciones", "Lo único que Logix no resuelve solo. Al corregirse con el proveedor, "
                                   "márcala como resuelta (y reactiva la OC si estaba detenida).")
        filas = self.consultar(consultas.excepciones_abiertas)
        tabla = Tabla(self.contenido, [("Fecha", 130), ("OC", 110), ("Tipo", 170), ("Detalle", 620)])
        tabla.llenar(filas, lambda f: [fecha(f["fecha"]), f["folio"] or "", f["tipo"], f["detalle"]],
                     etiqueta=lambda f: "ROJO")
        f = self.fila_botones()

        def resolver(reactivar):
            sel = tabla.seleccion()
            if not sel:
                return
            nota = ctk.CTkInputDialog(title="Resolver", text="¿Cómo se resolvió?").get_input()
            if nota:
                self.ejecutar(lambda cur: consultas.resolver_excepcion(cur, self.usuario, sel[0]["id"], nota,
                                                                       reactivar), "Excepción resuelta.")
                self.ir("Excepciones")
        self.boton(f, "Marcar resuelta", lambda: resolver(False)).pack(side="left")
        self.boton(f, "Resuelta y reactivar OC", lambda: resolver(True), color=CIAN).pack(side="left", padx=8)

    def v_buzon(self):
        self.titulo("Buzón de facturas (robot R2)",
                    "Los proveedores envían su XML por correo con el folio de la OC en el asunto y el robot lo "
                    "procesa solo. Para la demostración, aquí puedes simular la llegada de un correo.")
        f = self.fila_botones()
        self.e_oc_buzon = ctk.CTkEntry(f, placeholder_text="Folio de la OC (asunto del correo)", width=260)
        self.e_oc_buzon.pack(side="left")
        self.boton(f, "Simular correo con XML…", self._simular_correo, color=CIAN).pack(side="left", padx=8)
        self.boton(f, "Revisar buzón ahora", self._robots_ahora, color=ACENTO).pack(side="left")
        f2 = self.fila_botones()
        ctk.CTkLabel(f2, text="Simular al proveedor de esa OC:").pack(side="left")
        self.boton(f2, "Factura correcta", lambda: self._factura_simulada(False), color=VERDE).pack(side="left", padx=6)
        self.boton(f2, "Factura con importe equivocado", lambda: self._factura_simulada(True),
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
        self.titulo("Catálogo de proveedores (001-04)", "Comparte el código de Telegram con cada proveedor para que "
                                                        "se vincule con el bot (/vincular código): así recibe su orden "
                                                        "de compra, envía su factura y consulta su pago.")
        provs = self.consultar(compras.proveedores_activos)
        t = Tabla(self.contenido, [("Proveedor", 320), ("RFC", 130), ("Correo", 260), ("Telegram", 150),
                                   ("Lista 69-B", 120)], alto=8)
        t.llenar(provs, lambda p: [p["razon_social"], p["rfc"], p["correo"] or "",
                                   "✔ Vinculado" if p["telegram_chat_id"] else f"Código {p['codigo_telegram']}",
                                   f"⚠ {p['sat_69b']}" if p["sat_69b"] else "—"],
                 etiqueta=lambda p: "ROJO" if p["sat_69b"] else "VERDE")

    # --- Almacén: confirmar que el material llegó
    def v_recepcion(self):
        self.titulo("Recepción en almacén", "Solo aparecen las OC con factura ya validada. Revisa el material físico: "
                                            "si llegó completo, confírmalo y Logix manda el expediente a Recursos "
                                            "Financieros en ese momento. Si llegó mal, repórtalo y Logix avisa a "
                                            "Adquisiciones.")
        filas = self.consultar(recepcion.por_recibir)
        tabla = Tabla(self.contenido, [("OC", 120), ("Proveedor", 300), ("Área", 260), ("Importe", 110),
                                       ("Fecha OC", 130)])
        tabla.llenar(filas, lambda f: [f["folio"], f["proveedor"], f["area_solicitante"], pesos(f["total"]),
                                       fecha(f["fecha"])])
        f = self.fila_botones()
        fds = ctk.CTkCheckBox(f, text="Recibí la hoja de seguridad (FDS), si aplica")
        fds.pack(side="left")

        def confirmar():
            sel = tabla.seleccion()
            if sel:
                self.ejecutar(lambda cur: recepcion.confirmar_recepcion(cur, self.usuario, sel[0]["id"], bool(fds.get())),
                              lambda r: f"Recepción registrada (entrada {r[0]}, salida {r[1]}). "
                                        "Logix armó el expediente y lo mandó a Recursos Financieros.")
                self.ir("Recepción")

        def problema():
            sel = tabla.seleccion()
            if sel:
                d = ctk.CTkInputDialog(title="Reportar problema",
                                       text=f"¿Qué pasó con el material de {sel[0]['folio']}? "
                                            "(falta algo, llegó dañado, es diferente…)").get_input()
                if d is not None:
                    self.ejecutar(lambda cur: recepcion.reportar_problema(cur, self.usuario, sel[0]["id"], d),
                                  "Problema reportado. Logix avisó a Adquisiciones.")
                    self.ir("Recepción")
        self.boton(f, "✔ Llegó completo: confirmar", confirmar, color=VERDE).pack(side="right")
        self.boton(f, "⚠ Reportar problema", problema, color=ROJO).pack(side="right", padx=8)

    # --- Recursos Financieros (comunicación con Adquisiciones y robot R5)
    def v_pagos(self):
        self.titulo("Expedientes para pago", "Aquí llegan solos los expedientes completos (orden de compra + factura "
                                             "validada + entrada de almacén). El pago lo hace Recursos Financieros "
                                             "con su banco, fuera de Logix. Cada botón le avisa a Adquisiciones "
                                             "(y al proveedor cuando le interesa).")
        t2 = Tabla(self.contenido, [("OC", 120), ("Proveedor", 280), ("Área", 220), ("Importe", 110),
                                    ("Llegó", 130), ("Programado", 100)], alto=8)
        t2.llenar(self.consultar(pagos.por_pagar), lambda f: [f["folio"], f["proveedor"], f["area_solicitante"],
                                                              pesos(f["total"]), fecha(f["fecha_turno"]),
                                                              fecha(f["fecha_programada"])])
        f = self.fila_botones()

        def sel():
            s = t2.seleccion()
            if not s:
                messagebox.showinfo("Logix", "Selecciona un expediente.")
            return s[0] if s else None

        def abrir():
            s = sel()
            if s and s["ruta_pdf"]:
                os.startfile(s["ruta_pdf"])

        def programar():
            s = sel()
            if s:
                f_ = ctk.CTkInputDialog(title="Programar", text="Fecha de pago (AAAA-MM-DD):").get_input()
                if f_:
                    try:
                        dia = date.fromisoformat(f_.strip())
                    except ValueError:
                        messagebox.showwarning("Logix", "Escribe la fecha como AAAA-MM-DD, por ejemplo 2026-12-10.")
                        return
                    self.ejecutar(lambda cur: pagos.programar(cur, self.usuario, s["id"], dia),
                                  "Pago programado. Logix avisó a Adquisiciones y al proveedor.")
                    self.ir("Expedientes")

        def manual():
            s = sel()
            if s:
                ref = ctk.CTkInputDialog(title="Registrar pago", text="Referencia bancaria:").get_input()
                if ref:
                    self.ejecutar(lambda cur: pagos.registrar_pago(cur, self.usuario, s["id"], ref, date.today()),
                                  "Pago registrado. Logix avisó a Adquisiciones y al proveedor.")
                    self.ir("Expedientes")

        def devolver():
            s = sel()
            if s:
                m = ctk.CTkInputDialog(title="Devolver a Adquisiciones",
                                       text="¿Qué falta o qué está mal? (Adquisiciones lo leerá)").get_input()
                if m is not None:
                    self.ejecutar(lambda cur: pagos.devolver(cur, self.usuario, s["id"], m),
                                  "Devuelto a Adquisiciones con tu motivo.")
                    self.ir("Expedientes")

        def conciliar():
            ruta = filedialog.askopenfilename(title="Archivo del banco (CSV)", filetypes=[("CSV", "*.csv")])
            if ruta:
                destino = config.RAIZ / "banco" / "entrada"
                destino.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy(ruta, destino / os.path.basename(ruta))
                res = pagos.conciliar_carpeta()
                messagebox.showinfo("Robot R5", "\n".join(res) or "Sin movimientos.")
                self.ir("Expedientes")
        self.boton(f, "Abrir expediente PDF", abrir, color=ACENTO).pack(side="left")
        self.boton(f, "Programar fecha", programar).pack(side="left", padx=6)
        self.boton(f, "Conciliar archivo del banco…", conciliar, color=CIAN).pack(side="left", padx=6)
        self.boton(f, "Registrar pago manual", manual).pack(side="left", padx=6)
        self.boton(f, "↩ Devolver a Adquisiciones", devolver, color=ROJO).pack(side="right")

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
            ctk.CTkLabel(self.res_folio, text="⚠ Detenido fuera del camino normal: Adquisiciones ya fue avisada.",
                         text_color=ROJO).pack(anchor="w")
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
        self.titulo("Indicadores", "Se calculan solos desde la bitácora (métricas de la E4).")
        ind = self.consultar(consultas.indicadores)
        fila = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila.pack(fill="x", pady=8)
        self.tarjeta(fila, ind["facturas_procesadas"], "Facturas procesadas")
        self.tarjeta(fila, ind["facturas_rechazadas"], "Facturas detenidas", ROJO)
        self.tarjeta(fila, f"{ind['pct_ordenes_con_excepcion']}%", "Órdenes con excepción")
        fila2 = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila2.pack(fill="x", pady=8)
        envio = ind["min_promedio_envio_a_finanzas"]
        self.tarjeta(fila2, envio if envio is not None else "—", "Min. de almacén a Finanzas", VERDE)
        horas = ind["horas_promedio_en_finanzas"]
        self.tarjeta(fila2, horas if horas is not None else "—", "Horas en Finanzas hasta pago")
        self.tarjeta(fila2, ind["devoluciones_de_finanzas"], "Devoluciones de Finanzas")
        fila3 = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila3.pack(fill="x", pady=8)
        self.tarjeta(fila3, ind["ordenes_pagadas"], "Compras pagadas", VERDE)
        self.tarjeta(fila3, ind["hojas_impresas"], "Hojas impresas", VERDE)

    def v_bitacora(self):
        self.titulo("Bitácora de auditoría", "Quién hizo qué y cuándo. No se puede editar ni borrar.")
        tabla = Tabla(self.contenido, [("Fecha", 140), ("Actor", 130), ("Entidad", 80), ("Id", 50), ("Acción", 170),
                                       ("Antes", 120), ("Después", 140), ("Detalle", 330)], alto=20)
        tabla.llenar(self.consultar(consultas.bitacora), lambda b: [fecha(b["fecha"]), b["actor"], b["entidad"],
                     b["entidad_id"] or "", b["accion"], b["valor_anterior"] or "", b["valor_nuevo"] or "",
                     b["detalle"] or ""])


if __name__ == "__main__":
    App().mainloop()
