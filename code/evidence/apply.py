from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from evidence.schemas import EvidenceInterpretation
from sources import FinancialEvent

_RETRY_ATTEMPTS = 2
_ALLOWED_ACTIONS = frozenset({"fill_amount", "cancel", "delay", "confirm", "amend"})
_EXPLICIT_ACTIONS = frozenset({"cancel", "confirm", "amend"})


def interpretations_from_port(
    port: Callable[..., Any],
    request_slice: Any,
) -> tuple[EvidenceInterpretation, ...]:
    for _ in range(_RETRY_ATTEMPTS):
        try:
            normalized = _normalize(port(request_slice))
        except Exception:
            continue
        if normalized is not None:
            return normalized
    return ()


def accepted_interpretations(
    events: tuple[FinancialEvent, ...],
    interpretations: Sequence[EvidenceInterpretation],
) -> tuple[EvidenceInterpretation, ...]:
    by_id = {event.event_id: event for event in events}
    accepted: list[EvidenceInterpretation] = []
    for interpretation in _resolve_conflicts(interpretations):
        current = by_id.get(interpretation.event_id)
        if current is None:
            continue
        if _apply_one(current, interpretation) is not None:
            accepted.append(interpretation)
    return tuple(accepted)


def apply_interpretations(
    events: tuple[FinancialEvent, ...],
    interpretations: Sequence[EvidenceInterpretation],
) -> tuple[FinancialEvent, ...]:
    by_id = {event.event_id: event for event in events}
    for interpretation in _resolve_conflicts(interpretations):
        current = by_id.get(interpretation.event_id)
        if current is None:
            continue
        updated = _apply_one(current, interpretation)
        if updated is not None:
            by_id[interpretation.event_id] = updated
    return tuple(by_id[event.event_id] for event in events)


def _resolve_conflicts(
    interpretations: Sequence[EvidenceInterpretation],
) -> tuple[EvidenceInterpretation, ...]:
    grouped: dict[str, list[EvidenceInterpretation]] = defaultdict(list)
    for interpretation in interpretations:
        if interpretation.action not in _ALLOWED_ACTIONS:
            continue
        grouped[interpretation.event_id].append(interpretation)
    return tuple(_pick_conflict_winner(items) for items in grouped.values())


def _pick_conflict_winner(
    items: Sequence[EvidenceInterpretation],
) -> EvidenceInterpretation:
    explicit = [item for item in items if item.action in _EXPLICIT_ACTIONS]
    if not explicit:
        return items[-1]
    cancels = [item for item in explicit if item.action == "cancel"]
    if cancels:
        return cancels[-1]
    return explicit[-1]


def _apply_one(
    event: FinancialEvent,
    interpretation: EvidenceInterpretation,
) -> FinancialEvent | None:
    if interpretation.action == "fill_amount":
        if event.amount.strip() != "":
            return None
        return replace(event, amount=interpretation.amount)
    if interpretation.action == "cancel":
        return replace(event, status="cancelled")
    if interpretation.action == "delay":
        if not interpretation.settlement_date:
            return None
        return replace(event, settlement_date=interpretation.settlement_date)
    if interpretation.action == "confirm":
        return replace(event, status="settled")
    if interpretation.action == "amend":
        if not interpretation.amount:
            return None
        return replace(event, amount=interpretation.amount)
    return None


def _normalize(result: Any) -> tuple[EvidenceInterpretation, ...] | None:
    if result is None:
        return ()
    if isinstance(result, EvidenceInterpretation):
        return (result,)
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
        items = tuple(result)
        if all(isinstance(item, EvidenceInterpretation) for item in items):
            return items
    return None
