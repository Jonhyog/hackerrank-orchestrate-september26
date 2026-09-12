from dataclasses import dataclass

from sources import Request, World


@dataclass(frozen=True)
class Ports:
    interpret_image: object | None = None
    interpret_message: object | None = None
    explain: object | None = None


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


def solve(world: World, request: Request, ports: Ports | None = None) -> Decision:
    _ = (world, ports)
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
