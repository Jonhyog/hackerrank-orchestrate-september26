from datetime import date, timedelta

from dossier.records import DossierDecision, ForecastSummary, RequestDossier
from dossier.write import write_dossier
from evidence.schemas import EvidenceInterpretation
from ledger.forecast import FORECAST_HORIZON_DAYS
from sources import PaymentOption, Request, UserProfile

__all__ = [
    "DossierDecision",
    "ForecastSummary",
    "RequestDossier",
    "build_dossier",
    "write_dossier",
]


def build_dossier(
    request: Request,
    profile: UserProfile | None,
    decision: DossierDecision,
    payment_options: tuple[PaymentOption, ...],
    evidence_facts: tuple[EvidenceInterpretation, ...],
) -> RequestDossier:
    request_day = date.fromisoformat(request.request_date)
    return RequestDossier(
        request=request,
        decision=decision,
        forecast=ForecastSummary(
            request_date=request.request_date,
            horizon_end=(
                request_day + timedelta(days=FORECAST_HORIZON_DAYS)
            ).isoformat(),
            home_currency=(profile.home_currency.value if profile is not None else ""),
            minimum_balance_to_keep=(
                _as_amount(profile.minimum_balance_to_keep)
                if profile is not None
                else ""
            ),
        ),
        payment_options=payment_options,
        evidence_facts=evidence_facts,
    )


def _as_amount(value: float) -> str:
    if float(value) == int(value):
        return str(int(value))
    return str(value)
