"""Configuración leída del archivo .env (nunca se sube a GitHub)."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

SQL_SERVER = os.getenv("LOGIX_SQL_SERVER", r".\SQLEXPRESS")
SQL_DB = os.getenv("LOGIX_SQL_DB", "logix_db")


def _driver_disponible() -> str:
    """Usa el driver ODBC más nuevo que tenga la máquina (18, 17...) si no se indica en .env."""
    try:
        import pyodbc
        candidatos = sorted(d for d in pyodbc.drivers() if d.startswith("ODBC Driver") and "SQL Server" in d)
        if candidatos:
            return max(candidatos, key=lambda d: int("".join(ch for ch in d if ch.isdigit()) or 0))
    except Exception:  # noqa: BLE001
        pass
    return "ODBC Driver 18 for SQL Server"


SQL_DRIVER = os.getenv("LOGIX_SQL_DRIVER") or _driver_disponible()

# Carpeta donde se guardan XML, PDF y expedientes (la BD solo guarda la ruta).
DOCUMENTOS = Path(os.getenv("LOGIX_DOCUMENTOS", RAIZ / "documentos"))

# Correo (buzón de facturas y avisos). Gmail: usar "contraseña de aplicación".
CORREO_USUARIO = os.getenv("LOGIX_CORREO_USUARIO", "")
CORREO_PASSWORD = os.getenv("LOGIX_CORREO_PASSWORD", "")
CORREO_IMAP = os.getenv("LOGIX_CORREO_IMAP", "imap.gmail.com")
CORREO_SMTP = os.getenv("LOGIX_CORREO_SMTP", "smtp.gmail.com")

# Bot de Telegram (token que da @BotFather).
TELEGRAM_TOKEN = os.getenv("LOGIX_TELEGRAM_TOKEN", "")

# Si es 1, los avisos no se envían: solo se registran (para pruebas sin internet).
MODO_SIMULADO = os.getenv("LOGIX_MODO_SIMULADO", "1") == "1"


# Usuario y contraseña de SQL Server: solo para las pruebas en GitHub (Linux no tiene sesión de Windows).
# En la PC se dejan vacíos y se usa la autenticación de Windows.
SQL_USUARIO = os.getenv("LOGIX_SQL_USER", "")
SQL_PASSWORD = os.getenv("LOGIX_SQL_PASSWORD", "")


def cadena_conexion(base: str | None = None) -> str:
    acceso = (f"UID={SQL_USUARIO};PWD={SQL_PASSWORD};" if SQL_USUARIO else "Trusted_Connection=yes;")
    return (
        f"DRIVER={{{SQL_DRIVER}}};SERVER={SQL_SERVER};DATABASE={base or SQL_DB};"
        f"{acceso}TrustServerCertificate=yes;"
    )
