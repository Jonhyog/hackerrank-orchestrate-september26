from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slice import RequestSlice, for_request, write_sandbox
from sources import Request, World


@dataclass(frozen=True)
class Ports:
    interpret_image: Callable[[RequestSlice], Any] | None = None
    interpret_message: Callable[[RequestSlice], Any] | None = None
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
    if sandbox_root is not None:
        write_sandbox(request, request_slice, sandbox_root)
    if ports is not None:
        if request_slice.image is not None and ports.interpret_image is not None:
            ports.interpret_image(request_slice)
        if request_slice.messages and ports.interpret_message is not None:
            ports.interpret_message(request_slice)
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
