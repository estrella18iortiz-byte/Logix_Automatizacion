"""Revisa que esta computadora tenga todo para correr Logix y dice cómo arreglar lo que falte.

    python verificar_instalacion.py      (o doble clic en VERIFICAR.bat)
"""
import importlib.util
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
problemas = 0


def ok(texto):
    print(f"  ✔ {texto}")


def mal(texto, arreglo):
    global problemas
    problemas += 1
    print(f"  ✘ {texto}\n      → {arreglo}")


print("\n1. Python")
if sys.version_info >= (3, 10):
    ok(f"Python {sys.version.split()[0]}")
else:
    mal(f"Python {sys.version.split()[0]} es muy viejo", "Instala Python 3.12 desde python.org (marca «Add to PATH»).")

print("\n2. Librerías")
faltan = [m for m, nombre in [("pyodbc", "pyodbc"), ("customtkinter", "customtkinter"), ("dotenv", "python-dotenv"),
                              ("requests", "requests"), ("qrcode", "qrcode"), ("fpdf", "fpdf2"), ("PIL", "pillow")]
          if importlib.util.find_spec(m) is None]
if faltan:
    mal(f"Faltan: {', '.join(faltan)}", "Doble clic en INSTALAR.bat (o: pip install -r requirements.txt).")
else:
    ok("Todas instaladas")

print("\n3. Archivo .env")
env = RAIZ / ".env"
if not env.exists():
    shutil.copy(RAIZ / ".env.example", env)
    ok("No existía: se creó a partir de .env.example (modo simulado)")
else:
    ok(".env encontrado")

if "pyodbc" in faltan or "dotenv" in faltan:
    print("\nInstala las librerías y vuelve a correr este verificador.")
    sys.exit(1)

import pyodbc  # noqa: E402

from logix import config  # noqa: E402

print("\n4. SQL Server")
drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
if any(d.startswith("ODBC Driver") for d in drivers):
    ok(f"Driver: {config.SQL_DRIVER}")
else:
    mal("No hay «ODBC Driver 17/18 for SQL Server»",
        "Instálalo desde Microsoft: «Download ODBC Driver for SQL Server» (x64).")

conectado = None
for servidor in dict.fromkeys([config.SQL_SERVER, r".\SQLEXPRESS", "localhost", r"(localdb)\MSSQLLocalDB"]):
    try:
        cad = (f"DRIVER={{{config.SQL_DRIVER}}};SERVER={servidor};DATABASE=master;"
               "Trusted_Connection=yes;TrustServerCertificate=yes;")
        con = pyodbc.connect(cad, timeout=5)
        version = con.cursor().execute("SELECT SERVERPROPERTY('ProductVersion'), SERVERPROPERTY('Edition')").fetchone()
        tiene_bd = con.cursor().execute("SELECT DB_ID('logix_db')").fetchone()[0] is not None
        con.close()
        conectado = servidor
        ok(f"Conectado a «{servidor}» · versión {version[0]} · {version[1]}")
        if servidor != config.SQL_SERVER:
            mal(f".env dice «{config.SQL_SERVER}», pero la instancia que respondió es «{servidor}»",
                f"En .env cambia la línea a: LOGIX_SQL_SERVER={servidor}")
        if tiene_bd:
            ok("La base logix_db existe")
        else:
            mal("La base logix_db todavía no existe", "Doble clic en REINICIAR_DATOS.bat.")
        break
    except pyodbc.Error:
        continue
if not conectado:
    mal("No pude conectarme a ninguna instancia de SQL Server",
        "Abre «Servicios» de Windows y verifica que «SQL Server (SQLEXPRESS)» esté en ejecución, "
        "o anota el nombre de tu instancia (en SSMS, el «Server name») y ponlo en .env como LOGIX_SQL_SERVER.")

print("\n5. Fuentes y logotipo")
if (Path("C:/Windows/Fonts") / "arial.ttf").exists():
    ok("Arial disponible para los PDF")
else:
    mal("No encontré Arial", "Los PDF usarán Helvetica (sin acentos especiales).")
if (RAIZ / "recursos" / "logo_logix.png").exists():
    ok("Logotipo de Logix encontrado")
else:
    mal("Falta recursos/logo_logix.png", "Copia la carpeta recursos completa.")

print("\n6. Telegram")
if config.TELEGRAM_TOKEN:
    try:
        from logix.telegram import TelegramAPI
        bot = TelegramAPI()._llamar("getMe")
        ok(f"Bot conectado: @{bot['username']}")
    except Exception as e:  # noqa: BLE001
        mal(f"El token no funcionó ({e})", "Revisa LOGIX_TELEGRAM_TOKEN en .env (cópialo completo de @BotFather).")
else:
    print("  – Sin token (los avisos de Telegram se simulan). Ver README › «Conectar Telegram».")

print("\n7. Correo")
if config.CORREO_USUARIO and config.CORREO_PASSWORD:
    import smtplib
    try:
        with smtplib.SMTP_SSL(config.CORREO_SMTP, 465, timeout=15) as s:
            s.login(config.CORREO_USUARIO, config.CORREO_PASSWORD)
        ok(f"Inicio de sesión correcto en {config.CORREO_USUARIO}")
    except Exception as e:  # noqa: BLE001
        mal(f"No pude iniciar sesión en el correo ({e})",
            "Usa una «contraseña de aplicación» de Google (requiere verificación en 2 pasos), no tu contraseña normal.")
else:
    print("  – Sin correo configurado (los correos se simulan).")

print("\n8. Modo")
print(f"  – {'SIMULADO: no se envía nada' if config.MODO_SIMULADO else 'REAL: se envían correos y mensajes de Telegram'}"
      " (LOGIX_MODO_SIMULADO en .env)")

print("\n" + ("✅ Todo listo para usar Logix." if problemas == 0 else f"⚠️  {problemas} punto(s) por arreglar (ver →)."))
