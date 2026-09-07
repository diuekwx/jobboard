import base64
import os

import pytest

from backend.security.encryption import (
    DecryptionError,
    EncryptionConfigError,
    blind_index,
    decrypt_text,
    encrypt_text,
)

TEST_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()
CONTEXT = "integration_tokens.access_token:test-user"


@pytest.fixture(autouse=True)
def encryption_config(monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_ID", "test-v1")


def test_round_trip():
    encrypted = encrypt_text("secret", context=CONTEXT)
    assert encrypted != "secret"
    assert decrypt_text(encrypted, context=CONTEXT) == "secret"


def test_same_text_has_different_ciphertext():
    assert encrypt_text("secret", context=CONTEXT) != encrypt_text("secret", context=CONTEXT)


def test_tampering_fails():
    encrypted = encrypt_text("secret", context=CONTEXT)
    parts = encrypted.split(":")
    parts[-1] = ("A" if parts[-1][0] != "A" else "B") + parts[-1][1:]
    with pytest.raises(DecryptionError):
        decrypt_text(":".join(parts), context=CONTEXT)


def test_wrong_context_fails():
    encrypted = encrypt_text("secret", context=CONTEXT)
    with pytest.raises(DecryptionError):
        decrypt_text(encrypted, context="integration_tokens.access_token:other-user")


def test_none_remains_none():
    assert encrypt_text(None, context=CONTEXT) is None
    assert decrypt_text(None, context=CONTEXT) is None


def test_missing_key_fails(monkeypatch):
    monkeypatch.delenv("DATA_ENCRYPTION_KEY")
    with pytest.raises(EncryptionConfigError, match="required"):
        encrypt_text("secret", context=CONTEXT)


def test_wrong_key_size_fails(monkeypatch):
    monkeypatch.setenv(
        "DATA_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"short").decode()
    )
    with pytest.raises(EncryptionConfigError, match="32 bytes"):
        encrypt_text("secret", context=CONTEXT)


def test_error_does_not_reveal_secret():
    encrypted = encrypt_text("VERY-PRIVATE-VALUE", context=CONTEXT)
    with pytest.raises(DecryptionError) as error:
        decrypt_text(encrypted, context="wrong")
    assert "VERY-PRIVATE-VALUE" not in str(error.value)
    assert encrypted not in str(error.value)


def test_blind_index_is_stable_but_bound_to_its_context():
    first = blind_index("gmail-message-123", context="messages.id")
    second = blind_index("gmail-message-123", context="messages.id")
    other_field = blind_index("gmail-message-123", context="events.source_id")

    assert first == second
    assert first != other_field
    assert "gmail-message-123" not in first


def test_backed_up_key_recovers_data_after_wrong_key_fails(monkeypatch):
    encrypted = encrypt_text("recoverable", context=CONTEXT)
    backed_up_key = os.environ["DATA_ENCRYPTION_KEY"]

    replacement = base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode()
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", replacement)
    with pytest.raises(DecryptionError):
        decrypt_text(encrypted, context=CONTEXT)

    monkeypatch.setenv("DATA_ENCRYPTION_KEY", backed_up_key)
    assert decrypt_text(encrypted, context=CONTEXT) == "recoverable"
