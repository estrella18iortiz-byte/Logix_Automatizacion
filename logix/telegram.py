"""Conexión mínima con la API oficial de bots de Telegram (https://core.telegram.org/bots/api)."""
import requests

from . import config

URL = "https://api.telegram.org"


class TelegramAPI:
    def __init__(self, token: str | None = None):
        self.token = token or config.TELEGRAM_TOKEN

    def _llamar(self, metodo: str, params: dict | None = None, espera_http: int = 30):
        r = requests.post(f"{URL}/bot{self.token}/{metodo}", json=params or {}, timeout=espera_http)
        datos = r.json()
        if not datos.get("ok"):
            raise RuntimeError(f"Telegram {metodo}: {datos.get('description', r.text[:200])}")
        return datos["result"]

    def enviar(self, chat_id, texto: str):
        return self._llamar("sendMessage", {"chat_id": int(chat_id), "text": texto[:4000]})

    def actualizaciones(self, offset: int, espera: int = 0) -> list[dict]:
        """Mensajes nuevos para el bot. Sin servidor público: Logix pregunta («long polling»)."""
        return self._llamar("getUpdates", {"offset": offset, "timeout": espera}, espera_http=espera + 10)

    def descargar(self, file_id: str) -> bytes:
        info = self._llamar("getFile", {"file_id": file_id})
        r = requests.get(f"{URL}/file/bot{self.token}/{info['file_path']}", timeout=30)
        r.raise_for_status()
        return r.content
