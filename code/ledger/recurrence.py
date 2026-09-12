from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ledger.parse import as_date, parse_amount
from sources import FinancialEvent

_CASH = frozenset({"debit", "credit"})
_GIG_HINTS = ("payout", "earnings", "platform", "marketplace", "freelance", "gig")


@dataclass(frozen=True)
class RecurringCommitment:
    user_id: str
    category: str
    description: str
    direction: str
    amount: Decimal
    last_settlement: date
    cadence: str
    step_days: int


def detect_commitments(
    events: tuple[FinancialEvent, ...],
    request_date: date,
) -> tuple[RecurringCommitment, ...]:
    groups: dict[tuple[str, str, str, str], list[FinancialEvent]] = defaultdict(list)
    for event in events:
        if event.status != "settled" or event.direction not in _CASH:
            continue
        amount = parse_amount(event.amount)
        settled = as_date(event.settlement_date)
        if amount is None or settled is None or settled > request_date:
            continue
        key = (event.user_id, event.category, event.description, event.direction)
        groups[key].append(event)

    commitments: list[RecurringCommitment] = []
    for (user_id, category, description, direction), items in groups.items():
        items = sorted(items, key=lambda event: event.settlement_date)
        if len(items) < 3:
            continue
        settled_days = [as_date(event.settlement_date) for event in items]
        if any(day is None for day in settled_days):
            continue
        days = [day for day in settled_days if day is not None]
        gaps = [(days[index] - days[index - 1]).days for index in range(1, len(days))]
        cadence = _cadence(gaps)
        if cadence is None:
            continue
        if direction == "credit" and (
            _skip_income(description)
            or _salary_series_stopped(events, category, items[-1])
        ):
            continue
        amounts = [
            amount
            for amount in (parse_amount(event.amount) for event in items)
            if amount is not None
        ]
        if not amounts:
            continue
        kind, step = cadence
        commitments.append(
            RecurringCommitment(
                user_id=user_id,
                category=category,
                description=description,
                direction=direction,
                amount=max(amounts[-3:]),
                last_settlement=days[-1],
                cadence=kind,
                step_days=step,
            )
        )
    return tuple(commitments)


def project_commitment(
    commitment: RecurringCommitment,
    request_date: date,
    horizon: date,
    occupied: set[tuple[str, str, str]],
) -> list[tuple[date, Decimal]]:
    flows: list[tuple[date, Decimal]] = []
    current = commitment.last_settlement
    while True:
        current = _next_date(current, commitment)
        if current > horizon:
            break
        if current < request_date:
            continue
        key = (commitment.category, commitment.description, current.isoformat())
        if key in occupied:
            continue
        signed = (
            -commitment.amount
            if commitment.direction == "debit"
            else commitment.amount
        )
        flows.append((current, signed))
    return flows


def occupied_dates(events: tuple[FinancialEvent, ...]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for event in events:
        if event.status in {"cancelled", "failed", "unrealized"}:
            continue
        if not event.settlement_date:
            continue
        keys.add((event.category, event.description, event.settlement_date))
    return keys


def _cadence(gaps: list[int]) -> tuple[str, int] | None:
    if not gaps:
        return None
    if _mostly_monthly(gaps):
        return ("monthly", 1)
    if all(6 <= gap <= 9 for gap in gaps):
        return ("weekly", 7)
    if all(13 <= gap <= 17 for gap in gaps):
        return ("biweekly", 14)
    return None


def _mostly_monthly(gaps: list[int]) -> bool:
    if all(27 <= gap <= 35 for gap in gaps):
        return True
    if len(gaps) < 2 or any(gap > 45 for gap in gaps):
        return False
    in_band = sum(1 for gap in gaps if 27 <= gap <= 35)
    return in_band >= len(gaps) - 1 and in_band >= 1


def _next_date(current: date, commitment: RecurringCommitment) -> date:
    if commitment.cadence == "monthly":
        return _add_months(current, 1)
    return current + timedelta(days=commitment.step_days)


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, _month_length(year, month))
    return date(year, month, day)


def _month_length(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - timedelta(days=1)).day


def _salary_series_stopped(
    events: tuple[FinancialEvent, ...],
    category: str,
    last: FinancialEvent,
) -> bool:
    if category != "salary":
        return False
    last_day = last.settlement_date
    for event in events:
        if event.category != "salary" or event.direction != "credit":
            continue
        if event.settlement_date < last_day:
            continue
        if "final" in event.description.lower():
            return True
    return False


def _skip_income(description: str) -> bool:
    lowered = description.lower()
    return any(hint in lowered for hint in _GIG_HINTS)
