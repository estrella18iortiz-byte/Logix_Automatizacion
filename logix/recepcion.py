"""Recepción en almacén · confirmar que el material llegó.

Lo único que hace una persona aquí es lo que ningún software puede hacer:
revisar el material FÍSICO. Almacén tiene dos botones:
  - «Llegó completo»: Logix genera la entrada y la salida y, en ese mismo momento,
    el robot R3 arma el expediente y lo manda a Recursos Financieros.
  - «Reportar problema» (llegó incompleto, dañado o diferente): Logix abre una
    excepción y avisa a Adquisiciones para que lo arregle con el proveedor.
"""
from . import avisos, db, expediente
from .errores import ReglaNegocio


def por_recibir(cur) -> list[dict]:
    """Órdenes con factura ya validada: el proveedor puede entregar."""
    cur.execute("""SELECT oc.id, oc.folio, p.razon_social AS proveedor, oc.area_solicitante, oc.total, oc.fecha
                   FROM ordenes_compra oc JOIN proveedores p ON p.id = oc.proveedor_id
                   WHERE oc.estatus = 'FACTURA_VALIDADA' ORDER BY oc.fecha""")
    return db.filas(cur)


def _folio_lista(cur, oc_id: int) -> str:
    cur.execute("SELECT folio, estatus FROM ordenes_compra WHERE id = ?", oc_id)
    fila = cur.fetchone()
    if not fila:
        raise ReglaNegocio("La orden de compra no existe.")
    folio, estatus = fila
    if estatus != "FACTURA_VALIDADA":
        raise ReglaNegocio(f"La OC {folio} no está lista para recibirse (estatus {estatus}). "
                           "Primero debe validarse la factura del proveedor.")
    return folio


def confirmar_recepcion(cur, usuario: dict, oc_id: int, fds_entregada: bool = False,
                        observaciones: str = "") -> tuple[str, str]:
    """El material llegó completo: entrada y salida automáticas y expediente a Finanzas."""
    folio = _folio_lista(cur, oc_id)
    cur.execute("SELECT COUNT(*) FROM recepciones")
    n = cur.fetchone()[0] + 1
    entrada, salida = f"ENT-{n:05d}", f"SAL-{n:05d}"      # entrada y salida simultánea
    cur.execute("INSERT INTO recepciones (oc_id, almacen_id, folio_entrada, folio_salida, fds_entregada, "
                "observaciones) VALUES (?, ?, ?, ?, ?, ?)", oc_id, usuario["id"], entrada, salida,
                int(fds_entregada), (observaciones or "").strip()[:500] or None)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "RECIBE_MATERIAL", "FACTURA_VALIDADA", "RECIBIDA",
                f"{entrada}/{salida} FDS={'sí' if fds_entregada else 'no'}")
    avisos.a_rol(cur, "ADQUISICIONES", f"Material recibido · {folio}",
                 f"Almacén confirmó que llegó el material de la OC {folio} (entrada {entrada}).")
    # Robot R3: arma el expediente y lo manda a Recursos Financieros.
    expediente.armar_y_enviar(cur, oc_id)
    return entrada, salida


def reportar_problema(cur, usuario: dict, oc_id: int, detalle: str):
    """El material llegó incompleto, dañado o diferente a la OC."""
    if not detalle or len(detalle.strip()) < 5:
        raise ReglaNegocio("Describa el problema (qué falta o qué llegó mal).")
    folio = _folio_lista(cur, oc_id)
    cur.execute("INSERT INTO excepciones (oc_id, tipo, detalle) VALUES (?, 'RECEPCION_CON_PROBLEMA', ?)",
                oc_id, detalle.strip())
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "REPORTA_PROBLEMA_RECEPCION", detalle=detalle.strip())
    avisos.a_rol(cur, "ADQUISICIONES", f"Problema en la entrega · {folio}",
                 f"Almacén reportó un problema con el material de la OC {folio}: {detalle.strip()}. "
                 "Arréglelo con el proveedor; cuando llegue bien, Almacén confirmará la recepción.")
