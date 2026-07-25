import json
from functools import lru_cache

from cryptography.fernet import Fernet
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator


@lru_cache
def _fernet() -> Fernet:
    from app.config import get_settings

    return Fernet(get_settings().storage_encryption_key.encode())


class EncryptedJSON(TypeDecorator):
    """A JSON dict, encrypted at rest with Fernet.

    Used for `StorageCredential.secrets`: cloud access keys and OAuth tokens
    are real secrets, not incidental data, so they're encrypted transparently
    at the column level rather than stored as plaintext JSON. Lives in
    domain/shared (next to `Base`) rather than infrastructure because this
    codebase's domain classes are themselves the SQLAlchemy mapped classes
    (see `Base`'s docstring) -- a persistence-mapping helper like this one
    belongs alongside it, not behind an extra infra-only layer.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: dict | None, dialect) -> bytes | None:
        if value is None:
            return None
        return _fernet().encrypt(json.dumps(value).encode())

    def process_result_value(self, value: bytes | None, dialect) -> dict | None:
        if value is None:
            return None
        return json.loads(_fernet().decrypt(value).decode())
