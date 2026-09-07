from datetime import timezone

from sqlalchemy import TIMESTAMP, Text
from sqlalchemy.types import TypeDecorator

from backend.security.encryption import decrypt_text, encrypt_text


class UTCDateTime(TypeDecorator):
    """UTC instants; legacy naive values are interpreted as UTC.

    PostgreSQL stores timestamptz. SQLite stores UTC without an offset and this
    adapter restores the offset on read so API serialization stays unambiguous.
    """
    impl = TIMESTAMP(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class EncryptedText(TypeDecorator):
    """Store text as authenticated ciphertext while exposing plaintext to Python."""

    impl = Text
    cache_ok = True

    def __init__(self, context: str):
        super().__init__()
        self.context = context

    def process_bind_param(self, value, dialect):
        return encrypt_text(value, context=self.context)

    def process_result_value(self, value, dialect):
        return decrypt_text(value, context=self.context)
