"""
Date/time utilities following the Brazilian 252 business-day convention.

Note: For production use, a proper Brazilian holiday calendar should be
plugged in (e.g. via the `holidays` library with BR locale). Here we use
a simplified Saturday/Sunday exclusion plus the most common national
holidays, which is accurate enough for pricing purposes.
"""
from __future__ import annotations

from datetime import date, timedelta


# Brazilian national holidays (fixed-date only — variable ones omitted for brevity)
_FIXED_HOLIDAYS: set[tuple[int, int]] = {
    (1, 1),    # Ano Novo
    (4, 21),   # Tiradentes
    (5, 1),    # Dia do Trabalho
    (9, 7),    # Independência
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),   # Finados
    (11, 15),  # Proclamação da República
    (12, 25),  # Natal
}


def is_business_day(d: date) -> bool:
    """Return True if *d* is a Brazilian business day."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if (d.month, d.day) in _FIXED_HOLIDAYS:
        return False
    return True


def business_days_between(start: date, end: date) -> int:
    """
    Count business days between *start* (inclusive) and *end* (exclusive).
    Follows the Brazilian 252-day convention.
    """
    if end <= start:
        return 0
    count = 0
    current = start
    while current < end:
        if is_business_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def years_to_maturity(maturity: date, ref: date | None = None) -> float:
    """
    Return years to maturity as a fraction using the 252 business-day basis.
    Standard: years = du / 252 where du = business days remaining.
    """
    if ref is None:
        ref = date.today()
    du = business_days_between(ref, maturity)
    return du / 252.0


def next_coupon_dates(
    maturity: date,
    ref: date,
    frequency: int = 2,
) -> list[date]:
    """
    Generate all remaining coupon dates for a semi-annual bond (NTN-F / NTN-B).

    Coupons are paid on the 1st of the coupon month, every (12 // frequency) months
    counting back from maturity.

    Args:
        maturity: Bond maturity date.
        ref: Reference (pricing) date.
        frequency: Coupons per year (default 2 = semi-annual).

    Returns:
        Sorted list of future coupon dates (including final payment at maturity).
    """
    months_between_coupons = 12 // frequency
    dates: list[date] = []
    coupon_date = maturity
    while coupon_date > ref:
        dates.append(coupon_date)
        # step back by coupon interval
        month = coupon_date.month - months_between_coupons
        year = coupon_date.year
        while month <= 0:
            month += 12
            year -= 1
        coupon_date = date(year, month, coupon_date.day)
    dates.sort()
    return dates
