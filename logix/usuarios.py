"""Inicio de sesión con bloqueo tras 5 intentos fallidos (RNF-03)."""
from . import db
from .errores import ReglaNegocio
from .seguridad import verificar

MAX_INTENTOS = 5


def iniciar_sesion(cur, usuario: str, password: str) -> dict:
    cur.execute("""SELECT u.id, u.nombre, u.usuario, u.rol, u.area_id, u.hash_password, u.sal,
                          u.intentos_fallidos, u.activo, u.codigo_telegram, u.telegram_chat_id, a.nombre AS area
                   FROM usuarios u LEFT JOIN areas a ON a.id = u.area_id WHERE u.usuario = ?""", usuario.strip())
    filas = db.filas(cur)
    if not filas:
        raise ReglaNegocio("Usuario o contraseña incorrectos.")
    u = filas[0]
    if not u["activo"] or u["intentos_fallidos"] >= MAX_INTENTOS:
        raise ReglaNegocio("Usuario bloqueado. Pida al administrador que lo desbloquee.")
    if not verificar(password, u["hash_password"], u["sal"]):
        cur.execute("UPDATE usuarios SET intentos_fallidos = intentos_fallidos + 1 WHERE id = ?", u["id"])
        db.bitacora(cur, usuario, "USUARIO", u["id"], "LOGIN_FALLIDO")
        raise ReglaNegocio("Usuario o contraseña incorrectos.")
    cur.execute("UPDATE usuarios SET intentos_fallidos = 0 WHERE id = ?", u["id"])
    db.bitacora(cur, u["usuario"], "USUARIO", u["id"], "LOGIN")
    for k in ("hash_password", "sal"):
        u.pop(k)
    return u
