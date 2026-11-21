"""Cancelación de una compra · un solo lugar para todas las formas de cancelar.

En el diagrama del 19-nov-2026 una compra se cancela por cinco motivos:

  DEVOLUCION_ALMACEN  el Jefe de Almacén presiona «Devolución» (no llegó o llegó en mal estado)
  MATERIAL_NO_LLEGO   pasaron 7 días y el material no llegó (robot R3)
  FACTURA_INVALIDA    la factura no pasó la validación (robot R2)
  FACTURA_NO_LLEGO    pasaron 48 h desde que llegó el material y no hay factura (robot R3)
  PAGO_CANCELADO      Finanzas cancela después de un error del banco

En todos los casos pasa lo mismo:
  1. La OC queda CANCELADA con su motivo (y queda en la bitácora).
  2. Si el material ya estaba en almacén, se marca «por devolver» al proveedor.
  3. Se avisa al PROVEEDOR por correo y Telegram con la razón
     (y a Almacén si hay material que regresar, y a Finanzas si el expediente ya le había llegado).
     Adquisiciones ya no participa: la compra salió de una requisición validada (evento simulado).
"""
from . import avisos, db
from .errores import ReglaNegocio

TITULOS = {
    "DEVOLUCION_ALMACEN": "Devolución de material",
    "MATERIAL_NO_LLEGO": "El material no llegó en 7 días",
    "FACTURA_INVALIDA": "Factura no válida",
    "FACTURA_NO_LLEGO": "La factura no llegó en 48 horas",
    "PAGO_CANCELADO": "Pago cancelado por Recursos Financieros",
}
# Estatus desde los que todavía se puede cancelar (PAGADA y CANCELADA ya terminaron).
CANCELABLES = {"ESPERANDO_MATERIAL", "MATERIAL_RECIBIDO", "EN_FINANZAS", "PAGO_CON_ERROR"}


def cancelar(cur, oc_id: int, tipo: str, motivo: str, actor: str) -> str:
    """Cancela la OC y avisa a quien corresponde. Regresa el folio."""
    if tipo not in TITULOS:
        raise ValueError(f"Tipo de cancelación desconocido: {tipo}")
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise ReglaNegocio("Escribe la razón de la cancelación o devolución (se le manda al proveedor).")
    cur.execute("SELECT folio, estatus, proveedor_id, total FROM ordenes_compra WHERE id = ?", oc_id)
    fila = cur.fetchone()
    if not fila:
        raise ReglaNegocio("La orden de compra no existe.")
    folio, estatus, proveedor_id, total = fila
    if estatus not in CANCELABLES:
        raise ReglaNegocio(f"La OC {folio} ya terminó (estatus {estatus}); no se puede cancelar.")

    # ¿Hay material en el almacén que deba regresarse al proveedor?
    cur.execute("SELECT COUNT(*) FROM recepciones WHERE oc_id = ?", oc_id)
    hay_material = cur.fetchone()[0] > 0

    cur.execute("""UPDATE ordenes_compra SET estatus = 'CANCELADA', tipo_cancelacion = ?, motivo_cancelacion = ?,
                          fecha_cancelacion = SYSDATETIME(), material_por_devolver = ? WHERE id = ?""",
                tipo, motivo[:500], int(hay_material), oc_id)
    cur.execute("UPDATE pagos SET estatus = 'CANCELADO' WHERE oc_id = ? AND estatus <> 'CONFIRMADO'", oc_id)
    db.bitacora(cur, actor, "OC", oc_id, "CANCELA", estatus, "CANCELADA", f"{tipo}: {motivo}")

    titulo = TITULOS[tipo]
    if hay_material:
        devolucion = " El material que entregó se le devolverá; coordine la recolección con el Almacén."
    elif tipo == "DEVOLUCION_ALMACEN":
        devolucion = " Si el material llegó en mal estado, coordine su recolección con el Almacén."
    else:
        devolucion = " Si aún no envía el material, ya no lo envíe."
    avisos.a_proveedor(cur, proveedor_id, f"Compra cancelada · {folio}",
                       f"La orden de compra {folio} por ${total:,.2f} fue CANCELADA.\n"
                       f"Causa: {titulo}.\nRazón: {motivo}.{devolucion}")
    if hay_material and tipo != "DEVOLUCION_ALMACEN":
        avisos.a_rol(cur, "ALMACEN", f"Material por devolver · {folio}",
                     f"La OC {folio} se canceló ({titulo}). Regrese el material al proveedor y márquelo "
                     "como devuelto en Logix › Recepción.")
    if estatus in ("EN_FINANZAS", "PAGO_CON_ERROR") and tipo != "PAGO_CANCELADO":
        avisos.a_rol(cur, "FINANZAS", f"Compra cancelada · {folio}", f"La OC {folio} se canceló: {motivo}.")
    return folio


def marcar_material_devuelto(cur, usuario: dict, oc_id: int):
    """El Jefe de Almacén confirma que el material ya se le regresó al proveedor."""
    cur.execute("SELECT folio, material_por_devolver, material_devuelto FROM ordenes_compra WHERE id = ?", oc_id)
    fila = cur.fetchone()
    if not fila or not fila[1] or fila[2]:
        raise ReglaNegocio("Esa orden no tiene material pendiente de devolver.")
    cur.execute("UPDATE ordenes_compra SET material_devuelto = 1 WHERE id = ?", oc_id)
    db.bitacora(cur, usuario["usuario"], "OC", oc_id, "MATERIAL_DEVUELTO", detalle="Material regresado al proveedor")
