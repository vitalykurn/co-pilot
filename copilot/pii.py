"""Mask obvious personal data before the ticket text reaches a third-party model.

Not a DLP product: emails, phone numbers, card-like and long account-like digit
runs are replaced by placeholders. Short numbers (amounts, hours, leverage
ratios) are kept because the draft may legitimately echo them.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<![\w:])\+?\d[\d\s().-]{8,}\d\b")
_LONG_DIGITS = re.compile(r"\b\d{7,}\b")  # account / transaction ids


def mask(text: str) -> str:
    text = _EMAIL.sub("[EMAIL]", text)
    text = _CARD.sub("[CARD]", text)
    text = _PHONE.sub("[PHONE]", text)
    text = _LONG_DIGITS.sub("[ID]", text)
    return text
