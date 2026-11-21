"""El robot de Logix: corre todas las automatizaciones sin que nadie lo active.

    python robot.py            # se queda trabajando
    python robot.py --una-vez  # una sola vuelta (pruebas o el Programador de tareas de Windows)

Cada minuto:
  R0  simula los eventos: cada MINUTOS_ENTRE_REQUISICIONES llega una requisición validada de un
      departamento (Recursos Humanos, limpieza, Sistemas...) y R1 genera y manda su OC al instante
  R2  revisa el buzón de facturas (correo real si hay credenciales; si no, la carpeta buzon/entrada)
  R3  vigila los plazos: material (recordatorio día 3, último aviso 5 h antes, cancelación día 7)
      y factura (cancelación a las 48 h de que llegó el material)
  R5  manda al banco los pagos programados cuya hora llegó (5–10 min después del expediente) y
      reintenta los pagos que el banco rechazó con «error general» (máximo 3 intentos)
  R6  envía los avisos de la cola (correo y Telegram)
Todo el tiempo (si hay token de Telegram):
  R7  contesta el bot: vinculación, consulta de folios y facturas XML de proveedores
(R1, R4 y R5 también trabajan en el momento: al llegar la requisición, al juntarse la factura
 válida con el material confirmado, y al mandar el pago al banco emulado.)
"""
import sys
import time
from datetime import datetime

from logix import bot_telegram, config, db, notificador, pagos, plazos, simulador
from logix.robot_facturas import revisar_buzon_carpeta, revisar_buzon_correo
from logix.telegram import TelegramAPI

INTERVALO = 60


def vuelta() -> dict:
    res = {}
    try:
        with db.conexion() as con:
            res["R0 requisiciones simuladas"] = simulador.tal_vez_generar(con.cursor())
        facturas = revisar_buzon_carpeta()
        if config.CORREO_USUARIO and config.CORREO_PASSWORD and not config.MODO_SIMULADO:
            facturas += revisar_buzon_correo()
        res["R2 facturas"] = len(facturas)
        with db.conexion() as con:
            cur = con.cursor()
            res["R3 plazos"] = plazos.revisar(cur)
            res["R5 pagos programados"] = pagos.pagar_programados(cur)
            res["R5 reintentos de pago"] = pagos.reintentar_pendientes(cur)
        if config.TELEGRAM_TOKEN:
            res["R7 mensajes del bot"] = bot_telegram.revisar(TelegramAPI())
        res["R6 avisos"] = notificador.enviar_pendientes()
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
