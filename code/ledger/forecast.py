from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ledger.parse import as_date, parse_amount
from ledger.recurrence import (
    detect_commitments,
    occupied_dates,
    project_commitment,
)
from sources import FinancialEvent, Request, UserProfile

FORECAST_HORIZON_DAYS = 90
_CASH = frozenset({"debit", "credit"})
_IGNORE = frozenset({"cancelled", "failed", "unrealized"})


def amount_safe_and_earliest(
    profile: UserProfile | None,
    events: tuple[FinancialEvent, ...],
    request: Request,
) -> tuple[float, str]:
    if profile is None:
        return 0.0, ""
    request_day = date.fromisoformat(request.request_date)
    requested = Decimal(str(request.requested_amount))
    balances = daily_balances(profile, events, request_day)
    minimum = Decimal(str(profile.minimum_balance_to_keep))
    trough = min(balances.values())
    safe = _clamp_to_request(trough - minimum, requested)
    earliest = _earliest_full_payment(balances, minimum, requested, request_day)
    return _as_number(safe), earliest


def daily_balances(
    profile: UserProfile,
    events: tuple[FinancialEvent, ...],
    request_day: date,
    spending_changes: tuple[tuple[str, str, str, Decimal | None], ...] = (),
) -> dict[date, Decimal]:
    return _daily_balances(profile, events, request_day, spending_changes)


def payments_are_safe(
    balances: dict[date, Decimal],
    minimum: Decimal,
    payments: tuple[tuple[date, Decimal], ...],
    request_day: date,
) -> bool:
    if not balances:
        return False
    horizon = max(balances)
    last_day = horizon
    if payments:
        last_day = max(last_day, max(day for day, _amount in payments))
    day = request_day
    last_balance = balances[request_day]
    while day <= last_day:
        balance = balances.get(day, last_balance)
        last_balance = balances.get(day, last_balance)
        for pay_on, amount in payments:
            if day >= pay_on:
                balance -= amount
        if balance < minimum:
            return False
        day += timedelta(days=1)
    return True


def _daily_balances(
    profile: UserProfile,
    events: tuple[FinancialEvent, ...],
    request_day: date,
    spending_changes: tuple[tuple[str, str, str, Decimal | None], ...] = (),
) -> dict[date, Decimal]:
    horizon = request_day + timedelta(days=FORECAST_HORIZON_DAYS)
    flows: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for day, amount in _recorded_flows(
        events, request_day, horizon, spending_changes
    ):
        flows[day] += amount
    commitments = detect_commitments(events, request_day)
    taken = occupied_dates(events)
    for commitment in commitments:
        for day, amount in project_commitment(commitment, request_day, horizon, taken):
            flows[day] += _apply_spending_change(
                commitment.category, commitment.description, amount, spending_changes
            )
    balance = Decimal(str(profile.current_available_balance))
    balances: dict[date, Decimal] = {}
    day = request_day
    while day <= horizon:
        balance += flows[day]
        balances[day] = balance
        day += timedelta(days=1)
    return balances


def _apply_spending_change(
    category: str,
    description: str,
    amount: Decimal,
    spending_changes: tuple[tuple[str, str, str, Decimal | None], ...],
) -> Decimal:
    for kind, change_category, change_description, new_amount in spending_changes:
        if change_category != category or change_description != description:
            continue
        if kind == "stop":
            return Decimal("0")
        if kind == "reduce" and new_amount is not None:
            if amount < 0:
                return -new_amount
            return new_amount
    return amount


def _recorded_flows(
    events: tuple[FinancialEvent, ...],
    request_day: date,
    horizon: date,
    spending_changes: tuple[tuple[str, str, str, Decimal | None], ...] = (),
) -> list[tuple[date, Decimal]]:
    flows: list[tuple[date, Decimal]] = []
    for event in events:
        if event.status in _IGNORE or event.direction not in _CASH:
            continue
        if event.status == "pending" and event.direction == "credit":
            continue
        amount = parse_amount(event.amount)
        settled = as_date(event.settlement_date)
        if amount is None or settled is None:
            continue
        if settled < request_day or settled > horizon:
            continue
        if event.status == "settled" and settled <= request_day:
            continue
        signed = -amount if event.direction == "debit" else amount
        signed = _apply_spending_change(
            event.category, event.description, signed, spending_changes
        )
        if signed == 0:
            continue
        flows.append((settled, signed))
    return flows


def _earliest_full_payment(
    balances: dict[date, Decimal],
    minimum: Decimal,
    requested: Decimal,
    request_day: date,
) -> str:
    horizon = request_day + timedelta(days=FORECAST_HORIZON_DAYS)
    day = request_day
    while day <= horizon:
        if _full_payment_is_safe(
            balances, minimum, requested, request_day, horizon, day
        ):
            return day.isoformat()
        day += timedelta(days=1)
    return ""


def _full_payment_is_safe(
    balances: dict[date, Decimal],
    minimum: Decimal,
    requested: Decimal,
    request_day: date,
    horizon: date,
    pay_on: date,
) -> bool:
    day = request_day
    while day <= horizon:
        balance = balances[day]
        if day >= pay_on:
            balance -= requested
        if balance < minimum:
            return False
        day += timedelta(days=1)
    return True


def _clamp_to_request(available: Decimal, requested: Decimal) -> Decimal:
    if available <= 0 or requested <= 0:
        return Decimal("0")
    return min(available, requested)


def _as_number(value: Decimal) -> float:
    quantized = value.quantize(Decimal("0.01"))
    if quantized == quantized.to_integral():
        return float(int(quantized))
    return float(quantized)
