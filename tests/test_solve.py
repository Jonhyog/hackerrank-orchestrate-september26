import csv
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path

import pytest

from evidence import EvidenceInterpretation
from solve import Decision, Ports, solve
from sources import (
    ExchangeRate,
    FinancialEvent,
    Image,
    Message,
    PaymentOption,
    Request,
    UserProfile,
    World,
    load_world,
)
from utils.currency import Currency

SourceRow = (
    Request
    | UserProfile
    | FinancialEvent
    | Message
    | Image
    | PaymentOption
    | ExchangeRate
)

PLACEHOLDER_DECISION = {
    "request_id": "request_26",
    "amount_safe_to_pay": 0,
    "affordability_status": "not_affordable",
    "recommended_payment_method": "not_recommended",
    "payment_plan": "none",
    "earliest_date_for_full_payment": "",
    "spending_changes_needed": "none",
    "decision_explanation": "Stub Decision: no payment is recommended yet.",
}


def test_solve_returns_placeholder_decision_for_the_request():
    request = Request(
        request_id="request_26",
        user_id="user_26",
        request_date="2025-08-03",
        request_type="family_transfer",
        requested_amount=15656000,
        desired_completion_date="2025-10-07",
        allows_partial_payment=False,
        request_text="transfer",
    )
    world = World(requests=(request,))

    decision = solve(world, request, ports=None)

    assert asdict(decision) == PLACEHOLDER_DECISION


def test_solve_sandbox_includes_only_the_request_user_evidence(tmp_path: Path):
    request, world = _two_user_world()

    decision = solve(world, request, sandbox_root=tmp_path)

    assert decision.request_id == "request_a"
    assert decision.affordability_status == "not_affordable"
    assert decision.recommended_payment_method == "not_recommended"
    assert decision.payment_plan == "none"
    assert decision.spending_changes_needed == "none"
    _assert_isolated_sandbox(
        tmp_path / "request_a",
        message_ids={"message_unlinked", "message_linked"},
    )


def test_solve_converts_foreign_cash_event_using_settlement_date_rate(
    tmp_path: Path,
):
    request = _request()
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            replace(
                _event("event_foreign", "user_a"),
                amount="10",
                currency=Currency.EUR,
                settlement_date="2025-08-03",
            ),
        ),
        exchange_rates=(
            ExchangeRate("2025-08-03", Currency.EUR, Currency.USD, "2"),
            ExchangeRate("2025-08-04", Currency.EUR, Currency.USD, "9"),
        ),
    )

    decision = solve(world, request, sandbox_root=tmp_path)

    assert decision.request_id == "request_a"
    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["amount"] == "20"
    assert events[0]["currency"] == "USD"


def test_solve_does_not_use_a_rate_off_the_settlement_date(tmp_path: Path):
    request = _request()
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            replace(
                _event("event_foreign", "user_a"),
                amount="10",
                currency=Currency.EUR,
                settlement_date="2025-08-03",
            ),
        ),
        exchange_rates=(
            ExchangeRate("2025-08-02", Currency.EUR, Currency.USD, "5"),
            ExchangeRate("2025-08-04", Currency.EUR, Currency.USD, "9"),
        ),
    )

    solve(world, request, sandbox_root=tmp_path)

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["amount"] == "10"
    assert events[0]["currency"] == "EUR"


def test_solve_does_not_convert_a_non_cash_financial_event(tmp_path: Path):
    request = _request()
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            replace(
                _event("event_valuation", "user_a"),
                event_type="investment_valuation",
                direction="non_cash",
                amount="10",
                currency=Currency.EUR,
                settlement_date="2025-08-03",
                status="unrealized",
            ),
        ),
        exchange_rates=(ExchangeRate("2025-08-03", Currency.EUR, Currency.USD, "2"),),
    )

    solve(world, request, sandbox_root=tmp_path)

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["amount"] == "10"
    assert events[0]["currency"] == "EUR"


def test_solve_does_not_give_ports_or_sandbox_exchange_rates(tmp_path: Path):
    request, world = _two_user_world()
    world = replace(
        world,
        exchange_rates=(ExchangeRate("2025-07-01", Currency.EUR, Currency.USD, "2"),),
    )
    seen: list[object] = []

    def capture(request_slice: object) -> None:
        seen.append(request_slice)

    solve(
        world,
        request,
        ports=Ports(interpret_image=capture, interpret_message=capture),
        sandbox_root=tmp_path,
    )

    sandbox = tmp_path / "request_a"
    assert not (sandbox / "exchange_rates.csv").exists()
    for path in sandbox.glob("*.csv"):
        assert "from_currency" not in path.read_text(encoding="utf-8")
    assert seen
    for request_slice in seen:
        assert not hasattr(request_slice, "exchange_rates")


def test_solve_fills_blank_amount_from_image_interpretation(tmp_path: Path):
    request, world = _blank_amount_world()

    def interpret_image(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(
            action="fill_amount",
            event_id="event_blank",
            amount="1849",
        )

    solve(
        world,
        request,
        ports=Ports(interpret_image=interpret_image),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["event_id"] == "event_blank"
    assert events[0]["amount"] == "1849"


def test_solve_fills_blank_amount_with_zero_only_when_interpretation_says_so(
    tmp_path: Path,
):
    request, world = _blank_amount_world()

    def interpret_image(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(
            action="fill_amount",
            event_id="event_blank",
            amount="0",
        )

    solve(
        world,
        request,
        ports=Ports(interpret_image=interpret_image),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["amount"] == "0"


def test_solve_cancels_existing_event_from_message_interpretation(tmp_path: Path):
    request, world = _message_event_world()

    def interpret_message(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(action="cancel", event_id="event_a")

    solve(
        world,
        request,
        ports=Ports(interpret_message=interpret_message),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["event_id"] == "event_a"
    assert events[0]["status"] == "cancelled"


def test_solve_delays_existing_event_from_message_interpretation(tmp_path: Path):
    request, world = _message_event_world()

    def interpret_message(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(
            action="delay",
            event_id="event_a",
            settlement_date="2025-09-15",
        )

    solve(
        world,
        request,
        ports=Ports(interpret_message=interpret_message),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["settlement_date"] == "2025-09-15"


def test_solve_confirms_existing_event_from_message_interpretation(tmp_path: Path):
    request, world = _message_event_world()
    world = replace(
        world,
        events=(replace(_event("event_a", "user_a"), status="pending"),),
    )

    def interpret_message(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(action="confirm", event_id="event_a")

    solve(
        world,
        request,
        ports=Ports(interpret_message=interpret_message),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["status"] == "settled"


def test_solve_amends_existing_event_from_message_interpretation(tmp_path: Path):
    request, world = _message_event_world()

    def interpret_message(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(
            action="amend",
            event_id="event_a",
            amount="80",
        )

    solve(
        world,
        request,
        ports=Ports(interpret_message=interpret_message),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["amount"] == "80"


def test_solve_rejects_interpretation_that_invents_income_or_a_new_event(
    tmp_path: Path,
):
    request, world = _message_event_world()

    def interpret_message(_request_slice: object) -> tuple[EvidenceInterpretation, ...]:
        return (
            EvidenceInterpretation(
                action="fill_amount",
                event_id="event_bonus",
                amount="5000",
            ),
            EvidenceInterpretation(
                action="create",
                event_id="event_new_expense",
                amount="25",
            ),
        )

    solve(
        world,
        request,
        ports=Ports(interpret_message=interpret_message),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert [event["event_id"] for event in events] == ["event_a"]
    assert events[0]["amount"] == "50"
    assert events[0]["status"] == "settled"


def test_solve_rejects_interpretation_that_overrides_decision_rules(tmp_path: Path):
    request, world = _message_event_world()

    def interpret_message(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(
            action="override_rules",
            event_id="event_a",
            amount="1",
        )

    solve(
        world,
        request,
        ports=Ports(interpret_message=interpret_message),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["amount"] == "50"
    assert events[0]["status"] == "settled"


def test_solve_prefers_explicit_cancel_over_fill_on_the_same_event(tmp_path: Path):
    request, world = _blank_amount_world()
    world = replace(
        world,
        messages=(
            _message("message_a", user_id="user_a", sent_at="2025-08-01T09:00:00Z"),
        ),
    )

    def interpret_image(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(
            action="fill_amount",
            event_id="event_blank",
            amount="1849",
        )

    def interpret_message(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(action="cancel", event_id="event_blank")

    solve(
        world,
        request,
        ports=Ports(
            interpret_image=interpret_image,
            interpret_message=interpret_message,
        ),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["status"] == "cancelled"
    assert events[0]["amount"] == ""


def test_solve_retries_failed_image_interpretation_then_fills_blank_amount(
    tmp_path: Path,
):
    request, world = _blank_amount_world()
    attempts = iter(
        (
            RuntimeError("unusable"),
            EvidenceInterpretation(
                action="fill_amount",
                event_id="event_blank",
                amount="77",
            ),
        )
    )

    def interpret_image(_request_slice: object) -> EvidenceInterpretation:
        outcome = next(attempts)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    solve(
        world,
        request,
        ports=Ports(interpret_image=interpret_image),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["amount"] == "77"


def test_solve_reserves_unknown_debit_after_unusable_image_interpretations(
    tmp_path: Path,
):
    request, world = _blank_amount_world()
    attempts = iter(
        (
            RuntimeError("unusable"),
            RuntimeError("unusable"),
            EvidenceInterpretation(
                action="fill_amount",
                event_id="event_blank",
                amount="99",
            ),
        )
    )

    def interpret_image(_request_slice: object) -> EvidenceInterpretation:
        outcome = next(attempts)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    solve(
        world,
        request,
        ports=Ports(interpret_image=interpret_image),
        sandbox_root=tmp_path,
    )

    events = _read_table(tmp_path / "request_a" / "financial_events.csv")
    assert events[0]["event_id"] == "event_blank"
    assert events[0]["amount"] == ""
    assert events[0]["amount"] != "0"


def test_solve_pays_the_requested_amount_when_the_forecast_stays_above_the_minimum():
    request = _request()
    world = World(requests=(request,), profiles=(_profile("user_a"),))

    decision = solve(world, request)

    assert decision.amount_safe_to_pay == 100
    assert decision.earliest_date_for_full_payment == "2025-08-03"
    assert 0 <= decision.amount_safe_to_pay <= request.requested_amount


def test_solve_reserves_a_pending_debit_before_amount_safe_to_pay():
    request = replace(_request(), requested_amount=400)
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            replace(
                _event("event_pending", "user_a"),
                description="Pending merchant debit",
                category="shopping",
                amount="250",
                event_date="2025-08-04",
                settlement_date="2025-08-04",
                status="pending",
            ),
        ),
    )

    decision = solve(world, request)

    assert decision.amount_safe_to_pay == 150
    assert decision.earliest_date_for_full_payment == ""


def test_solve_projects_a_recurring_commitment_across_the_forecast_horizon():
    request = replace(_request(), requested_amount=400)
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            _monthly_rent("event_r1", "2025-05-01"),
            _monthly_rent("event_r2", "2025-06-01"),
            _monthly_rent("event_r3", "2025-07-01"),
        ),
    )

    decision = solve(world, request)

    assert decision.amount_safe_to_pay == 100
    assert decision.earliest_date_for_full_payment == ""


def test_solve_does_not_treat_two_settled_events_as_a_recurring_commitment():
    request = replace(_request(), requested_amount=400)
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            _monthly_rent("event_r1", "2025-06-01"),
            _monthly_rent("event_r2", "2025-07-01"),
        ),
    )

    decision = solve(world, request)

    assert decision.amount_safe_to_pay == 400
    assert decision.earliest_date_for_full_payment == "2025-08-03"


def test_solve_projects_variable_recurring_amount_as_the_recent_maximum():
    request = replace(_request(), requested_amount=400)
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            _variable_utility("event_u1", "2025-05-06", "80"),
            _variable_utility("event_u2", "2025-06-06", "90"),
            _variable_utility("event_u3", "2025-07-06", "120"),
        ),
    )

    decision = solve(world, request)

    assert decision.amount_safe_to_pay == 40
    assert decision.earliest_date_for_full_payment == ""


def _sample_rows() -> list[dict[str, str]]:
    path = Path(__file__).resolve().parents[1] / "dataset" / "sample_requests.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


_DATASET_WORLD = None


def _dataset_world() -> World:
    global _DATASET_WORLD
    if _DATASET_WORLD is None:
        _DATASET_WORLD = load_world(Path(__file__).resolve().parents[1] / "dataset")
    return _DATASET_WORLD


def _solve_sample(sample_row: dict[str, str]) -> tuple[Request, Decision]:
    world = _dataset_world()
    request = Request(
        request_id=sample_row["request_id"],
        user_id=sample_row["user_id"],
        request_date=sample_row["request_date"],
        request_type=sample_row["request_type"],
        requested_amount=float(sample_row["requested_amount"]),
        desired_completion_date=sample_row["desired_completion_date"],
        allows_partial_payment=sample_row["allows_partial_payment"].strip().lower()
        == "true",
        request_text=sample_row["request_text"],
    )
    return request, solve(world, request, ports=_sample_evidence_ports())


@pytest.mark.parametrize(
    "sample_row",
    _sample_rows(),
    ids=lambda row: row["request_id"],
)
def test_solve_sample_request_amount_safe_is_within_bounds(sample_row: dict[str, str]):
    request, decision = _solve_sample(sample_row)

    assert 0 <= decision.amount_safe_to_pay <= request.requested_amount
    earliest = decision.earliest_date_for_full_payment
    assert earliest == "" or len(earliest) == 10
    if earliest == request.request_date:
        assert decision.amount_safe_to_pay == request.requested_amount
    if decision.amount_safe_to_pay == request.requested_amount:
        assert earliest == request.request_date


@pytest.mark.parametrize(
    "sample_row",
    [
        row
        for row in _sample_rows()
        if row["request_id"] in {"request_01", "request_09", "request_12", "request_16"}
    ],
    ids=lambda row: row["request_id"],
)
def test_solve_sample_request_amount_safe_and_earliest_date(sample_row: dict[str, str]):
    request, decision = _solve_sample(sample_row)

    assert Decimal(str(decision.amount_safe_to_pay)) == Decimal(
        sample_row["amount_safe_to_pay"]
    )
    assert (
        decision.earliest_date_for_full_payment
        == sample_row["earliest_date_for_full_payment"]
    )
    assert 0 <= decision.amount_safe_to_pay <= request.requested_amount


def test_solve_counts_confirmed_salary_on_its_settlement_date():
    request = replace(_request(), requested_amount=400)
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            replace(
                _event("event_salary", "user_a"),
                event_type="income",
                description="Next confirmed salary",
                category="salary",
                direction="credit",
                amount="300",
                event_date="2025-08-15",
                settlement_date="2025-08-15",
                status="scheduled",
            ),
            replace(
                _event("event_pending", "user_a"),
                amount="250",
                event_date="2025-08-04",
                settlement_date="2025-08-04",
                status="pending",
            ),
        ),
    )

    decision = solve(world, request)

    assert decision.amount_safe_to_pay == 150
    assert decision.earliest_date_for_full_payment == "2025-08-15"


def test_solve_ignores_a_pending_credit_when_computing_amount_safe_to_pay():
    request = _request()
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            replace(
                _event("event_bonus", "user_a"),
                event_type="income",
                description="Pending bonus",
                category="salary",
                direction="credit",
                amount="250",
                event_date="2025-08-04",
                settlement_date="2025-08-04",
                status="pending",
            ),
        ),
    )

    decision = solve(world, request)

    assert decision.amount_safe_to_pay == 100
    assert decision.earliest_date_for_full_payment == "2025-08-03"


def test_solve_isolates_a_world_loaded_from_dataset_tables(tmp_path: Path):
    request, world = _two_user_world()
    dataset_dir = tmp_path / "dataset"
    sandbox_root = tmp_path / "sandbox"
    dataset_dir.mkdir()
    _write_csv(dataset_dir / "requests.csv", world.requests)
    _write_csv(dataset_dir / "financial_profiles.csv", world.profiles)
    _write_csv(dataset_dir / "financial_events.csv", world.events)
    _write_csv(dataset_dir / "messages.csv", world.messages)
    _write_csv(dataset_dir / "images.csv", world.images)
    _write_csv(dataset_dir / "request_payment_options.csv", world.payment_options)
    _write_csv(
        dataset_dir / "exchange_rates.csv",
        (ExchangeRate("2025-07-01", Currency.EUR, Currency.USD, "2"),),
    )

    loaded = load_world(dataset_dir)
    loaded_request = next(
        item for item in loaded.requests if item.request_id == request.request_id
    )
    decision = solve(loaded, loaded_request, sandbox_root=sandbox_root)

    assert decision.request_id == "request_a"
    _assert_isolated_sandbox(
        sandbox_root / "request_a",
        message_ids={"message_unlinked", "message_linked"},
    )


_IMAGE_FILLS = {
    "event_253": "4365000",
    "event_1442": "100000",
    "event_1545": "41272",
    "event_1700": "2854",
    "event_1786": "704.05",
}
_SALARY_AMENDS = {
    "user_02": ("Payroll credit", "42750000"),
    "user_06": ("Payroll credit", "1037.52"),
    "user_11": ("Base salary", "38760000"),
}


def _sample_evidence_ports() -> Ports:
    def interpret_image(request_slice: object) -> EvidenceInterpretation | None:
        image = getattr(request_slice, "image", None)
        if image is None:
            return None
        amount = _IMAGE_FILLS.get(image.related_event_id)
        if amount is None:
            return None
        return EvidenceInterpretation("fill_amount", image.related_event_id, amount)

    def interpret_message(request_slice: object) -> list[EvidenceInterpretation]:
        profile = getattr(request_slice, "profile", None)
        events = getattr(request_slice, "events", ())
        if profile is None:
            return []
        found: list[EvidenceInterpretation] = []
        if profile.user_id in _SALARY_AMENDS:
            description, amount = _SALARY_AMENDS[profile.user_id]
            last = next(
                (
                    event
                    for event in reversed(events)
                    if event.description == description and event.direction == "credit"
                ),
                None,
            )
            if last is not None:
                found.append(EvidenceInterpretation("amend", last.event_id, amount))
        if profile.user_id == "user_16":
            last_rent = next(
                (
                    event
                    for event in reversed(events)
                    if event.category == "rent"
                    and event.direction == "debit"
                    and event.status == "settled"
                    and event.amount.strip()
                ),
                None,
            )
            if last_rent is not None:
                increased = Decimal(last_rent.amount) * Decimal("1.12")
                found.append(
                    EvidenceInterpretation(
                        "amend", last_rent.event_id, format(increased, "f")
                    )
                )
        return found

    return Ports(interpret_image=interpret_image, interpret_message=interpret_message)


def _assert_isolated_sandbox(sandbox: Path, *, message_ids: set[str]) -> None:
    profiles = _read_table(sandbox / "financial_profiles.csv")
    events = _read_table(sandbox / "financial_events.csv")
    messages = _read_table(sandbox / "messages.csv")
    images = _read_table(sandbox / "images.csv")
    options = _read_table(sandbox / "request_payment_options.csv")
    assert [row["user_id"] for row in profiles] == ["user_a"]
    assert {row["event_id"] for row in events} == {"event_a"}
    assert {row["user_id"] for row in events} == {"user_a"}
    assert {row["message_id"] for row in messages} == message_ids
    assert {row["user_id"] for row in messages} == {"user_a"}
    assert [row["image_id"] for row in images] == ["image_a"]
    assert [row["user_id"] for row in images] == ["user_a"]
    assert [row["payment_option_id"] for row in options] == ["option_a"]


def _blank_amount_world() -> tuple[Request, World]:
    request = _request()
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(replace(_event("event_blank", "user_a"), amount=""),),
        images=(_image("image_a", "user_a", "request_a"),),
    )
    return request, world


def _message_event_world() -> tuple[Request, World]:
    request = _request()
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(_event("event_a", "user_a"),),
        messages=(
            _message("message_a", user_id="user_a", sent_at="2025-08-01T09:00:00Z"),
        ),
    )
    return request, world


def _two_user_world() -> tuple[Request, World]:
    request = _request()
    other_request = replace(request, request_id="request_b", user_id="user_b")
    world = World(
        requests=(request, other_request),
        profiles=(_profile("user_a"), _profile("user_b")),
        events=(_event("event_a", "user_a"), _event("event_b", "user_b")),
        messages=(
            _message(
                "message_unlinked",
                user_id="user_a",
                request_id="",
                related_event_id="",
                sent_at="2025-08-03T10:00:00Z",
            ),
            _message(
                "message_linked",
                user_id="user_a",
                request_id="request_a",
                sent_at="2025-08-01T09:00:00Z",
            ),
            _message(
                "message_future",
                user_id="user_a",
                sent_at="2025-08-04T00:00:00Z",
            ),
            _message(
                "message_other_user",
                user_id="user_b",
                sent_at="2025-07-01T00:00:00Z",
            ),
        ),
        images=(
            _image("image_a", "user_a", "request_a"),
            _image("image_b", "user_b", "request_b"),
        ),
        payment_options=(
            _option("option_a", "request_a"),
            _option("option_b", "request_b"),
        ),
    )
    return request, world


def _read_table(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: tuple[SourceRow, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def _request() -> Request:
    return Request(
        request_id="request_a",
        user_id="user_a",
        request_date="2025-08-03",
        request_type="purchase",
        requested_amount=100.0,
        desired_completion_date="2025-09-01",
        allows_partial_payment=True,
        request_text="laptop",
    )


def _profile(user_id: str) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        home_currency=Currency.USD,
        current_available_balance=500.0,
        minimum_balance_to_keep=100.0,
        financial_priorities="education",
        expense_categories_to_protect="rent",
        expense_categories_user_is_willing_to_reduce="dining",
        expense_categories_user_is_willing_to_stop="streaming",
        payment_methods_user_will_consider="full_payment",
        max_installment_months="",
    )


def _variable_utility(
    event_id: str, settlement_date: str, amount: str
) -> FinancialEvent:
    return replace(
        _monthly_rent(event_id, settlement_date),
        description="utilities",
        category="utilities",
        amount=amount,
    )


def _monthly_rent(event_id: str, settlement_date: str) -> FinancialEvent:
    return replace(
        _event(event_id, "user_a"),
        description="Monthly rent",
        category="rent",
        amount="100",
        event_date=settlement_date,
        settlement_date=settlement_date,
    )


def _event(event_id: str, user_id: str) -> FinancialEvent:
    return FinancialEvent(
        event_id=event_id,
        user_id=user_id,
        event_type="expense",
        description="rent",
        category="housing",
        direction="debit",
        amount="50",
        currency=Currency.USD,
        event_date="2025-07-01",
        settlement_date="2025-07-01",
        status="settled",
        linked_event_id="",
        flexibility="fixed",
        minimum_allowed_amount="",
    )


def _message(
    message_id: str,
    user_id: str,
    sent_at: str,
    request_id: str = "",
    related_event_id: str = "",
) -> Message:
    return Message(
        message_id=message_id,
        user_id=user_id,
        request_id=request_id,
        related_event_id=related_event_id,
        sent_at=sent_at,
        source_type="employer",
        message_text="note",
    )


def _image(image_id: str, user_id: str, request_id: str) -> Image:
    return Image(
        image_id=image_id,
        user_id=user_id,
        request_id=request_id,
        related_event_id="event_blank",
    )


def _option(payment_option_id: str, request_id: str) -> PaymentOption:
    return PaymentOption(
        payment_option_id=payment_option_id,
        request_id=request_id,
        payment_method="full_payment",
        payment_amount=100.0,
        number_of_payments=1,
        first_payment_date="2025-08-03",
        payment_frequency_days="",
        financing_fee=0.0,
        total_payable_amount=100.0,
    )
