"""Toma las capturas de pantalla de evidencia del flujo completo (Logix 3.1: eventos simulados, sin Adquisiciones).

    python capturar_evidencias.py

¡OJO! Reinicia la base con datos simulados. Abre el panel, lo maneja solo (como si una
persona diera los clics) y guarda una imagen PNG de cada pantalla en evidencias/.
Los mensajes emergentes se contestan solos y quedan anotados en evidencias/LEEME.md.
No toques el mouse mientras corre (tarda menos de un minuto).
"""
import random
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


panel.config.MODO_SIMULADO = True    # las capturas nunca envían correos ni Telegram reales
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


def combo(app, valor):
    """Elige un valor en la primera lista desplegable de la pantalla."""
    def buscar(w):
        for h in w.winfo_children():
            if isinstance(h, panel.ctk.CTkComboBox):
                return h
            r = buscar(h)
            if r:
                return r
    buscar(app.contenido).set(valor)


def sql(texto, *params):
    with db.conexion() as con:
        con.cursor().execute(texto, *params)


def main():
    SALIDA.mkdir(exist_ok=True)
    for f in SALIDA.glob("*.png"):
        f.unlink()
    generar_datos.main()
    sql("UPDATE parametros SET valor = '0' WHERE clave IN ('MINUTOS_PAGO_MIN', 'MINUTOS_PAGO_MAX')")  # pago al instante
    # Para que el semáforo de plazos tenga los tres colores: una OC a 4 h de vencer (rojo).
    sql("UPDATE ordenes_compra SET fecha = ? WHERE folio = 'OC-2026-0003'",
        datetime.now() - timedelta(days=6, hours=20))

    app = panel.App()
    app.attributes("-topmost", True)
    app.geometry("1366x800+20+20")
    refrescar(app, 1)
    captura(app, "01_inicio_de_sesion.png", "Pantalla de inicio de sesión (contraseña de prueba logix2026).")

    # ---------- Llega una requisición validada (evento simulado R0) → R1 genera la OC sola
    entrar(app, "admin")
    captura(app, "02_admin_inicio.png", "Inicio (admin): tarjetas por etapa y plazo del material (R3). "
                                        "Adquisiciones ya no usa Logix.")
    app.ir("Requisiciones")
    random.seed(7)                      # para que la requisición simulada salga igual cada vez
    combo(app, "Departamento de Recursos Humanos")
    boton(app, "Simular requisición ahora")
    seleccionar(tabla_de(app), "REQ-2026-0007")
    captura(app, "03_requisicion_validada_simulada.png",
            "Llegó la requisición REQ-2026-0007 de Recursos Humanos (formato 001-03, partida 21101, validada con "
            "4 firmas). R1 generó sola la OC-2026-0007 para el proveedor fijo de papelería.")
    app.ir("Consultar folio")
    app.e_folio.insert(0, "OC-2026-0007")
    app._buscar_folio()
    captura(app, "04_oc_generada_automatica.png",
            "La OC-2026-0007 salió sola de la requisición: R1 generó el PDF con QR y lo mandó al proveedor.")

    # ---------- Jefe de Almacén: plazos, devolución y llegó bien
    entrar(app, "almacen")
    seleccionar(tabla_de(app), "OC-2026-0007")
    captura(app, "05_almacen_que_se_acepto.png",
            "Jefe de Almacén: semáforo del plazo de 7 días y, al seleccionar una orden, exactamente qué se aceptó "
            "comprar (requisición, artículos, unidades y cantidades) para compararlo con lo que llegó.")
    seleccionar(tabla_de(app), "OC-2026-0003")
    RESPUESTAS.append("Llegaron 3 cables, 1 con el conector roto")
    boton(app, "Devolución")
    captura(app, "06_almacen_devolucion_con_razon.png",
            "Devolución: el jefe escribe la razón; la compra se cancela y se le avisa al proveedor.")

    # ---------- Proveedor manda factura correcta antes de que llegue el material (R2)
    entrar(app, "admin")
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
    boton(app, "Aceptar")
    captura(app, "09_almacen_acepta_pago_automatico.png",
            "El jefe aceptó el material y la factura ya estaba validada: R4 armó el expediente y R5 pagó en el banco.")
    entrar(app, "finanzas")
    captura(app, "10_finanzas_sin_fallas.png",
            "Finanzas no tuvo que hacer nada: el pago salió solo. Su pantalla solo muestra fallas (ninguna).")

    # ---------- Error del banco: saldo insuficiente → Finanzas reintenta
    sql("UPDATE banco_cuenta SET saldo = 50 WHERE id = 1")
    entrar(app, "almacen")
    app.ir("Recepción")
    seleccionar(tabla_de(app), "OC-2026-0001")
    boton(app, "Aceptar")
    entrar(app, "admin")
    app.ir("Buzón de facturas")
    app.e_oc_buzon.insert(0, "OC-2026-0001")
    app._factura_simulada(False)
    entrar(app, "finanzas")
    captura(app, "11_finanzas_falla_saldo_insuficiente.png",
            "Falla SALDO_INSUFICIENTE: Finanzas ve por qué falló, qué decidir y el dinero detenido (no se reintenta solo).")
    entrar(app, "admin")
    app.ir("Banco emulado")
    with db.conexion() as con:
        banco_emulado.depositar(con.cursor(), 250000)
    app.ir("Banco emulado")
    captura(app, "12_banco_emulado.png", "Banco emulado: saldo, falla simulada y cada respuesta del banco.")
    entrar(app, "finanzas")
    seleccionar(tabla_de(app), "OC-2026-0001")
    boton(app, "Reintentar pago")
    captura(app, "13_finanzas_reintento_confirmado.png", "Con saldo, Finanzas reintentó y el banco confirmó el pago.")

    # ---------- Error general: 3 reintentos automáticos → Finanzas cancela
    sql("UPDATE banco_cuenta SET falla_simulada = 'ERROR_GENERAL' WHERE id = 1")
    entrar(app, "almacen")
    app.ir("Recepción")
    seleccionar(tabla_de(app), "OC-2026-0006")
    boton(app, "Aceptar")
    entrar(app, "admin")
    app.ir("Buzón de facturas")
    app.e_oc_buzon.insert(0, "OC-2026-0006")
    app._factura_simulada(False)
    entrar(app, "admin")
    app.ir("Robots y avisos")
    for _ in range(2):
        boton(app, "Ejecutar todos los robots ahora")      # 2 vueltas = intentos 2 y 3
    entrar(app, "finanzas")
    captura(app, "14_finanzas_error_general_3_intentos.png",
            "ERROR_GENERAL: el robot reintentó solo 3 veces; después pasó a Finanzas.")
    seleccionar(tabla_de(app), "OC-2026-0006")
    RESPUESTAS.append("El banco no responde desde hace dos días; se recompra con otro trámite")
    boton(app, "Cancelar pago")
    sql("UPDATE banco_cuenta SET falla_simulada = 'NINGUNA' WHERE id = 1")
    captura(app, "15_finanzas_cancela_pago.png",
            "Finanzas canceló el pago con motivo: se le avisó al proveedor; el material se devuelve.")

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
        fh.write(f"# Evidencias · Logix 3.1 (eventos simulados, sin Adquisiciones)\n\nGeneradas el {datetime.now():%d/%m/%Y %H:%M} "
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
