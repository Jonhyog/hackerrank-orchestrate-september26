from datetime import date, timedelta
from decimal import Decimal

from sources import PaymentOption, Request, UserProfile


def considers(profile: UserProfile, method: str) -> bool:
    return method in pipe_values(profile.payment_methods_user_will_consider)


def pipe_values(raw: str) -> set[str]:
    return {part for part in raw.split("|") if part}


def partial_is_eligible(
    profile: UserProfile,
    request: Request,
    amount_safe: Decimal,
    requested: Decimal,
    earliest: str,
) -> bool:
    return (
        request.allows_partial_payment
        and considers(profile, "partial_payment")
        and Decimal("0") < amount_safe < requested
        and bool(earliest)
        and earliest <= request.desired_completion_date
    )


def max_installment_months(profile: UserProfile) -> int | None:
    raw = profile.max_installment_months.strip()
    if not raw:
        return None
    return int(raw)


def installment_payments(
    option: PaymentOption,
) -> tuple[tuple[str, Decimal], ...]:
    if option.number_of_payments < 1 or not option.first_payment_date:
        return ()
    try:
        first = date.fromisoformat(option.first_payment_date)
        step = int(option.payment_frequency_days)
    except ValueError:
        return ()
    amount = Decimal(str(option.payment_amount))
    return tuple(
        (
            (first + timedelta(days=index * step)).isoformat(),
            amount,
        )
        for index in range(option.number_of_payments)
    )


def plan_entry(day: str, amount: Decimal) -> str:
    return f"{day}:{format_amount(amount)}"


def format_amount(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    if quantized == quantized.to_integral():
        return str(int(quantized))
    return f"{quantized:.2f}"
