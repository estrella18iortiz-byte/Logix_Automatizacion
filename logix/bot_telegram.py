"""Robot R7 · Bot de Telegram de Logix.

Lo que se le puede escribir al bot:
  /start                      → instrucciones
  /vincular 123456            → liga este chat con su usuario o proveedor (código que muestra Logix)
  OC-2026-0001 (o PAG-...)    → responde en qué etapa va el trámite
  un archivo .xml             → (proveedores) envía su factura; el pie del archivo debe traer el folio de la OC
                                 y el robot R2 la valida en ese momento

Privacidad: solo responde a chats vinculados, y un proveedor solo puede consultar SUS órdenes.
"""
import re

from . import consultas, db
from .robot_facturas import PATRON_OC, procesar_factura

PATRON_FOLIO = re.compile(r"(OC|PAG)-\d{4}-\d{4}", re.IGNORECASE)

AYUDA = ("Hola, soy el asistente de Logix 🤖 (datos simulados).\n\n"
         "• Para vincular tu cuenta: /vincular y tu código de 6 dígitos (lo ves en Logix).\n"
         "• Para consultar un trámite: escribe su folio, por ejemplo OC-2026-0001 o PAG-2026-0001.\n"
         "• Proveedores: envíen el XML de su factura con el folio de la OC en el pie del archivo.")


def _quien(cur, chat_id: int) -> dict | None:
    cur.execute("SELECT id, nombre, rol FROM usuarios WHERE telegram_chat_id = ?", chat_id)
    f = cur.fetchone()
    if f:
        return {"tipo": "USUARIO", "id": f[0], "nombre": f[1], "rol": f[2]}
    cur.execute("SELECT id, razon_social, correo FROM proveedores WHERE telegram_chat_id = ?", chat_id)
    f = cur.fetchone()
    if f:
        return {"tipo": "PROVEEDOR", "id": f[0], "nombre": f[1], "correo": f[2]}
    return None


def vincular(cur, chat_id: int, codigo: str) -> str:
    codigo = codigo.strip()
    for tabla, campo in (("usuarios", "nombre"), ("proveedores", "razon_social")):
        cur.execute(f"UPDATE {tabla} SET telegram_chat_id = ?, codigo_telegram = NULL "
                    f"OUTPUT INSERTED.id, INSERTED.{campo} WHERE codigo_telegram = ?", chat_id, codigo)
        f = cur.fetchone()
        if f:
            db.bitacora(cur, "ROBOT-R7", "USUARIO" if tabla == "usuarios" else "PROVEEDOR", f[0],
                        "VINCULA_TELEGRAM")
            return f"✅ Listo, {f[1]}. A partir de ahora recibirás aquí los avisos de Logix."
    return "❌ Ese código no es válido o ya se usó. Revisa el código que te muestra Logix."


def consultar(cur, quien: dict, folio: str) -> str:
    s = consultas.seguimiento(cur, folio)
    if not s:
        return f"No encontré el folio {folio.upper()}."
    if quien["tipo"] == "PROVEEDOR":
        cur.execute("SELECT proveedor_id FROM ordenes_compra WHERE folio = ?", s["folio"])
        f = cur.fetchone()
        if not f or f[0] != quien["id"]:
            return "Ese folio no corresponde a una orden de tu empresa."
    etapas = consultas.ETAPAS
    barra = " → ".join(("✅ " if s["etapa"] is not None and i < s["etapa"] else "🔵 " if i == s["etapa"] else "⚪ ")
                       + e for i, e in enumerate(etapas))
    ultimo = s["eventos"][-1] if s["eventos"] else None
    texto = f"📄 {s['folio']} · ${s['total']:,.2f}\nEstatus: {s['estatus']}\n\n{barra}"
    if ultimo:
        texto += f"\n\nÚltimo movimiento: {ultimo['accion'].replace('_', ' ').lower()} ({ultimo['fecha']:%d/%m %H:%M})"
    if s["etapa"] is None:
        texto += f"\n❌ Compra cancelada: {s['motivo_cancelacion'] or 'sin motivo'}"
    return texto


def atender(cur, mensaje: dict, api) -> str:
    """Decide la respuesta a UN mensaje de Telegram. `api` solo se usa para descargar archivos."""
    chat_id = mensaje["chat"]["id"]
    texto = (mensaje.get("text") or mensaje.get("caption") or "").strip()

    if texto.lower().startswith("/vincular"):
        partes = texto.split()
        return vincular(cur, chat_id, partes[1]) if len(partes) > 1 else "Escribe: /vincular 123456"

    quien = _quien(cur, chat_id)
    if quien is None:
        return AYUDA + "\n\n🔒 Primero vincula tu cuenta con /vincular y tu código."

    doc = mensaje.get("document")
    if doc:
        if quien["tipo"] != "PROVEEDOR":
            return "Solo los proveedores envían facturas por este medio."
        if not doc.get("file_name", "").lower().endswith(".xml"):
            return "Envía el archivo XML de tu factura (CFDI), no el PDF."
        m = PATRON_OC.search(texto) or PATRON_OC.search(doc.get("file_name", ""))
        if not m:
            return "Escribe el folio de la OC (por ejemplo OC-2026-0001) en el pie del archivo y envíalo de nuevo."
        contenido = api.descargar(doc["file_id"])
        resultado, codigos = procesar_factura(cur, contenido, doc["file_name"], m.group(0), quien["correo"])
        if resultado == "VALIDA":
            return f"✅ Factura validada para la {m.group(0).upper()}. En un momento te llega el siguiente paso."
        if {"OC_INEXISTENTE", "OC_NO_ESPERA_FACTURA", "CFDI_INVALIDO"} & set(codigos):
            return f"❌ Archivo no aceptado ({', '.join(codigos)}). En un momento te llega el detalle."
        return (f"❌ Factura no válida ({', '.join(codigos)}): la compra {m.group(0).upper()} se canceló. "
                "En un momento te llega el detalle.")

    m = PATRON_FOLIO.search(texto)
    if m:
        return consultar(cur, quien, m.group(0))
    return f"Hola, {quien['nombre']}.\n\n" + AYUDA


def revisar(api, espera: int = 0) -> int:
    """Una vuelta del bot: lee los mensajes nuevos y contesta cada uno. Regresa cuántos atendió."""
    with db.conexion() as con:
        cur = con.cursor()
        cur.execute("SELECT valor FROM parametros WHERE clave = 'TELEGRAM_OFFSET'")
        f = cur.fetchone()
        offset = int(f[0]) if f else 0
        if not f:
            cur.execute("INSERT INTO parametros VALUES ('TELEGRAM_OFFSET', '0', 'Último mensaje leído del bot')")
    actualizaciones = api.actualizaciones(offset, espera)
    for upd in actualizaciones:
        mensaje = upd.get("message")
        if mensaje:
            try:
                with db.conexion() as con:
                    respuesta = atender(con.cursor(), mensaje, api)
            except Exception as e:  # noqa: BLE001
                respuesta = f"Ocurrió un error al procesar tu mensaje ({type(e).__name__})."
            api.enviar(mensaje["chat"]["id"], respuesta)
        with db.conexion() as con:
            con.cursor().execute("UPDATE parametros SET valor = ? WHERE clave = 'TELEGRAM_OFFSET'",
                                 str(upd["update_id"] + 1))
    return len(actualizaciones)
