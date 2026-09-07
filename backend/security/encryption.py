
import base64
import binascii
import os
import re
import secrets
import hashlib
import hmac

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_PREFIX = "enc"
_VERSION = "v1"
_NONCE_BYTES = 12
_KEY_BYTES = 32
_VALID_KEY_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class EncryptionConfigError(RuntimeError):
    """Encryption configuration is missing or invalid."""


class DecryptionError(ValueError):
    """An encrypted value could not be safely decrypted."""


def _decode_base64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)


def _encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _load_key() -> tuple[bytes, str]:
    encoded_key = os.getenv("DATA_ENCRYPTION_KEY")
    key_id = os.getenv("DATA_ENCRYPTION_KEY_ID")
    if not encoded_key:
        raise EncryptionConfigError("DATA_ENCRYPTION_KEY is required")
    if not key_id:
        raise EncryptionConfigError("DATA_ENCRYPTION_KEY_ID is required")
    if not _VALID_KEY_ID.fullmatch(key_id):
        raise EncryptionConfigError("DATA_ENCRYPTION_KEY_ID has an invalid format")
    try:
        key = _decode_base64(encoded_key)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise EncryptionConfigError(
            "DATA_ENCRYPTION_KEY must be valid URL-safe base64"
        ) from exc
    if len(key) != _KEY_BYTES:
        raise EncryptionConfigError(
            "DATA_ENCRYPTION_KEY must decode to exactly 32 bytes"
        )
    encryption_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"job:data-encryption:v1",
    ).derive(key)
    return encryption_key, key_id


def _load_lookup_key() -> bytes:
    encoded_key = os.getenv("DATA_ENCRYPTION_KEY")
    if not encoded_key:
        raise EncryptionConfigError("DATA_ENCRYPTION_KEY is required")
    try:
        master_key = _decode_base64(encoded_key)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise EncryptionConfigError(
            "DATA_ENCRYPTION_KEY must be valid URL-safe base64"
        ) from exc
    if len(master_key) != _KEY_BYTES:
        raise EncryptionConfigError(
            "DATA_ENCRYPTION_KEY must decode to exactly 32 bytes"
        )
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"job:blind-index:v1",
    ).derive(master_key)


def _associated_data(key_id: str, context: str) -> bytes:
    if not context:
        raise ValueError("Encryption context must not be empty")
    return f"{_PREFIX}:{_VERSION}:{key_id}:{context}".encode("utf-8")


def encrypt_text(value: str | None, *, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("encrypt_text only accepts strings or None")
    key, key_id = _load_key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(
        nonce, value.encode("utf-8"), _associated_data(key_id, context)
    )
    return ":".join(
        (_PREFIX, _VERSION, key_id, _encode_base64(nonce), _encode_base64(ciphertext))
    )


def decrypt_text(value: str | None, *, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("decrypt_text only accepts strings or None")
    key, configured_key_id = _load_key()
    try:
        prefix, version, stored_key_id, nonce_text, ciphertext_text = value.split(
            ":", maxsplit=4
        )
    except ValueError:
        raise DecryptionError("Encrypted value has an invalid format") from None
    if prefix != _PREFIX or version != _VERSION:
        raise DecryptionError("Encrypted value uses an unsupported format")
    if stored_key_id != configured_key_id:
        raise DecryptionError("The required encryption key is unavailable")
    try:
        nonce = _decode_base64(nonce_text)
        ciphertext = _decode_base64(ciphertext_text)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise DecryptionError("Encrypted value has an invalid format") from None
    if len(nonce) != _NONCE_BYTES:
        raise DecryptionError("Encrypted value has an invalid format")
    try:
        plaintext = AESGCM(key).decrypt(
            nonce, ciphertext, _associated_data(stored_key_id, context)
        )
        return plaintext.decode("utf-8")
    except (InvalidTag, UnicodeDecodeError):
        raise DecryptionError("Encrypted value could not be authenticated") from None


def blind_index(value: str | None, *, context: str) -> str | None:
    """Return a keyed, non-reversible equality lookup for a sensitive value."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("blind_index only accepts strings or None")
    if not context:
        raise ValueError("Blind-index context must not be empty")
    message = f"{context}\0{value}".encode("utf-8")
    return hmac.new(_load_lookup_key(), message, hashlib.sha256).hexdigest()
