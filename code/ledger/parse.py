from datetime import date
from decimal import Decimal

from utils.dates import calendar_date


def parse_amount(raw: str) -> Decimal | None:
    text = raw.strip()
    if not text:
        return None
    return Decimal(text)


def as_date(raw: str) -> date | None:
    day = calendar_date(raw)
    if day is None:
        return None
    return date.fromisoformat(day)
