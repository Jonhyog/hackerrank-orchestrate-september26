import csv
from dataclasses import asdict, replace
from pathlib import Path

from solve import Ports, solve
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

    assert asdict(decision) == {**PLACEHOLDER_DECISION, "request_id": "request_a"}
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
