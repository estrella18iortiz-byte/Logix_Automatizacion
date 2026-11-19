"""Poner avisos en la cola. El robot R5 (notificador.py) es quien los envía.

Canales: CORREO (siempre) y TELEGRAM (solo si la persona ya se vinculó con el bot de Logix).
"""


def encolar(cur, canal: str, destinatario: str | None, asunto: str | None, mensaje: str):
    if destinatario:
        cur.execute("INSERT INTO notificaciones (canal, destinatario, asunto, mensaje) VALUES (?, ?, ?, ?)",
                    canal, str(destinatario), asunto, mensaje)


def a_usuario(cur, usuario_id: int, asunto: str, mensaje: str):
    cur.execute("SELECT correo, telegram_chat_id, usuario FROM usuarios WHERE id = ?", usuario_id)
    fila = cur.fetchone()
    if fila:
        correo, chat, usuario = fila
        encolar(cur, "CORREO", correo or f"{usuario}@logix.demo", asunto, mensaje)
        if chat:
            encolar(cur, "TELEGRAM", chat, asunto, mensaje)


def a_rol(cur, rol: str, asunto: str, mensaje: str, area_id: int | None = None):
    sql = "SELECT id FROM usuarios WHERE rol = ? AND activo = 1"
    params = [rol]
    if area_id is not None:
        sql += " AND area_id = ?"
        params.append(area_id)
    cur.execute(sql, *params)
    for (uid,) in cur.fetchall():
        a_usuario(cur, uid, asunto, mensaje)


def a_proveedor(cur, proveedor_id: int, asunto: str, mensaje: str, correo_extra: str | None = None):
    cur.execute("SELECT correo, telegram_chat_id FROM proveedores WHERE id = ?", proveedor_id)
    correo, chat = cur.fetchone()
    encolar(cur, "CORREO", correo_extra or correo, asunto, mensaje)
    if chat:
        encolar(cur, "TELEGRAM", chat, asunto, mensaje)
