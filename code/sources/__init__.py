import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Request:
    request_id: str
    user_id: str
    request_date: str
    request_type: str
    requested_amount: float
    desired_completion_date: str
    allows_partial_payment: bool
    request_text: str


@dataclass(frozen=True)
class World:
    requests: tuple[Request, ...]


def load_world(dataset_dir: Path) -> World:
    path = dataset_dir / "requests.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        requests = tuple(_request_from_row(row) for row in csv.DictReader(handle))
    return World(requests=requests)


def _request_from_row(row: dict[str, str]) -> Request:
    return Request(
        request_id=row["request_id"],
        user_id=row["user_id"],
        request_date=row["request_date"],
        request_type=row["request_type"],
        requested_amount=float(row["requested_amount"]),
        desired_completion_date=row["desired_completion_date"],
        allows_partial_payment=row["allows_partial_payment"].strip().lower() == "true",
        request_text=row["request_text"],
    )
