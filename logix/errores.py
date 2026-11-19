class ReglaNegocio(Exception):
    """Una regla del instructivo o del sistema impide la operación.
    El mensaje se le muestra tal cual a la persona (debe explicar qué hacer)."""
