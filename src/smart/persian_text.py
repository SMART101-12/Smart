"""Unicode normalization helpers for Persian/Arabic market text."""

from __future__ import annotations


def normalize_persian_text(value: str) -> str:
    """Normalize common Arabic/Persian variants for deterministic matching.

    Raw TSETMC payloads must remain unchanged; this helper is only for
    comparisons and symbol resolution.
    """
    if value is None:
        return ""
    return (
        str(value)
        .replace("ي", "ی")
        .replace("ى", "ی")
        .replace("ك", "ک")
        .replace("ـ", "")
        .strip()
    )
