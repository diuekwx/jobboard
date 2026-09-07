import logging
from datetime import datetime, timezone

from backend.service import classification_service
from backend.service.classification_service import EmailInput


def test_malformed_llm_output_is_not_copied_into_logs(monkeypatch, caplog):
    secret = "PRIVATE-MODEL-OUTPUT-92831"
    monkeypatch.setattr(
        classification_service,
        "_call_llm",
        lambda content, max_tokens: {"unexpected": secret},
    )
    item = EmailInput(
        "message-id",
        "private-sender@example.com",
        "PRIVATE-SUBJECT-92831",
        "PRIVATE-BODY-92831",
        datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    with caplog.at_level(logging.WARNING):
        assert classification_service._classify_chunk_llm([item]) == {}

    assert secret not in caplog.text
    assert item.subject not in caplog.text
    assert item.body not in caplog.text
