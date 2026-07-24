"""Basic email-format validation. Blank emails are not counted invalid."""
from __future__ import annotations
import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_email_format(records: list[dict]) -> dict:
    total = len(records)
    invalid_count = 0
    for rec in records:
        email = (rec.get("email") or "").strip()
        if not email:
            continue
        if not _EMAIL_RE.match(email):
            invalid_count += 1
    return {
        "invalid_count": invalid_count,
        "invalid_rate": (invalid_count / total) if total else 0.0,
    }
