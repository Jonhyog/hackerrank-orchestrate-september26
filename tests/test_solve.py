from dataclasses import asdict

from solve import solve
from sources import Request, World


def test_solve_returns_placeholder_decision_for_the_request():
    request = Request(
        request_id="request_26",
        user_id="user_26",
        request_date="2025-08-03",
        request_type="family_transfer",
        requested_amount=15656000,
        desired_completion_date="2025-10-07",
        allows_partial_payment=False,
        request_text="transfer",
    )
    world = World(requests=(request,))

    decision = solve(world, request, ports=None)

    assert asdict(decision) == {
        "request_id": "request_26",
        "amount_safe_to_pay": 0,
        "affordability_status": "not_affordable",
        "recommended_payment_method": "not_recommended",
        "payment_plan": "none",
        "earliest_date_for_full_payment": "",
        "spending_changes_needed": "none",
        "decision_explanation": "Stub Decision: no payment is recommended yet.",
    }
