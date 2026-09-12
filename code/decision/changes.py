from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from decision.eligibility import format_amount, pipe_values
from ledger.parse import parse_amount
from ledger.recurrence import detect_commitments
from sources import FinancialEvent, UserProfile

_STOP = frozenset({"stoppable", "reducible_or_stoppable"})
_REDUCE = frozenset({"reducible", "reducible_or_stoppable"})


@dataclass(frozen=True)
class SpendingChange:
    event_id: str
    kind: str
    category: str
    description: str
    amount: Decimal | None


def eligible_changes(
    profile: UserProfile,
    events: tuple[FinancialEvent, ...],
    request_day: date,
) -> tuple[SpendingChange, ...]:
    protected = pipe_values(profile.expense_categories_to_protect)
    can_stop = pipe_values(profile.expense_categories_user_is_willing_to_stop)
    can_reduce = pipe_values(profile.expense_categories_user_is_willing_to_reduce)
    recurring = {
        (item.category, item.description)
        for item in detect_commitments(events, request_day)
    }
    found: list[SpendingChange] = []
    for event in _latest_flexible_events(events, recurring):
        if event.category in protected:
            continue
        if event.flexibility in _STOP and event.category in can_stop:
            found.append(
                SpendingChange(
                    event.event_id,
                    "stop",
                    event.category,
                    event.description,
                    None,
                )
            )
        if event.flexibility in _REDUCE and event.category in can_reduce:
            amount = parse_amount(event.minimum_allowed_amount)
            if amount is not None:
                found.append(
                    SpendingChange(
                        event.event_id,
                        "reduce",
                        event.category,
                        event.description,
                        amount,
                    )
                )
    return tuple(found)


def format_changes(changes: tuple[SpendingChange, ...]) -> str:
    parts: list[str] = []
    for change in sorted(changes, key=lambda item: item.event_id):
        if change.kind == "stop":
            parts.append(f"stop:{change.event_id}")
        elif change.kind == "reduce" and change.amount is not None:
            parts.append(
                f"reduce_to:{change.event_id}:{format_amount(change.amount)}"
            )
    return "|".join(parts) if parts else "none"


def as_forecast_edits(
    changes: tuple[SpendingChange, ...],
) -> tuple[tuple[str, str, str, Decimal | None], ...]:
    return tuple(
        (change.kind, change.category, change.description, change.amount)
        for change in changes
    )


def _latest_flexible_events(
    events: tuple[FinancialEvent, ...],
    recurring: set[tuple[str, str]],
) -> list[FinancialEvent]:
    chosen: dict[tuple[str, str], FinancialEvent] = {}
    for event in events:
        key = (event.category, event.description)
        if key not in recurring or event.direction != "debit":
            continue
        if event.flexibility not in _STOP | _REDUCE:
            continue
        current = chosen.get(key)
        if current is None or (event.settlement_date, event.event_id) > (
            current.settlement_date,
            current.event_id,
        ):
            chosen[key] = event
    return list(chosen.values())
