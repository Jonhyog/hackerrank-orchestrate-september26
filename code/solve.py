from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from decision import decide
from dossier import DossierDecision, RequestDossier, build_dossier
from evidence import (
    EvidenceInterpretation,
    accepted_interpretations,
    apply_interpretations,
    interpretations_from_port,
    reserve_unknown_debits,
)
from exchange_rates import RateBook
from ledger import amount_safe_and_earliest
from slice import RequestSlice, for_request, write_sandbox
from sources import Request, World
from writer.splice import splice

InterpretationResult = EvidenceInterpretation | Sequence[EvidenceInterpretation] | None


@dataclass(frozen=True)
class Ports:
    interpret_image: Callable[[RequestSlice], InterpretationResult] | None = None
    interpret_message: Callable[[RequestSlice], InterpretationResult] | None = None
    explain: Callable[[RequestDossier], Any] | None = None


@dataclass(frozen=True)
class Decision:
    request_id: str
    amount_safe_to_pay: float
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
    evidence_facts = accepted_interpretations(request_slice.events, interpretations)
    request_slice = replace(
        request_slice,
        events=reserve_unknown_debits(
            apply_interpretations(request_slice.events, interpretations)
        ),
    )
    if sandbox_root is not None:
        write_sandbox(request, request_slice, sandbox_root)
    amount_safe, earliest = amount_safe_and_earliest(
        request_slice.profile, request_slice.events, request
    )
    plan = decide(
        request_slice.profile,
        request_slice.events,
        request,
        request_slice.payment_options,
        amount_safe,
        earliest,
    )
    engine = Decision(
        request_id=request.request_id,
        amount_safe_to_pay=amount_safe,
        affordability_status=plan.affordability_status,
        recommended_payment_method=plan.recommended_payment_method,
        payment_plan=plan.payment_plan,
        earliest_date_for_full_payment=earliest,
        spending_changes_needed=plan.spending_changes_needed,
        decision_explanation="Stub Decision: no payment is recommended yet.",
    )
    if ports is None or ports.explain is None:
        return engine
    dossier = build_dossier(
        request,
        request_slice.profile,
        DossierDecision(
            amount_safe_to_pay=engine.amount_safe_to_pay,
            affordability_status=engine.affordability_status,
            recommended_payment_method=engine.recommended_payment_method,
            payment_plan=engine.payment_plan,
            earliest_date_for_full_payment=engine.earliest_date_for_full_payment,
            spending_changes_needed=engine.spending_changes_needed,
        ),
        request_slice.payment_options,
        evidence_facts,
    )
    return splice(engine, ports.explain(dossier))
