"""Robot R6 · Envía los avisos de la cola por correo y por Telegram.

- Reintenta hasta 3 veces; después marca el aviso como FALLIDA (RNF-09).
- MODO_SIMULADO=1: no envía nada, solo marca SIMULADA (para probar sin internet).
- Lista blanca de demostración: si LOGIX_DEMO_CORREO tiene valor, TODOS los correos se
  redirigen ahí. En Telegram solo reciben avisos los chats que se vincularon con el bot.
"""
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from . import config, db
from .telegram import TelegramAPI

MAX_INTENTOS = 3
DEMO_CORREO = os.getenv("LOGIX_DEMO_CORREO", "")


def _correo(destino: str, asunto: str, cuerpo: str, adjunto: str | None = None):
    msg = MIMEMultipart()
    msg.attach(MIMEText(cuerpo + "\n\n— Logix · Automatización y Sistematización de Procesos (datos simulados)",
                        "plain", "utf-8"))
    if adjunto and Path(adjunto).exists():
        parte = MIMEApplication(Path(adjunto).read_bytes(), _subtype="pdf")
        parte.add_header("Content-Disposition", "attachment", filename=Path(adjunto).name)
        msg.attach(parte)
    msg["Subject"] = f"[Logix] {asunto or 'Aviso'}"
    msg["From"] = config.CORREO_USUARIO
    msg["To"] = destino
    with smtplib.SMTP_SSL(config.CORREO_SMTP, 465, timeout=20) as s:
        s.login(config.CORREO_USUARIO, config.CORREO_PASSWORD)
        s.send_message(msg)


def _telegram(chat_id: str, asunto: str | None, cuerpo: str, adjunto: str | None = None):
    api = TelegramAPI()
    api.enviar(chat_id, f"📌 {asunto}\n\n{cuerpo}" if asunto else cuerpo)
    if adjunto and Path(adjunto).exists():
        # El PDF va justo después del mensaje, como archivo descargable.
        api.enviar_documento(chat_id, adjunto, f"📄 {asunto}" if asunto else "")


def enviar_pendientes() -> dict:
    conteo = {"ENVIADA": 0, "SIMULADA": 0, "FALLIDA": 0, "REINTENTO": 0}
    with db.conexion() as con:
        cur = con.cursor()
        cur.execute("SELECT id, canal, destinatario, asunto, mensaje, intentos, adjunto FROM notificaciones "
                    "WHERE estatus = 'PENDIENTE' ORDER BY id")
        pendientes = cur.fetchall()
        for nid, canal, destino, asunto, mensaje, intentos, adjunto in pendientes:
            if config.MODO_SIMULADO:
                cur.execute("UPDATE notificaciones SET estatus = 'SIMULADA', enviada = SYSDATETIME() WHERE id = ?", nid)
                conteo["SIMULADA"] += 1
                continue
            try:
                if canal == "CORREO":
                    texto = mensaje if not DEMO_CORREO else f"(Para: {destino})\n\n{mensaje}"
                    _correo(DEMO_CORREO or destino, asunto, texto, adjunto)
                elif canal == "TELEGRAM":
                    _telegram(destino, asunto, mensaje, adjunto)
                else:
                    raise ValueError(f"Canal desconocido: {canal}")
                cur.execute("UPDATE notificaciones SET estatus = 'ENVIADA', intentos = ?, enviada = SYSDATETIME(), "
                            "error = NULL WHERE id = ?", intentos + 1, nid)
                conteo["ENVIADA"] += 1
            except Exception as e:  # noqa: BLE001 — cualquier falla cuenta como intento
                nuevo = "FALLIDA" if intentos + 1 >= MAX_INTENTOS else "PENDIENTE"
                cur.execute("UPDATE notificaciones SET estatus = ?, intentos = ?, error = ? WHERE id = ?",
                            nuevo, intentos + 1, str(e)[:500], nid)
                conteo["FALLIDA" if nuevo == "FALLIDA" else "REINTENTO"] += 1
            con.commit()
    return conteo
