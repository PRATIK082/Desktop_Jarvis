import pytest

from jarvis.privacy.redaction import Redactor


@pytest.mark.parametrize(
    "text,expected_category",
    [
        ("contact me at alice@example.com", "email"),
        ("call 555-123-4567", "phone"),
        ("ssn 123-45-6789", "ssn"),
        ("card 4111 1111 1111 1111", "credit_card"),
        ("ip 10.0.0.1", "ipv4"),
        ("token sk_abcdefghijklmnopqrstuvwxyz", "api_key"),
        ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123def", "jwt"),
    ],
)
def test_redacts_pii(text, expected_category):
    redactor = Redactor()
    out, report = redactor.redact(text)
    assert "[REDACTED:" + expected_category + "]" in out
    assert report.categories.get(expected_category, 0) >= 1


def test_custom_pattern():
    redactor = Redactor(extra_patterns=[r"SECRET-\d+"])
    out, report = redactor.redact("value SECRET-42 here")
    assert "[REDACTED:custom_0]" in out
    assert report.redacted_count == 1


def test_no_pii_unchanged():
    redactor = Redactor()
    text = "hello jarvis how are you"
    out, report = redactor.redact(text)
    assert out == text
    assert report.redacted_count == 0


def test_redact_many():
    redactor = Redactor()
    res = redactor.redact_many(["a@b.com", "no pii"])
    assert len(res) == 2
    assert res[0][1].redacted_count == 1
    assert res[1][1].redacted_count == 0
