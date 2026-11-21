"""Genera la factura XML (CFDI simulado) que mandaría el proveedor de una orden de compra.

    python generar_factura_prueba.py OC-2026-0012      (o doble clic en GENERAR_FACTURA.bat)

Sirve para la demostración y el video: el proveedor manda este archivo por Telegram con el
folio en el pie y el robot R2 lo valida. Crea dos archivos en datos_prueba/facturas_telegram/:
  · <folio>_factura_correcta.xml     → se valida y la compra sigue al pago
  · <folio>_factura_importe_mal.xml  → se rechaza (importe distinto) y la compra se cancela
Solo datos simulados.
"""
import sys
from decimal import Decimal
from pathlib import Path

from logix import compras, db
from logix.cfdi_simulado import generar_xml

SALIDA = Path(__file__).resolve().parent / "datos_prueba" / "facturas_telegram"


def generar(folio: str) -> list[Path]:
    folio = folio.strip().upper()
    with db.conexion() as con:
        cur = con.cursor()
        cur.execute("""SELECT oc.id, oc.total, p.rfc, p.razon_social FROM ordenes_compra oc
                       JOIN proveedores p ON p.id = oc.proveedor_id WHERE oc.folio = ?""", folio)
        fila = cur.fetchone()
        if not fila:
            raise SystemExit(f"No existe la orden {folio}.")
        oc_id, total, rfc, razon = fila
        lineas = [(l["descripcion"], l["cantidad"], l["precio_unitario"]) for l in compras.lineas_oc(cur, oc_id)]
        rfc_tec = db.parametro(cur, "RFC_INSTITUCION")
    SALIDA.mkdir(parents=True, exist_ok=True)
    n = folio[-4:]
    correcta = SALIDA / f"{folio}_factura_correcta.xml"
    mala = SALIDA / f"{folio}_factura_importe_mal.xml"
    correcta.write_bytes(generar_xml(rfc, razon, rfc_tec, lineas, folio=f"F{n}"))
    mala.write_bytes(generar_xml(rfc, razon, rfc_tec, lineas, folio=f"E{n}", total_forzado=total + Decimal("250")))
    print(f"{folio} · {razon} · total ${total:,.2f}")
    print(f"  ✔ {correcta.name}  (se valida)")
    print(f"  ✘ {mala.name}  (se rechaza y cancela la compra)")
    print(f"Carpeta: {SALIDA}")
    return [correcta, mala]


if __name__ == "__main__":
    generar(sys.argv[1] if len(sys.argv) > 1 else input("Folio de la orden (ej. OC-2026-0012): "))
