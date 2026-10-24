"""Compare explicit fiscal dates without mistaking leap days for year-end changes."""
from __future__ import annotations

from collections.abc import Iterable
import re

from persiantools.jdatetime import JalaliDate


def comparable_fiscal_year_ends(periods: Iterable[str]) -> bool:
    """Accept the same calendar day or the same validated month-end convention.

    The source dates remain untouched. A fixed Esfand 29 is valid even in a
    leap year; Esfand 29/30 are interchangeable only when every date is the
    actual last day of its own month.
    """
    boundaries: list[tuple[int, int, bool]] = []
    for period in periods:
        if not isinstance(period, str) or not re.fullmatch(r"1[34]\d{2}/\d{2}/\d{2}", period):
            return False
        year, month, day = map(int, period.split("/"))
        try:
            current = JalaliDate(year, month, day).to_gregorian()
            following = JalaliDate(year + 1, 1, 1) if month == 12 else JalaliDate(year, month + 1, 1)
        except ValueError:
            return False
        month_end = (following.to_gregorian() - current).days == 1
        boundaries.append((month, day, month_end))
    if not boundaries:
        return False
    same_day = len({(month, day) for month, day, _ in boundaries}) == 1
    same_month_end = len({month for month, _, _ in boundaries}) == 1 and all(
        is_end for _, _, is_end in boundaries
    )
    return same_day or same_month_end
