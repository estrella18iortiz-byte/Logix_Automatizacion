"""Toma las capturas de pantalla de evidencia del flujo completo (diagrama del 19-nov-2026).

    python capturar_evidencias.py

¡OJO! Reinicia la base con datos simulados. Abre el panel, lo maneja solo (como si una
persona diera los clics) y guarda una imagen PNG de cada pantalla en evidencias/.
Los mensajes emergentes se contestan solos y quedan anotados en evidencias/LEEME.md.
No toques el mouse mientras corre (tarda menos de un minuto).
"""
import time
from datetime import datetime, timedelta
from pathlib import Path

from PIL import ImageGrab

import generar_datos
import panel
from logix import banco_emulado, db

SALIDA = Path(__file__).resolve().parent / "evidencias"
NOTAS = []          # (archivo, descripción, mensajes que mostró Logix)
MENSAJES = []       # mensajes emergentes desde la última captura
RESPUESTAS = []     # lo que se «escribe» en los cuadros de texto, en orden


class MensajesFalsos:
    """Reemplaza las ventanas emergentes: guarda el texto en lugar de esperar un clic."""
    @staticmethod
    def showinfo(titulo, texto):
        MENSAJES.append(f"{titulo}: {texto}")

    showwarning = showinfo
    showerror = showinfo


class DialogoFalso:
    """Reemplaza CTkInputDialog: «escribe» la siguiente respuesta preparada."""
    def __init__(self, title="", text=""):
        self.text = text

    def get_input(self):
        r = RESPUESTAS.pop(0)
        MENSAJES.append(f"[Se escribió] {self.text} → {r}")
        return r


panel.messagebox = MensajesFalsos
panel.ctk.CTkInputDialog = DialogoFalso


def refrescar(app, espera=0.6):
    for _ in range(4):
        app.update_idletasks()
        app.update()
        time.sleep(espera / 4)


def captura(app, archivo: str, descripcion: str):
    refrescar(app)
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(SALIDA / archivo)
    NOTAS.append((archivo, descripcion, list(MENSAJES)))
    MENSAJES.clear()
    print("📸", archivo)


def entrar(app, usuario):
    app.pantalla_login()
    refrescar(app, 0.2)
    app.e_usuario.insert(0, usuario)
    app.e_pass.insert(0, generar_datos.PASSWORD_DEMO)
    app.entrar()
    refrescar(app, 0.3)


def seleccionar(tabla, folio):
    for iid, fila in tabla.datos.items():
        if fila.get("folio") == folio:
            tabla.selection_set(iid)
            return
    raise RuntimeError(f"No encontré {folio} en la tabla")


def tabla_de(app, n=0):
    """La n-ésima tabla de la pantalla actual."""
    tablas = []

    def buscar(w):
        for h in w.winfo_children():
            if isinstance(h, panel.Tabla):
                tablas.append(h)
            buscar(h)
    buscar(app.contenido)
    return tablas[n]


def boton(app, texto):
    def buscar(w):
        for h in w.winfo_children():
            if isinstance(h, panel.ctk.CTkButton) and texto in h.cget("text"):
                return h
            r = buscar(h)
            if r:
                return r
    b = buscar(app.contenido)
    if not b:
        raise RuntimeError(f"No encontré el botón «{texto}»")
    b.invoke()
    refrescar(app, 0.3)


def sql(texto, *params):
    with db.conexion() as con:
        con.cursor().execute(texto, *params)


def main():
    SALIDA.mkdir(exist_ok=True)
    for f in SALIDA.glob("*.png"):
        f.unlink()
    generar_datos.main()
    # Para que el semáforo de plazos tenga los tres colores: una OC a 4 h de vencer (rojo).
    sql("UPDATE ordenes_compra SET fecha = ? WHERE folio = 'OC-2026-0003'",
        datetime.now() - timedelta(days=6, hours=20))

    app = panel.App()
    app.attributes("-topmost", True)
    app.geometry("1366x800+20+20")
    refrescar(app, 1)
    captura(app, "01_inicio_de_sesion.png", "Pantalla de inicio de sesión (contraseña de prueba logix2026).")

    # ---------- Adquisiciones registra una compra aprobada (R1)
    entrar(app, "adquisiciones")
    captura(app, "02_adquisiciones_inicio.png", "Inicio de Adquisiciones: tarjetas por etapa y plazo del material (R3).")
    app.ir("Registrar compra")
    app.cb_prov.set(next(f"{p['razon_social']} · {p['rfc']}" for p in app.provs if p["rfc"] == "CDE020202BB2"))
    app.e_area.insert(0, "Departamento de Sistemas y Computación")
    for desc, uni, cant, precio in [("Mouse óptico USB", "Pieza", "5", "150"), ("Cable HDMI 2 m", "Pieza", "2", "180")]:
        app.e_desc.insert(0, desc); app.e_unidad.insert(0, uni); app.e_cant.insert(0, cant); app.e_precio.insert(0, precio)
        app._agregar_linea()
    captura(app, "03_registrar_compra.png", "Adquisiciones captura la compra ya aprobada con un proveedor fijo.")
    boton(app, "Registrar y enviar al proveedor")
    captura(app, "04_compra_registrada_OC_enviada.png",
            "R1 generó la OC-2026-0007 en PDF con QR y la mandó al proveedor por correo y Telegram.")

    # ---------- Jefe de Almacén: plazos, devolución y llegó bien
    entrar(app, "almacen")
    app.ir("Recepción")
    captura(app, "05_almacen_plazos_7_dias.png",
            "Jefe de Almacén: órdenes esperando material con semáforo del plazo de 7 días (rojo = vence pronto).")
    seleccionar(tabla_de(app), "OC-2026-0003")
    RESPUESTAS.append("Llegaron 3 cables, 1 con el conector roto")
    boton(app, "Devolución")
    captura(app, "06_almacen_devolucion_con_razon.png",
            "Devolución: el jefe escribe la razón; la compra se cancela y se avisa a Adquisiciones y al proveedor.")

    # ---------- Proveedor manda factura correcta antes de que llegue el material (R2)
    entrar(app, "adquisiciones")
    app.ir("Buzón de facturas")
    app.e_oc_buzon.insert(0, "OC-2026-0007")
    app._factura_simulada(False)
    app.e_oc_buzon.insert(0, "OC-2026-0004")
    app._factura_simulada(True)
    captura(app, "07_buzon_factura_valida_y_rechazada.png",
            "R2 validó la factura de la OC-2026-0007 y rechazó la de la OC-2026-0004 (importe distinto → cancelada).")
    app.ir("Compras canceladas")
    captura(app, "08_compras_canceladas_con_razon.png",
            "Compras canceladas con su causa y la razón que se le mandó al proveedor.")

    # ---------- Llegó bien → expediente → pago automático confirmado (R4 y R5)
    entrar(app, "almacen")
    app.ir("Recepción")
    seleccionar(tabla_de(app), "OC-2026-0007")
    boton(app, "Llegó bien")
    captura(app, "09_almacen_llego_bien_pago_automatico.png",
            "El material llegó bien y la factura ya estaba validada: R4 armó el expediente y R5 pagó en el banco.")
    entrar(app, "finanzas")
    app.ir("Pagos")
    captura(app, "10_finanzas_pago_confirmado.png", "Finanzas ve el pago confirmado por el banco con su clave de rastreo.")

    # ---------- Error del banco: saldo insuficiente → Finanzas reintenta
    sql("UPDATE banco_cuenta SET saldo = 50 WHERE id = 1")
    entrar(app, "almacen")
    app.ir("Recepción")
    seleccionar(tabla_de(app), "OC-2026-0001")
    boton(app, "Llegó bien")
    entrar(app, "adquisiciones")
    app.ir("Buzón de facturas")
    app.e_oc_buzon.insert(0, "OC-2026-0001")
    app._factura_simulada(False)
    entrar(app, "finanzas")
    app.ir("Pagos")
    captura(app, "11_finanzas_error_saldo_insuficiente.png",
            "El banco respondió SALDO_INSUFICIENTE: no se reintenta solo; Finanzas decide (reintentar o cancelar).")
    app.ir("Banco emulado")
    with db.conexion() as con:
        banco_emulado.depositar(con.cursor(), 250000)
    app.ir("Banco emulado")
    captura(app, "12_banco_emulado.png", "Banco emulado: saldo, falla simulada y cada respuesta del banco.")
    app.ir("Pagos")
    seleccionar(tabla_de(app), "OC-2026-0001")
    boton(app, "Reintentar pago")
    captura(app, "13_finanzas_reintento_confirmado.png", "Con saldo, Finanzas reintentó y el banco confirmó el pago.")

    # ---------- Error general: 3 reintentos automáticos → Finanzas cancela
    sql("UPDATE banco_cuenta SET falla_simulada = 'ERROR_GENERAL' WHERE id = 1")
    entrar(app, "almacen")
    app.ir("Recepción")
    seleccionar(tabla_de(app), "OC-2026-0006")
    boton(app, "Llegó bien")
    entrar(app, "adquisiciones")
    app.ir("Buzón de facturas")
    app.e_oc_buzon.insert(0, "OC-2026-0006")
    app._factura_simulada(False)
    entrar(app, "admin")
    app.ir("Robots y avisos")
    for _ in range(2):
        boton(app, "Ejecutar todos los robots ahora")      # 2 vueltas = intentos 2 y 3
    entrar(app, "finanzas")
    app.ir("Pagos")
    captura(app, "14_finanzas_error_general_3_intentos.png",
            "ERROR_GENERAL: el robot reintentó solo 3 veces; después pasó a Finanzas.")
    seleccionar(tabla_de(app), "OC-2026-0006")
    RESPUESTAS.append("El banco no responde desde hace dos días; se recompra con otro trámite")
    boton(app, "Cancelar pago")
    sql("UPDATE banco_cuenta SET falla_simulada = 'NINGUNA' WHERE id = 1")
    captura(app, "15_finanzas_cancela_pago.png",
            "Finanzas canceló el pago con motivo: se avisó al proveedor y a Adquisiciones; el material se devuelve.")

    # ---------- Seguimiento, avisos, indicadores y bitácora
    app.ir("Consultar folio")
    app.e_folio.insert(0, "OC-2026-0007")
    app._buscar_folio()
    captura(app, "16_seguimiento_pagada.png", "Seguimiento de la OC-2026-0007: Pagada, con su línea de tiempo.")
    app.ir("Consultar folio")
    app.e_folio.insert(0, "OC-2026-0004")
    app._buscar_folio()
    captura(app, "17_seguimiento_cancelada.png", "Seguimiento de una compra cancelada por factura no válida.")
    entrar(app, "almacen")
    app.ir("Recepción")
    captura(app, "18_almacen_material_por_devolver.png", "Material por devolver al proveedor (compras canceladas).")
    entrar(app, "admin")
    app.ir("Robots y avisos")
    captura(app, "19_avisos_correo_y_telegram.png", "Cola de avisos por correo y Telegram (modo simulado).")
    app.ir("Indicadores")
    captura(app, "20_indicadores.png", "Indicadores calculados solos desde la base y la bitácora.")
    app.ir("Bitácora")
    captura(app, "21_bitacora.png", "Bitácora de auditoría (no se puede modificar ni borrar).")
    app.destroy()

    _pdfs()
    with open(SALIDA / "LEEME.md", "w", encoding="utf-8") as fh:
        fh.write(f"# Evidencias · Logix 3.0 (diagrama del 19-nov-2026)\n\nGeneradas el {datetime.now():%d/%m/%Y %H:%M} "
                 "con `python capturar_evidencias.py` (datos simulados).\n\n")
        for archivo, descripcion, mensajes in NOTAS:
            fh.write(f"## {archivo}\n{descripcion}\n\n![{archivo}]({archivo})\n\n")
            for m in mensajes:
                fh.write(f"> {m.replace(chr(10), ' ')}\n>\n")
            fh.write("\n")
    print(f"Listo: {len(NOTAS)} capturas en {SALIDA}")


def _pdfs():
    """Convierte a imagen la primera página de la OC y del expediente de la OC-2026-0007."""
    try:
        import pymupdf
    except ImportError:
        return
    from logix import config
    carpeta = config.DOCUMENTOS / "expedientes" / "OC-2026-0007"
    for pdf, archivo, desc in [("OC-2026-0007_orden_de_compra.pdf", "22_pdf_orden_de_compra.png",
                                "PDF de la orden de compra (001-05) con QR que recibe el proveedor."),
                               ("OC-2026-0007_expediente.pdf", "23_pdf_expediente_finanzas.png",
                                "PDF del expediente para Recursos Financieros (memorándum + revisión automática).")]:
        ruta = carpeta / pdf
        if ruta.exists():
            with pymupdf.open(ruta) as doc:
                doc[0].get_pixmap(dpi=110).save(SALIDA / archivo)
            NOTAS.append((archivo, desc, []))
            print("📄", archivo)


if __name__ == "__main__":
    main()
