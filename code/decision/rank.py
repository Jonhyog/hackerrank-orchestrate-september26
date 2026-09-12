from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import combinations

from decision.changes import as_forecast_edits, eligible_changes, format_changes
from decision.eligibility import (
    considers,
    installment_payments,
    max_installment_months,
    partial_is_eligible,
    plan_entry,
)
from ledger import daily_balances, payments_are_safe
from sources import FinancialEvent, PaymentOption, Request, UserProfile


@dataclass(frozen=True)
class RankedPlan:
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    spending_changes_needed: str


@dataclass(frozen=True)
class _Candidate:
    status: str
    method: str
    plan: str
    spending_changes: str
    completes_by_deadline: bool
    total_paid: Decimal
    start_date: str
    payment_count: int
    option_id: str


def decide(
    profile: UserProfile | None,
    events: tuple[FinancialEvent, ...],
    request: Request,
    payment_options: tuple[PaymentOption, ...],
    amount_safe: float,
    earliest: str,
) -> RankedPlan:
    if profile is None:
        return _not_recommended()
    request_day = date.fromisoformat(request.request_date)
    balances = daily_balances(profile, events, request_day)
    minimum = Decimal(str(profile.minimum_balance_to_keep))
    safe = Decimal(str(amount_safe))
    candidates = _candidates(
        profile,
        request,
        payment_options,
        safe,
        earliest,
        balances,
        minimum,
        request_day,
    )
    if not any(candidate.completes_by_deadline for candidate in candidates):
        candidates.extend(
            _spending_change_candidates(
                profile,
                events,
                request,
                payment_options,
                minimum,
                request_day,
            )
        )
    if not candidates:
        return _not_recommended()
    winner = min(candidates, key=_rank_key)
    return RankedPlan(
        affordability_status=winner.status,
        recommended_payment_method=winner.method,
        payment_plan=winner.plan,
        spending_changes_needed=winner.spending_changes,
    )


def _candidates(
    profile: UserProfile,
    request: Request,
    payment_options: tuple[PaymentOption, ...],
    amount_safe: Decimal,
    earliest: str,
    balances: dict[date, Decimal],
    minimum: Decimal,
    request_day: date,
    spending_changes: str = "none",
) -> list[_Candidate]:
    requested = Decimal(str(request.requested_amount))
    found: list[_Candidate] = []
    full = _full_payment_today(
        profile, request, requested, balances, minimum, request_day, spending_changes
    )
    if full is not None:
        found.append(full)
    if spending_changes == "none" and partial_is_eligible(
        profile, request, amount_safe, requested, earliest
    ):
        remainder = requested - amount_safe
        found.append(
            _candidate(
                status="affordable_with_plan",
                method="partial_payment",
                payments=(
                    (request.request_date, amount_safe),
                    (earliest, remainder),
                ),
                deadline=request.desired_completion_date,
            )
        )
    if considers(profile, "installments"):
        found.extend(
            _installment_candidates(
                profile,
                request,
                payment_options,
                balances,
                minimum,
                request_day,
                spending_changes,
            )
        )
    if (
        spending_changes == "none"
        and considers(profile, "full_payment")
        and earliest > request.request_date
    ):
        found.append(
            _candidate(
                status="affordable_later",
                method="wait",
                payments=((earliest, requested),),
                deadline=request.desired_completion_date,
            )
        )
    return found


def _full_payment_today(
    profile: UserProfile,
    request: Request,
    requested: Decimal,
    balances: dict[date, Decimal],
    minimum: Decimal,
    request_day: date,
    spending_changes: str,
) -> _Candidate | None:
    if not considers(profile, "full_payment"):
        return None
    dated = ((request_day, requested),)
    if not payments_are_safe(balances, minimum, dated, request_day):
        return None
    return _candidate(
        status="affordable_now"
        if spending_changes == "none"
        else "affordable_with_plan",
        method="full_payment",
        payments=((request.request_date, requested),),
        deadline=request.desired_completion_date,
        spending_changes=spending_changes,
    )


def _spending_change_candidates(
    profile: UserProfile,
    events: tuple[FinancialEvent, ...],
    request: Request,
    payment_options: tuple[PaymentOption, ...],
    minimum: Decimal,
    request_day: date,
) -> list[_Candidate]:
    actions = eligible_changes(profile, events, request_day)
    found: list[_Candidate] = []
    for size in range(1, min(3, len(actions)) + 1):
        for combo in combinations(actions, size):
            if len({action.event_id for action in combo}) != len(combo):
                continue
            balances = daily_balances(
                profile, events, request_day, as_forecast_edits(combo)
            )
            found.extend(
                _candidates(
                    profile,
                    request,
                    payment_options,
                    Decimal("0"),
                    "",
                    balances,
                    minimum,
                    request_day,
                    format_changes(combo),
                )
            )
    return found


def _installment_candidates(
    profile: UserProfile,
    request: Request,
    payment_options: tuple[PaymentOption, ...],
    balances: dict[date, Decimal],
    minimum: Decimal,
    request_day: date,
    spending_changes: str = "none",
) -> list[_Candidate]:
    months = max_installment_months(profile)
    if months is None:
        return []
    found: list[_Candidate] = []
    for option in payment_options:
        if option.payment_method != "installments":
            continue
        if option.number_of_payments > months:
            continue
        payments = installment_payments(option)
        if not payments:
            continue
        dated = tuple((date.fromisoformat(day), amount) for day, amount in payments)
        if not payments_are_safe(balances, minimum, dated, request_day):
            continue
        found.append(
            _candidate(
                status="affordable_with_plan",
                method="installments",
                payments=payments,
                deadline=request.desired_completion_date,
                option_id=option.payment_option_id,
                total_paid=Decimal(str(option.total_payable_amount)),
                spending_changes=spending_changes,
            )
        )
    return found


def _candidate(
    *,
    status: str,
    method: str,
    payments: tuple[tuple[str, Decimal], ...],
    deadline: str,
    spending_changes: str = "none",
    option_id: str = "~",
    total_paid: Decimal | None = None,
) -> _Candidate:
    start = payments[0][0]
    end = payments[-1][0]
    return _Candidate(
        status=status,
        method=method,
        plan="|".join(plan_entry(day, amount) for day, amount in payments),
        spending_changes=spending_changes,
        completes_by_deadline=end <= deadline,
        total_paid=total_paid
        if total_paid is not None
        else sum((amount for _day, amount in payments), Decimal("0")),
        start_date=start,
        payment_count=len(payments),
        option_id=option_id,
    )


def _rank_key(candidate: _Candidate) -> tuple[object, ...]:
    return (
        not candidate.completes_by_deadline,
        candidate.spending_changes != "none",
        candidate.total_paid,
        candidate.start_date,
        candidate.payment_count,
        candidate.option_id,
    )


def _not_recommended() -> RankedPlan:
    return RankedPlan(
        affordability_status="not_affordable",
        recommended_payment_method="not_recommended",
        payment_plan="none",
        spending_changes_needed="none",
    )
