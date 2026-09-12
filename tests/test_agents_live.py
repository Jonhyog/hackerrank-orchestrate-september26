import csv
import os
from dataclasses import replace
from pathlib import Path

import pytest

from agents import UsageLog, configured_ports
from config import load_config
from evidence import EvidenceInterpretation
from slice import for_request
from sources import Request, load_world

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.live
def test_live_image_request_fills_blank_salary_amount(tmp_path: Path):
    if os.environ.get("CURSOR_LIVE_SMOKE") != "1":
        pytest.skip("set CURSOR_LIVE_SMOKE=1 to hit the Cursor SDK")
    config = load_config()
    if not config.cursor_api_key:
        pytest.skip("CURSOR_API_KEY is not set")
    world = load_world(config.dataset_dir)
    request = _sample_request("request_03")
    usage = UsageLog()
    ports = configured_ports(replace(config, sandbox_root=tmp_path), usage)

    assert ports.interpret_image is not None
    interpretation = ports.interpret_image(for_request(world, request))

    assert isinstance(interpretation, EvidenceInterpretation)
    assert interpretation.action == "fill_amount"
    assert interpretation.event_id == "event_253"
    assert interpretation.amount.replace(",", "").replace(" ", "") == "4365000"
    assert usage.records
    assert usage.records[0].stage == "image"
    assert usage.records[0].total_tokens >= 0
    image_cwd = tmp_path / "request_03" / "image"
    assert image_cwd.is_dir()
    assert image_cwd != REPO_ROOT
    assert (image_cwd / "image_01.png").exists()
    assert (image_cwd / "candidate_event.csv").exists()
    assert not (image_cwd / "messages.csv").exists()


def _sample_request(request_id: str) -> Request:
    path = REPO_ROOT / "dataset" / "sample_requests.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        row = next(
            item for item in csv.DictReader(handle) if item["request_id"] == request_id
        )
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
