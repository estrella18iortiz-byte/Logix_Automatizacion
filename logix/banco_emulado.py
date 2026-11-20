"""BANCO EMULADO · simula al banco del Tec (NO es un banco real ni mueve dinero real).

Logix le manda una «orden de transferencia» y el banco responde, igual que lo haría
la banca electrónica. Las respuestas posibles:

  CONFIRMADO          el pago se hizo; regresa una clave de rastreo (SPEI-…)
  ERROR_GENERAL       falla momentánea del banco (se puede reintentar)
  SALDO_INSUFICIENTE  la cuenta del Tec no tiene dinero suficiente
  MONTO_INCORRECTO    el monto es cero/negativo o pasa el límite por operación
  DIVISA_INCORRECTA   solo se aceptan pagos en pesos (MXN)
  CUENTA_INVALIDA     la CLABE del proveedor no es válida (18 dígitos y dígito verificador)
  PAGO_DUPLICADO      esa OC ya se había pagado (regresa la clave del pago original)

Para la DEMOSTRACIÓN, en Logix › Banco emulado se puede forzar una falla
(columna banco_cuenta.falla_simulada) y ver cómo responde Logix a cada error.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

CODIGOS = ["ERROR_GENERAL", "SALDO_INSUFICIENTE", "MONTO_INCORRECTO", "DIVISA_INCORRECTA",
           "CUENTA_INVALIDA", "PAGO_DUPLICADO"]
MENSAJES = {
    "ERROR_GENERAL": "El banco no pudo procesar la operación en este momento.",
    "SALDO_INSUFICIENTE": "La cuenta del Tec no tiene saldo suficiente para este pago.",
    "MONTO_INCORRECTO": "El monto no es válido o supera el límite por operación.",
    "DIVISA_INCORRECTA": "El banco solo acepta transferencias en pesos mexicanos (MXN).",
    "CUENTA_INVALIDA": "La CLABE del proveedor no es válida.",
    "PAGO_DUPLICADO": "Esa referencia ya se había pagado.",
}
# El duplicado no se simula: se prueba de verdad mandando dos veces la misma OC.
FALLAS_SIMULABLES = ["NINGUNA", "ERROR_GENERAL", "SALDO_INSUFICIENTE", "MONTO_INCORRECTO", "DIVISA_INCORRECTA",
                     "CUENTA_INVALIDA"]
PESOS_CLABE = [3, 7, 1] * 6


@dataclass
class RespuestaBanco:
    codigo: str                 # CONFIRMADO o uno de CODIGOS
    mensaje: str
    clave_rastreo: str | None = None

    @property
    def confirmado(self) -> bool:
        return self.codigo in ("CONFIRMADO", "PAGO_DUPLICADO")


def digito_verificador(clabe17: str) -> str:
    """Algoritmo oficial de la CLABE: pesos 3-7-1, se suma (dígito×peso mod 10), 10 - (suma mod 10)."""
    suma = sum((int(d) * p) % 10 for d, p in zip(clabe17, PESOS_CLABE))
    return str((10 - suma % 10) % 10)


def clabe_valida(clabe: str | None) -> bool:
    clabe = (clabe or "").strip()
    return len(clabe) == 18 and clabe.isdigit() and digito_verificador(clabe[:17]) == clabe[17]


def transferir(cur, referencia: str, clabe: str, monto: Decimal, moneda: str) -> RespuestaBanco:
    """Procesa una transferencia y deja el movimiento registrado en banco_movimientos."""
    cur.execute("SELECT saldo, limite_operacion, falla_simulada FROM banco_cuenta WHERE id = 1")
    saldo, limite, falla = cur.fetchone()
    monto = Decimal(monto)

    # 1. ¿Ya se había pagado esta referencia? → no se paga dos veces.
    cur.execute("SELECT TOP 1 clave_rastreo FROM banco_movimientos WHERE referencia = ? AND resultado = 'CONFIRMADO'",
                referencia)
    previo = cur.fetchone()
    if previo:
        respuesta = RespuestaBanco("PAGO_DUPLICADO", MENSAJES["PAGO_DUPLICADO"], previo[0])
    elif falla and falla != "NINGUNA":
        respuesta = RespuestaBanco(falla, MENSAJES.get(falla, falla) + " (falla simulada para la demostración)")
    elif (moneda or "").upper() != "MXN":
        respuesta = RespuestaBanco("DIVISA_INCORRECTA", MENSAJES["DIVISA_INCORRECTA"] + f" Se recibió {moneda}.")
    elif monto <= 0 or monto > limite:
        respuesta = RespuestaBanco("MONTO_INCORRECTO",
                                   MENSAJES["MONTO_INCORRECTO"] + f" Monto ${monto:,.2f}; límite ${limite:,.2f}.")
    elif not clabe_valida(clabe):
        respuesta = RespuestaBanco("CUENTA_INVALIDA", MENSAJES["CUENTA_INVALIDA"] + f" ({clabe})")
    elif monto > saldo:
        respuesta = RespuestaBanco("SALDO_INSUFICIENTE",
                                   MENSAJES["SALDO_INSUFICIENTE"] + f" Saldo ${saldo:,.2f}; pago ${monto:,.2f}.")
    else:
        cur.execute("SELECT COUNT(*) FROM banco_movimientos")
        clave = f"SPEI-{datetime.now():%Y%m%d}-{cur.fetchone()[0] + 1:06d}"
        cur.execute("UPDATE banco_cuenta SET saldo = saldo - ? WHERE id = 1", monto)
        respuesta = RespuestaBanco("CONFIRMADO", "Transferencia realizada.", clave)

    if respuesta.codigo != "PAGO_DUPLICADO":      # el duplicado no genera un movimiento nuevo
        cur.execute("INSERT INTO banco_movimientos (referencia, clabe_destino, monto, moneda, resultado, clave_rastreo) "
                    "VALUES (?, ?, ?, ?, ?, ?)", referencia, (clabe or "")[:18], monto, (moneda or "")[:3],
                    respuesta.codigo, respuesta.clave_rastreo)
    return respuesta


# ---------------------------------------------------------------- para la pantalla «Banco emulado»
def estado(cur) -> dict:
    cur.execute("SELECT titular, saldo, limite_operacion, falla_simulada FROM banco_cuenta WHERE id = 1")
    titular, saldo, limite, falla = cur.fetchone()
    cur.execute("SELECT TOP 100 fecha, referencia, clabe_destino, monto, moneda, resultado, clave_rastreo "
                "FROM banco_movimientos ORDER BY id DESC")
    cols = [c[0] for c in cur.description]
    movs = [dict(zip(cols, f)) for f in cur.fetchall()]
    return {"titular": titular, "saldo": saldo, "limite": limite, "falla": falla, "movimientos": movs}


def simular_falla(cur, codigo: str):
    if codigo not in FALLAS_SIMULABLES:
        raise ValueError(codigo)
    cur.execute("UPDATE banco_cuenta SET falla_simulada = ? WHERE id = 1", codigo)


def depositar(cur, monto: Decimal):
    cur.execute("UPDATE banco_cuenta SET saldo = saldo + ? WHERE id = 1", Decimal(monto))
