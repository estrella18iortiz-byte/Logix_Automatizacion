"""Contraseñas con hash y sal (RNF-03). Nunca se guarda la contraseña en texto."""
import hashlib
import hmac
import secrets

ITERACIONES = 200_000


def generar_hash(password: str, sal: str | None = None) -> tuple[str, str]:
    sal = sal or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(sal), ITERACIONES)
    return h.hex(), sal


def verificar(password: str, hash_guardado: str, sal: str) -> bool:
    calculado, _ = generar_hash(password, sal)
    return hmac.compare_digest(calculado, hash_guardado)
