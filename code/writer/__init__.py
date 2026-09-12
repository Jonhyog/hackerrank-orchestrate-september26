from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from writer.splice import explanation_text, splice

if TYPE_CHECKING:
    from solve import Decision

__all__ = [
    "COLUMNS",
    "explanation_text",
    "splice",
    "write_output",
]

COLUMNS = (
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
)


def write_output(rows: Sequence[Decision], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "request_id": row.request_id,
                    "amount_safe_to_pay": row.amount_safe_to_pay,
                    "affordability_status": row.affordability_status,
                    "recommended_payment_method": row.recommended_payment_method,
                    "payment_plan": row.payment_plan,
                    "earliest_date_for_full_payment": (
                        row.earliest_date_for_full_payment
                    ),
                    "spending_changes_needed": row.spending_changes_needed,
                    "decision_explanation": row.decision_explanation,
                }
            )
