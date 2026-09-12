import csv
from collections.abc import Sequence
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from dossier.records import DossierDecision, ForecastSummary, RequestDossier
from evidence.schemas import EvidenceInterpretation
from sources import PaymentOption, Request


def write_dossier(sandbox_root: Path, dossier: RequestDossier) -> Path:
    cwd = sandbox_root / dossier.request.request_id / "explain"
    cwd.mkdir(parents=True, exist_ok=True)
    _write_records(cwd / "request.csv", Request, (dossier.request,))
    _write_records(cwd / "decision.csv", DossierDecision, (dossier.decision,))
    _write_records(cwd / "forecast_horizon.csv", ForecastSummary, (dossier.forecast,))
    _write_records(cwd / "payment_options.csv", PaymentOption, dossier.payment_options)
    _write_records(
        cwd / "evidence_facts.csv", EvidenceInterpretation, dossier.evidence_facts
    )
    return cwd


def _write_records(path: Path, record_type: type[Any], rows: Sequence[Any]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[field.name for field in fields(record_type)],
        )
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
