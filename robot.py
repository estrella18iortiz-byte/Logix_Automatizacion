"""El robot de Logix: corre todas las automatizaciones sin que nadie lo active.

    python robot.py            # se queda trabajando
    python robot.py --una-vez  # una sola vuelta (pruebas o el Programador de tareas de Windows)

Cada minuto:
  R2  revisa el buzón de facturas (correo real si hay credenciales; si no, la carpeta buzon/entrada)
  R5  concilia los archivos del banco (carpeta banco/entrada)
  R4  recuerda a Finanzas o a Adquisiciones los expedientes que llevan mucho sin respuesta
  R6  revisa el cierre de ejercicio (semáforo contra la fecha límite de diciembre)
  R7  envía los avisos de la cola (correo y Telegram)
Todo el tiempo (si hay token de Telegram):
  R8  contesta el bot: vinculación, consulta de folios y facturas XML de proveedores
(R1 y R3 no esperan al reloj: trabajan en el momento en que Adquisiciones registra
 una compra y en el momento en que Almacén confirma el material.)
"""
import sys
import time
from datetime import datetime

from logix import bot_telegram, config, db, notificador, pagos, vigilante
from logix.robot_facturas import revisar_buzon_carpeta, revisar_buzon_correo
from logix.telegram import TelegramAPI

INTERVALO = 60


def vuelta() -> dict:
    res = {}
    try:
        facturas = revisar_buzon_carpeta()
        if config.CORREO_USUARIO and config.CORREO_PASSWORD and not config.MODO_SIMULADO:
            facturas += revisar_buzon_correo()
        res["R2 facturas"] = len(facturas)
        res["R5 conciliación"] = len(pagos.conciliar_carpeta())
        with db.conexion() as con:
            cur = con.cursor()
            res["R4 recordatorios"] = pagos.recordar_pendientes(cur)
            res["R6 alertas de cierre"] = vigilante.revisar(cur)
        if config.TELEGRAM_TOKEN:
            res["R8 mensajes del bot"] = bot_telegram.revisar(TelegramAPI())
        res["R7 avisos"] = notificador.enviar_pendientes()
    except Exception as e:  # noqa: BLE001 — el robot no se cae; registra y sigue
        res["error"] = str(e)
    return res


def main():
    una_vez = "--una-vez" in sys.argv
    print(f"Robot Logix iniciado ({'modo simulado' if config.MODO_SIMULADO else 'envíos reales'}; "
          f"Telegram {'activo' if config.TELEGRAM_TOKEN else 'sin token'}).")
    api = TelegramAPI() if config.TELEGRAM_TOKEN else None
    ultima = 0.0
    while True:
        if time.time() - ultima >= INTERVALO or una_vez:
            print(f"[{datetime.now():%H:%M:%S}]", vuelta())
            ultima = time.time()
        if una_vez:
            break
        if api:
            try:
                # Espera hasta 20 s a que alguien le escriba al bot: responde casi al instante.
                if bot_telegram.revisar(api, espera=20):
                    notificador.enviar_pendientes()
            except Exception as e:  # noqa: BLE001
                print("Bot:", e)
                time.sleep(5)
        else:
            time.sleep(5)


if __name__ == "__main__":
    main()
