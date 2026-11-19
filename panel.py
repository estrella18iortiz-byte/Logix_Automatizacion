"""Panel Logix (CustomTkinter): lo único que usan las personas.

    python panel.py

Cada rol ve solo sus pantallas. Las personas solo deciden, autorizan, verifican el
bien físico y pagan; lo demás lo hacen los robots (robot.py).
"""
import os
import tkinter as tk
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from PIL import Image

import robot
from logix import (compras, config, consultas, db, firmas, pagos, recepcion, requisiciones,
                   usuarios, vigilante)
from logix.cfdi_simulado import generar_xml
from logix.errores import ReglaNegocio
from logix.robot_facturas import PATRON_OC, procesar_factura

MARINO, CIAN, ACENTO, FONDO = "#0B2545", "#00A8E8", "#8DA9C4", "#EEF4F8"
VERDE, AMARILLO, ROJO = "#2E9E5B", "#E0A800", "#C0392B"
FUENTE = "Century Gothic"

MENUS = {
    "SOLICITANTE": ["Inicio", "Nueva requisición", "Mis requisiciones", "Recibir material", "Consultar folio"],
    "JEFE_AREA": ["Inicio", "Firmas pendientes", "Nueva requisición", "Mis requisiciones", "Recibir material",
                  "Consultar folio"],
    "PRESUPUESTOS": ["Inicio", "Firmas pendientes", "Consultar folio"],
    "SUBDIRECTOR": ["Inicio", "Firmas pendientes", "Consultar folio"],
    "DIRECTOR": ["Inicio", "Firmas pendientes", "Consultar folio"],
    "JEFE_RM": ["Inicio", "Firmas pendientes", "Consultar folio"],
    "SUBDIR_ADMIN": ["Inicio", "Firmas pendientes", "Consultar folio"],
    "ADQUISICIONES": ["Inicio", "Firmas pendientes", "Generar orden de compra", "Excepciones",
                      "Buzón de facturas", "Proveedores", "Consultar folio"],
    "ALMACEN": ["Inicio", "Recepción", "Consultar folio"],
    "FINANZAS": ["Inicio", "Pagos", "Consultar folio"],
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
        self.title("Logix · Seguimiento del expediente de compra directa")
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
            "Inicio": self.v_inicio, "Nueva requisición": self.v_nueva_req, "Mis requisiciones": self.v_mis_req,
            "Firmas pendientes": self.v_firmas, "Generar orden de compra": self.v_generar_oc,
            "Excepciones": self.v_excepciones, "Buzón de facturas": self.v_buzon, "Proveedores": self.v_proveedores,
            "Recepción": self.v_recepcion, "Recibir material": self.v_recibir, "Pagos": self.v_pagos,
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
                    "Logix hace el trámite; tú solo decides, autorizas o verificas. "
                    "Lo que necesita tu atención aparece aquí.")
        t = self.consultar(consultas.tablero)
        mis_firmas = len(self.consultar(lambda c: firmas.pendientes_de(c, self.usuario)))
        fila = ctk.CTkFrame(self.contenido, fg_color="transparent")
        fila.pack(fill="x", pady=8)
        self.tarjeta(fila, mis_firmas, "Firmas que te tocan", CIAN if mis_firmas else MARINO)
        self.tarjeta(fila, t["firmas_pendientes"], "Firmas pendientes (todas)")
        self.tarjeta(fila, t["excepciones"], "Excepciones abiertas", ROJO if t["excepciones"] else VERDE)
        self.tarjeta(fila, t["ordenes"].get("PAGADA", 0), "Compras pagadas", VERDE)
        if not self.usuario.get("telegram_chat_id") and self.usuario.get("codigo_telegram"):
            aviso = ctk.CTkFrame(self.contenido, fg_color="white", corner_radius=12)
            aviso.pack(fill="x", pady=(10, 0))
            ctk.CTkLabel(aviso, text=f"📲 Recibe tus avisos en Telegram: abre el bot de Logix y envía  "
                                     f"/vincular {self.usuario['codigo_telegram']}",
                         font=("Segoe UI", 13, "bold"), text_color=MARINO).pack(anchor="w", padx=14, pady=10)
        ctk.CTkLabel(self.contenido, text="Semáforo del cierre de ejercicio (robot R6)", font=(FUENTE, 16, "bold"),
                     text_color=MARINO).pack(anchor="w", pady=(14, 0))
        estado = self.consultar(vigilante.estado_cierre)
        tabla = Tabla(self.contenido, [("Semáforo", 90), ("Folio", 120), ("Proveedor", 260), ("Estatus", 260),
                                       ("Importe", 110), ("Días al cierre", 110)])
        tabla.llenar(estado, lambda f: ["● " + f["semaforo"].title(), f["folio"], f["proveedor"],
                                        consultas.ESTATUS_LEGIBLE.get(f["estatus"], f["estatus"]), pesos(f["total"]),
                                        f["dias"]], etiqueta=lambda f: f["semaforo"])

    # --- Solicitante: nueva requisición (R1)
    def v_nueva_req(self):
        self.titulo("Nueva requisición (formato 001-03)",
                    "Elige qué necesitas y cuánto. Logix asigna la partida, propone el precio de referencia "
                    "y revisa el saldo antes de enviar. Después la manda sola a las 4 firmas.")
        self.catalogo = self.consultar(requisiciones.catalogo_conceptos)
        self.lineas = []
        caja = ctk.CTkFrame(self.contenido, fg_color="white", corner_radius=12)
        caja.pack(fill="x", pady=6)
        nombres = [c["descripcion"] for c in self.catalogo]
        self.cb_concepto = ctk.CTkComboBox(caja, values=nombres, width=380, command=self._concepto_elegido)
        self.cb_concepto.grid(row=0, column=0, padx=12, pady=12)
        self.e_cant = ctk.CTkEntry(caja, placeholder_text="Cantidad", width=90)
        self.e_cant.grid(row=0, column=1, padx=6)
        self.e_precio = ctk.CTkEntry(caja, placeholder_text="Precio con IVA", width=120)
        self.e_precio.grid(row=0, column=2, padx=6)
        self.boton(caja, "Agregar", self._agregar_linea, width=100).grid(row=0, column=3, padx=12)
        self.l_info = ctk.CTkLabel(caja, text="", font=("Segoe UI", 11), text_color="#4A5D73")
        self.l_info.grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 10))
        self.t_lineas = Tabla(self.contenido, [("Concepto", 330), ("Partida", 80), ("Cantidad", 80),
                                               ("Precio", 100), ("Importe", 110)], alto=6)
        self.l_total = ctk.CTkLabel(self.contenido, text="Total: $0.00", font=(FUENTE, 16, "bold"), text_color=MARINO)
        self.l_total.pack(anchor="e")
        self.t_just = ctk.CTkTextbox(self.contenido, height=70)
        self.t_just.pack(fill="x", pady=6)
        self.t_just.insert("1.0", "Justificación: ")
        f = self.fila_botones()
        self.boton(f, "Quitar renglón", self._quitar_linea, color=ACENTO).pack(side="left")
        self.boton(f, "Enviar a firmas", self._enviar_req, color=CIAN).pack(side="right")
        self._concepto_elegido(nombres[0])

    def _concepto_elegido(self, nombre):
        c = next(x for x in self.catalogo if x["descripcion"] == nombre)
        self.e_precio.delete(0, "end")
        self.e_precio.insert(0, f"{c['precio_referencia']:.2f}")
        self.l_info.configure(text=f"Partida {c['partida']} · {c['partida_desc']} · saldo disponible "
                                   f"{pesos(c['saldo'])} · precio de referencia {pesos(c['precio_referencia'])}")

    def _agregar_linea(self):
        try:
            cant, precio = Decimal(self.e_cant.get()), Decimal(self.e_precio.get())
        except InvalidOperation:
            messagebox.showwarning("Logix", "Escribe la cantidad y el precio con números.")
            return
        c = next(x for x in self.catalogo if x["descripcion"] == self.cb_concepto.get())
        self.lineas.append((c, cant, precio))
        self._refrescar_lineas()
        self.e_cant.delete(0, "end")

    def _quitar_linea(self):
        sel = self.t_lineas.selection()
        if sel:
            self.lineas.pop(self.t_lineas.index(sel[0]))
            self._refrescar_lineas()

    def _refrescar_lineas(self):
        self.t_lineas.llenar(self.lineas, lambda l: [l[0]["descripcion"], l[0]["partida"], f"{l[1]:g}",
                                                    pesos(l[2]), pesos(l[1] * l[2])])
        self.l_total.configure(text=f"Total: {pesos(sum(c * p for _, c, p in self.lineas))}")

    def _enviar_req(self):
        just = self.t_just.get("1.0", "end").replace("Justificación:", "").strip()
        lineas = [(c["id"], cant, p) for c, cant, p in self.lineas]
        folio = self.ejecutar(lambda cur: requisiciones.crear(cur, self.usuario, just, lineas),
                              lambda f: f"Requisición {f} enviada. Logix ya avisó al Jefe de tu área.")
        if folio:
            self.ir("Mis requisiciones")

    def v_mis_req(self):
        self.titulo("Requisiciones de mi área", "Si una requisición fue devuelta, selecciónala para corregirla.")
        filas = self.consultar(lambda c: requisiciones.de_usuario(c, self.usuario))
        tabla = Tabla(self.contenido, [("Folio", 120), ("Fecha", 130), ("Total", 100), ("Estatus", 220),
                                       ("Motivo de devolución", 380)])
        tabla.llenar(filas, lambda f: [f["folio"], fecha(f["fecha"]), pesos(f["total"]),
                                       consultas.ESTATUS_LEGIBLE.get(f["estatus"], f["estatus"]),
                                       f["motivo"] if f["estatus"] == "EN_CORRECCION" else ""])
        f = self.fila_botones()
        self.boton(f, "Corregir y reenviar", lambda: self._corregir(tabla)).pack(side="left")
        self.boton(f, "Ver seguimiento", lambda: self._ver_folio(tabla), color=ACENTO).pack(side="left", padx=8)

    def _corregir(self, tabla):
        sel = tabla.seleccion()
        if not sel or sel[0]["estatus"] != "EN_CORRECCION":
            messagebox.showinfo("Logix", "Selecciona una requisición devuelta.")
            return
        req = sel[0]
        det = self.consultar(lambda c: requisiciones.detalle(c, req["id"]))
        cambios = {}
        for d in det:
            r = ctk.CTkInputDialog(title="Corregir", text=f"{d['descripcion']}\nCantidad actual {d['cantidad']:g} · "
                                   f"precio {pesos(d['precio_unitario'])}\nEscribe «cantidad, precio» "
                                   "(vacío = sin cambio):").get_input()
            if r:
                try:
                    cant, precio = (Decimal(x.strip()) for x in r.split(","))
                    cambios[d["id"]] = (cant, precio)
                except (ValueError, InvalidOperation):
                    messagebox.showwarning("Logix", "Formato: 8, 150")
                    return
        self.ejecutar(lambda cur: requisiciones.corregir_y_reenviar(cur, self.usuario, req["id"], cambios),
                      f"{req['folio']} corregida y reenviada a firmas.")
        self.ir("Mis requisiciones")

    def _ver_folio(self, tabla):
        sel = tabla.seleccion()
        if sel:
            self.ir("Consultar folio")
            self.e_folio.insert(0, sel[0]["folio"])
            self._buscar_folio()

    # --- Firmas (R2)
    def v_firmas(self):
        self.titulo("Firmas pendientes", "Revisa y autoriza con un botón. Si algo no está bien, devuélvelo con su "
                                          "motivo. Logix turna al siguiente nivel y avisa solo.")
        filas = self.consultar(lambda c: firmas.pendientes_de(c, self.usuario))
        tabla = Tabla(self.contenido, [("Tipo", 150), ("Folio", 120), ("Nivel", 60), ("Importe", 110),
                                       ("Detalle", 420), ("Asignada", 130)])
        tabla.llenar(filas, lambda f: [firmas.NOMBRES[f["tipo"]].capitalize(), f["folio"], f["nivel"],
                                       pesos(f["total"]), f["detalle"], fecha(f["fecha_asignacion"])])
        f = self.fila_botones()
        self.boton(f, "✔ Aprobar", lambda: self._firmar(tabla, True), color=VERDE).pack(side="left")
        self.boton(f, "↩ Devolver con motivo", lambda: self._firmar(tabla, False), color=ROJO).pack(side="left",
                                                                                                    padx=8)
        self.boton(f, "Ver seguimiento", lambda: self._ver_folio(tabla), color=ACENTO).pack(side="right")

    def _firmar(self, tabla, aprobar):
        sel = tabla.seleccion()
        if not sel:
            messagebox.showinfo("Logix", "Selecciona una firma.")
            return
        a = sel[0]
        if aprobar:
            self.ejecutar(lambda cur: firmas.aprobar(cur, self.usuario, a["id"]), f"{a['folio']} aprobada.")
        else:
            motivo = ctk.CTkInputDialog(title="Devolver", text=f"Motivo para devolver {a['folio']}:").get_input()
            if motivo is None:
                return
            self.ejecutar(lambda cur: firmas.devolver(cur, self.usuario, a["id"], motivo), f"{a['folio']} devuelta.")
        self.ir("Firmas pendientes")

    # --- Adquisiciones (R8, R9)
    def v_generar_oc(self):
        self.titulo("Generar orden de compra (001-05)",
                    "Elige una o varias requisiciones validadas. Logix ya filtró a los proveedores: "
                    "solo puedes elegir a los aptos y el primero es el sugerido.")
        reqs = self.consultar(compras.requisiciones_validadas)
        t_req = Tabla(self.contenido, [("Folio", 120), ("Área", 300), ("Total", 110), ("Justificación", 420)], alto=5)
        t_req.llenar(reqs, lambda f: [f["folio"], f["area"], pesos(f["total"]), f["justificacion"]])
        provs = self.consultar(compras.evaluar_proveedores)
        ctk.CTkLabel(self.contenido, text="Proveedores (robot R8)", font=(FUENTE, 15, "bold"),
                     text_color=MARINO).pack(anchor="w")
        t_prov = Tabla(self.contenido, [("Dictamen", 90), ("Proveedor", 300), ("RFC", 130), ("Puntaje", 70),
                                        ("Motivo", 420)], alto=6)
        t_prov.llenar(provs, lambda p: ["✔ Apto" if p["apto"] else "✘ No apto", p["razon_social"], p["rfc"],
                                        p["puntaje_evaluacion"], p["motivo"]],
                      etiqueta=lambda p: "VERDE" if p["apto"] else "ROJO")
        f = self.fila_botones()
        cotiz = ctk.CTkCheckBox(f, text="Adjunté cotizaciones comparativas (obligatorio > $300,000)")
        cotiz.pack(side="left")

        def generar():
            r, p = t_req.seleccion(), t_prov.seleccion()
            if not r or not p:
                messagebox.showinfo("Logix", "Selecciona requisición(es) y un proveedor.")
                return
            folio = self.ejecutar(lambda cur: compras.crear_oc(cur, self.usuario, [x["id"] for x in r], p[0]["id"],
                                                               bool(cotiz.get())),
                                  lambda fo: f"Orden {fo} creada y enviada a firmas. Al autorizarse, Logix genera el "
                                             "PDF y se lo manda al proveedor.")
            if folio:
                self.ir("Generar orden de compra")
        self.boton(f, "Generar OC", generar, color=CIAN).pack(side="right")

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
        self.titulo("Buzón de facturas (robot R3)",
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
            messagebox.showinfo("Robot R3", f"Resultado: {res}" + (f"\nReglas: {', '.join(cods)}" if cods else ""))
            self.ir("Buzón de facturas")

    def _factura_simulada(self, con_error: bool):
        """Fabrica el XML que mandaría el proveedor de la OC y se lo da al robot R3."""
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
            messagebox.showinfo("Robot R3", f"Resultado: {r[0]}" + (f"\nReglas: {', '.join(r[1])}" if r[1] else ""))
            self.ir("Buzón de facturas")

    def v_proveedores(self):
        self.titulo("Catálogo de proveedores (001-04)", "Dictamen automático: evaluación 001-02 de más de 70 puntos, "
                                                        "vigente (menos de 1 año) y fuera de la lista 69-B del SAT. "
                                                        "Comparte el código de Telegram con cada proveedor para que "
                                                        "se vincule con el bot (/vincular código).")
        provs = self.consultar(compras.evaluar_proveedores)
        t = Tabla(self.contenido, [("Dictamen", 90), ("Proveedor", 290), ("RFC", 120), ("Puntaje", 70),
                                   ("Evaluado", 95), ("Telegram", 150), ("Motivo", 330)], alto=8)
        t.llenar(provs, lambda p: ["✔ Apto" if p["apto"] else "✘ No apto", p["razon_social"], p["rfc"],
                                   p["puntaje_evaluacion"], fecha(p["fecha_evaluacion"]),
                                   "✔ Vinculado" if p["telegram_chat_id"] else f"Código {p['codigo_telegram']}",
                                   p["motivo"]],
                 etiqueta=lambda p: "VERDE" if p["apto"] else "ROJO")

    # --- Almacén y área
    def v_recepcion(self):
        self.titulo("Recepción en almacén", "Solo aparecen las OC con factura ya validada por el robot. Revisa el bien "
                                            "físico y confirma: Logix genera la entrada y la salida y avisa al área.")
        filas = self.consultar(recepcion.por_recibir)
        tabla = Tabla(self.contenido, [("OC", 120), ("Proveedor", 340), ("Importe", 110), ("Fecha OC", 130)])
        tabla.llenar(filas, lambda f: [f["folio"], f["proveedor"], pesos(f["total"]), fecha(f["fecha"])])
        f = self.fila_botones()
        fds = ctk.CTkCheckBox(f, text="Recibí la hoja de seguridad (FDS), si aplica")
        fds.pack(side="left")

        def confirmar():
            sel = tabla.seleccion()
            if sel:
                self.ejecutar(lambda cur: recepcion.confirmar_recepcion(cur, self.usuario, sel[0]["id"], bool(fds.get())),
                              lambda r: f"Recepción registrada. Entrada {r[0]} y salida {r[1]}.")
                self.ir("Recepción")
        self.boton(f, "✔ El bien coincide: confirmar recepción", confirmar, color=VERDE).pack(side="right")

    def v_recibir(self):
        self.titulo("Recibir material", "Al recoger tu material, firma de recibido y califica al proveedor. "
                                        "Con tu firma Logix arma el expediente y lo manda a autorización de pago.")
        filas = self.consultar(lambda c: recepcion.por_firmar_area(c, self.usuario))
        tabla = Tabla(self.contenido, [("OC", 120), ("Proveedor", 340), ("Importe", 110), ("Recibido en almacén", 160)])
        tabla.llenar(filas, lambda f: [f["folio"], f["proveedor"], pesos(f["total"]), fecha(f["fecha_recepcion"])])
        f = self.fila_botones()
        ctk.CTkLabel(f, text="Calificación del proveedor:").pack(side="left")
        calif = ctk.CTkSegmentedButton(f, values=["1", "2", "3", "4", "5"])
        calif.set("5")
        calif.pack(side="left", padx=8)

        def firmar():
            sel = tabla.seleccion()
            if sel:
                self.ejecutar(lambda cur: recepcion.firmar_recibido(cur, self.usuario, sel[0]["id"], int(calif.get())),
                              "Firma registrada. Logix integró el expediente y lo turnó a autorización de pago.")
                self.ir("Recibir material")
        self.boton(f, "✔ Firmar de recibido", firmar, color=VERDE).pack(side="right")

    # --- Finanzas (R10)
    def v_pagos(self):
        self.titulo("Pagos", "La dispersión bancaria la hace Recursos Financieros fuera de Logix. Logix te avisa lo que "
                             "viene en camino y concilia el archivo del banco para marcar los pagos.")
        ctk.CTkLabel(self.contenido, text="En camino (pre-alerta)", font=(FUENTE, 15, "bold"),
                     text_color=MARINO).pack(anchor="w")
        t1 = Tabla(self.contenido, [("OC", 120), ("Proveedor", 340), ("Importe", 110), ("Firmas de pago", 120)], alto=4)
        t1.llenar(self.consultar(pagos.en_camino), lambda f: [f["folio"], f["proveedor"], pesos(f["total"]),
                                                              f"{f['firmas']} de 3"])
        ctk.CTkLabel(self.contenido, text="Turnados para pago", font=(FUENTE, 15, "bold"),
                     text_color=MARINO).pack(anchor="w")
        t2 = Tabla(self.contenido, [("OC", 120), ("Proveedor", 300), ("Importe", 110), ("Turnado", 130),
                                    ("Programado", 100)], alto=6)
        t2.llenar(self.consultar(pagos.por_pagar), lambda f: [f["folio"], f["proveedor"], pesos(f["total"]),
                                                              fecha(f["fecha_turno"]), fecha(f["fecha_programada"])])
        f = self.fila_botones()

        def sel():
            s = t2.seleccion()
            if not s:
                messagebox.showinfo("Logix", "Selecciona un expediente turnado.")
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
                    self.ejecutar(lambda cur: pagos.programar(cur, self.usuario, s["id"], date.fromisoformat(f_)),
                                  "Pago programado.")
                    self.ir("Pagos")

        def manual():
            s = sel()
            if s:
                ref = ctk.CTkInputDialog(title="Registrar pago", text="Referencia bancaria:").get_input()
                if ref:
                    self.ejecutar(lambda cur: pagos.registrar_pago(cur, self.usuario, s["id"], ref, date.today()),
                                  "Pago registrado y proveedor avisado.")
                    self.ir("Pagos")

        def devolver():
            s = sel()
            if s:
                m = ctk.CTkInputDialog(title="Devolver", text="Motivo:").get_input()
                if m:
                    self.ejecutar(lambda cur: pagos.devolver(cur, self.usuario, s["id"], m), "Devuelto a Adquisiciones.")
                    self.ir("Pagos")

        def conciliar():
            ruta = filedialog.askopenfilename(title="Archivo del banco (CSV)", filetypes=[("CSV", "*.csv")])
            if ruta:
                destino = config.RAIZ / "banco" / "entrada"
                destino.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy(ruta, destino / os.path.basename(ruta))
                res = pagos.conciliar_carpeta()
                messagebox.showinfo("Robot R10", "\n".join(res) or "Sin movimientos.")
                self.ir("Pagos")
        self.boton(f, "Abrir expediente PDF", abrir, color=ACENTO).pack(side="left")
        self.boton(f, "Programar fecha", programar).pack(side="left", padx=6)
        self.boton(f, "Conciliar archivo del banco…", conciliar, color=CIAN).pack(side="left", padx=6)
        self.boton(f, "Registrar pago manual", manual).pack(side="left", padx=6)
        self.boton(f, "Devolver", devolver, color=ROJO).pack(side="right")

    # --- Seguimiento (todos)
    def v_folio(self):
        self.titulo("Consultar folio", "Escribe un folio de requisición (REQ-), de orden (OC-) o un ticket de pago (PAG-).")
        f = self.fila_botones()
        self.e_folio = ctk.CTkEntry(f, placeholder_text="REQ-2026-0001 / OC-2026-0001 / PAG-2026-0001", width=340)
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
            ctk.CTkLabel(self.res_folio, text="⚠ Detenido por una excepción: Adquisiciones ya fue avisada.",
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
        self.tarjeta(fila2, ind["min_promedio_armado_expediente"] if ind["min_promedio_armado_expediente"] is not None
                     else "—", "Min. para armar expediente", VERDE)
        self.tarjeta(fila2, ind["ordenes_pagadas"], "Compras pagadas", VERDE)
        self.tarjeta(fila2, ind["hojas_impresas"], "Hojas impresas", VERDE)

    def v_bitacora(self):
        self.titulo("Bitácora de auditoría", "Quién hizo qué y cuándo. No se puede editar ni borrar.")
        tabla = Tabla(self.contenido, [("Fecha", 140), ("Actor", 130), ("Entidad", 80), ("Id", 50), ("Acción", 170),
                                       ("Antes", 120), ("Después", 140), ("Detalle", 330)], alto=20)
        tabla.llenar(self.consultar(consultas.bitacora), lambda b: [fecha(b["fecha"]), b["actor"], b["entidad"],
                     b["entidad_id"] or "", b["accion"], b["valor_anterior"] or "", b["valor_nuevo"] or "",
                     b["detalle"] or ""])


if __name__ == "__main__":
    App().mainloop()
