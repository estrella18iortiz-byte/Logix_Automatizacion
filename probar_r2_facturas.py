"""Prueba de integración del robot R2 (validación de facturas) con la base real (datos simulados).

    python generar_datos.py      (deja la base limpia)
    python probar_r2_facturas.py

Mete al buzón simulado las 10 facturas de datos_prueba/facturas en orden, corre el robot
y compara cada resultado con el esperado de casos.csv. Además revisa la regla nueva:
si la factura no es válida, la compra debe quedar CANCELADA (columna cancela_compra).
"""
import csv
import shutil
import time
from pathlib import Path

from logix import config, db
from logix.robot_facturas import revisar_buzon_carpeta

RAIZ = Path(__file__).resolve().parent
CASOS = RAIZ / "datos_prueba" / "facturas"
ENTRADA = config.RAIZ / "buzon" / "entrada"


def estatus_oc(folio: str) -> str | None:
    with db.conexion() as con:
        cur = con.cursor()
        cur.execute("SELECT estatus FROM ordenes_compra WHERE folio = ?", folio)
        fila = cur.fetchone()
        return fila[0] if fila else None


def main():
    ENTRADA.mkdir(parents=True, exist_ok=True)
    aprobados = 0
    with open(CASOS / "casos.csv", encoding="utf-8") as fh:
        casos = list(csv.DictReader(fh))

    print(f"{'#':>2}  {'Archivo':28} {'OC':14} {'Esperado':10} {'Obtenido':10} {'OC después':12} {'Tiempo':>7}  Reglas")
    for c in casos:
        # Una factura a la vez, en orden (como llegarían los correos).
        shutil.copy(CASOS / c["archivo"], ENTRADA / f"{c['folio_oc']} {c['archivo']}")
        antes = estatus_oc(c["folio_oc"])
        t0 = time.perf_counter()
        (_, obtenido, codigos), = revisar_buzon_carpeta(ENTRADA)
        seg = time.perf_counter() - t0
        despues = estatus_oc(c["folio_oc"])
        # Si se espera cancelación, la OC debe terminar CANCELADA; si no, no debe cambiar a CANCELADA.
        cancelada_ok = (despues == "CANCELADA") if c["cancela_compra"] == "SI" else (despues == antes)
        ok = obtenido == c["resultado_esperado"] and cancelada_ok
        aprobados += ok
        print(f"{c['orden']:>2}  {c['archivo']:28} {c['folio_oc']:14} {c['resultado_esperado']:10} "
              f"{obtenido:10} {str(despues):12} {seg:6.2f}s  {'✔' if ok else '✘'} {', '.join(codigos) or '—'}")

    with db.conexion() as con:
        cur = con.cursor()
        cur.execute("SELECT folio, estatus FROM ordenes_compra ORDER BY folio")
        estatus = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM notificaciones")
        n_not = cur.fetchone()[0]

    print(f"\nResultado: {aprobados} de {len(casos)} casos como se esperaba.")
    print("Estatus de las OC:", ", ".join(f"{f}={e}" for f, e in estatus))
    print(f"Avisos en cola (correo y Telegram): {n_not}")


if __name__ == "__main__":
    main()
