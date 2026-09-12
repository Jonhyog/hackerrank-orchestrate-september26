from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceInterpretation:
    action: str
    event_id: str
    amount: str = ""
    settlement_date: str = ""
