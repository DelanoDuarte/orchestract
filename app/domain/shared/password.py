import hashlib
import hmac
import os

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32


def hash_password(raw_password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.scrypt(raw_password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${derived.hex()}"


def verify_password(raw_password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            raw_password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(derived, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False
