import csv
from pathlib import Path

from typer.testing import CliRunner

from main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_FILE = REPO_ROOT / "output.csv"
EVALUATION_REQUESTS = REPO_ROOT / "dataset" / "requests.csv"

SUBMISSION_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def _evaluation_request_ids() -> list[str]:
    return [
        line.split(",", 1)[0]
        for line in EVALUATION_REQUESTS.read_text(encoding="utf-8").splitlines()[1:]
        if line
    ]


def _read_table(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_output_flag_writes_one_row_per_request_and_leaves_submission_untouched(
    tmp_path: Path,
):
    dest = tmp_path / "dev-output.csv"
    before = SUBMISSION_FILE.read_bytes() if SUBMISSION_FILE.exists() else None

    result = CliRunner().invoke(app, ["--output", str(dest)])

    assert result.exit_code == 0, result.output
    rows = _read_table(dest)
    assert list(rows[0].keys()) == SUBMISSION_COLUMNS
    assert [row["request_id"] for row in rows] == _evaluation_request_ids()
    if before is None:
        assert not SUBMISSION_FILE.exists()
    else:
        assert SUBMISSION_FILE.read_bytes() == before


def test_default_write_is_repo_root_output_csv(monkeypatch):
    monkeypatch.delenv("OUTPUT_PATH", raising=False)
    monkeypatch.delenv("DATASET_DIR", raising=False)
    before = SUBMISSION_FILE.read_bytes() if SUBMISSION_FILE.exists() else None
    try:
        result = CliRunner().invoke(app, [])

        assert result.exit_code == 0, result.output
        rows = _read_table(SUBMISSION_FILE)
        assert list(rows[0].keys()) == SUBMISSION_COLUMNS
        assert [row["request_id"] for row in rows] == _evaluation_request_ids()
    finally:
        if before is None:
            SUBMISSION_FILE.unlink(missing_ok=True)
        else:
            SUBMISSION_FILE.write_bytes(before)


def test_cli_does_not_write_environment_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "secret-from-env-not-code")
    dest = tmp_path / "dev-output.csv"

    result = CliRunner().invoke(app, ["--output", str(dest)])

    assert result.exit_code == 0, result.output
    assert "secret-from-env-not-code" not in result.output
    assert "secret-from-env-not-code" not in dest.read_text(encoding="utf-8")
