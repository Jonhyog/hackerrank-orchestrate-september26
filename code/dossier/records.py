from dataclasses import dataclass

from evidence.schemas import EvidenceInterpretation
from sources import PaymentOption, Request


@dataclass(frozen=True)
class DossierDecision:
    amount_safe_to_pay: float
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str


@dataclass(frozen=True)
class ForecastSummary:
    request_date: str
    horizon_end: str
    home_currency: str
    minimum_balance_to_keep: str


@dataclass(frozen=True)
class RequestDossier:
    request: Request
    decision: DossierDecision
    forecast: ForecastSummary
    payment_options: tuple[PaymentOption, ...]
    evidence_facts: tuple[EvidenceInterpretation, ...]
