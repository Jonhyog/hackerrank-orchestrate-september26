from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from evidence import (
    EvidenceInterpretation,
    apply_interpretations,
    interpretations_from_port,
    reserve_unknown_debits,
)
from exchange_rates import RateBook
from slice import RequestSlice, for_request, write_sandbox
from sources import Request, World

InterpretationResult = EvidenceInterpretation | Sequence[EvidenceInterpretation] | None


@dataclass(frozen=True)
class Ports:
    interpret_image: Callable[[RequestSlice], InterpretationResult] | None = None
    interpret_message: Callable[[RequestSlice], InterpretationResult] | None = None
    explain: Callable[..., Any] | None = None


@dataclass(frozen=True)
class Decision:
    request_id: str
    amount_safe_to_pay: int
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str


def solve(
    world: World,
    request: Request,
    ports: Ports | None = None,
    sandbox_root: Path | None = None,
) -> Decision:
    request_slice = for_request(world, request)
    if request_slice.profile is not None:
        request_slice = replace(
            request_slice,
            events=RateBook(world.exchange_rates).convert_cash_events(
                request_slice.events,
                request_slice.profile.home_currency,
            ),
        )
    if sandbox_root is not None:
        write_sandbox(request, request_slice, sandbox_root)
    interpretations: list[EvidenceInterpretation] = []
    if ports is not None:
        if request_slice.image is not None and ports.interpret_image is not None:
            interpretations.extend(
                interpretations_from_port(ports.interpret_image, request_slice)
            )
        if request_slice.messages and ports.interpret_message is not None:
            interpretations.extend(
                interpretations_from_port(ports.interpret_message, request_slice)
            )
    request_slice = replace(
        request_slice,
        events=reserve_unknown_debits(
            apply_interpretations(request_slice.events, interpretations)
        ),
    )
    if sandbox_root is not None:
        write_sandbox(request, request_slice, sandbox_root)
    return Decision(
        request_id=request.request_id,
        amount_safe_to_pay=0,
        affordability_status="not_affordable",
        recommended_payment_method="not_recommended",
        payment_plan="none",
        earliest_date_for_full_payment="",
        spending_changes_needed="none",
        decision_explanation="Stub Decision: no payment is recommended yet.",
    )
