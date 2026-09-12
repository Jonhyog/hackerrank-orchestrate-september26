import csv
from dataclasses import asdict, replace
from datetime import date, timedelta
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
from writer import write_output

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


def test_solve_uses_explanation_text_and_keeps_engine_decision_fields():
    request = _request()
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        payment_options=(_option("option_a", "request_a"),),
    )

    def explain(_dossier: object) -> str:
        return "Pay USD 100 today from the Request Dossier."

    decision = solve(world, request, ports=Ports(explain=explain))

    assert decision.request_id == "request_a"
    assert decision.amount_safe_to_pay == 100
    assert decision.affordability_status == "affordable_now"
    assert decision.recommended_payment_method == "full_payment"
    assert decision.payment_plan == "2025-08-03:100"
    assert decision.earliest_date_for_full_payment == "2025-08-03"
    assert decision.spending_changes_needed == "none"
    assert decision.decision_explanation == (
        "Pay USD 100 today from the Request Dossier."
    )


def test_solve_discards_extra_numeric_fields_from_the_explanation_agent():
    request = _request()
    world = World(requests=(request,), profiles=(_profile("user_a"),))

    def explain(_dossier: object) -> dict[str, object]:
        return {
            "decision_explanation": "Pay USD 100 today.",
            "amount_safe_to_pay": 999,
            "affordability_status": "not_affordable",
            "recommended_payment_method": "not_recommended",
            "payment_plan": "none",
            "earliest_date_for_full_payment": "",
            "spending_changes_needed": "stop:event_fake",
        }

    decision = solve(world, request, ports=Ports(explain=explain))

    assert decision.amount_safe_to_pay == 100
    assert decision.affordability_status == "affordable_now"
    assert decision.recommended_payment_method == "full_payment"
    assert decision.payment_plan == "2025-08-03:100"
    assert decision.earliest_date_for_full_payment == "2025-08-03"
    assert decision.spending_changes_needed == "none"
    assert decision.decision_explanation == "Pay USD 100 today."


def test_solve_explanation_port_receives_the_request_dossier_not_the_ledger():
    request = _request()
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(_event("event_a", "user_a"),),
        payment_options=(_option("option_a", "request_a"),),
        exchange_rates=(ExchangeRate("2025-08-03", Currency.EUR, Currency.USD, "2"),),
        messages=(
            _message("message_a", user_id="user_a", sent_at="2025-08-01T09:00:00Z"),
        ),
    )
    seen: list[object] = []

    def explain(dossier: object) -> str:
        seen.append(dossier)
        return "Grounded in the Request Dossier."

    def interpret_message(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(action="cancel", event_id="event_a")

    decision = solve(
        world,
        request,
        ports=Ports(interpret_message=interpret_message, explain=explain),
    )

    assert decision.decision_explanation == "Grounded in the Request Dossier."
    assert len(seen) == 1
    dossier = seen[0]
    assert getattr(dossier, "request").request_id == "request_a"
    assert getattr(dossier, "decision").amount_safe_to_pay == 100
    assert getattr(dossier, "decision").affordability_status == "affordable_now"
    forecast = getattr(dossier, "forecast")
    assert forecast.request_date == "2025-08-03"
    assert forecast.horizon_end == "2025-11-01"
    assert forecast.home_currency == "USD"
    assert forecast.minimum_balance_to_keep == "100"
    options = getattr(dossier, "payment_options")
    assert [option.payment_option_id for option in options] == ["option_a"]
    facts = getattr(dossier, "evidence_facts")
    assert [(fact.action, fact.event_id) for fact in facts] == [("cancel", "event_a")]
    assert not hasattr(dossier, "events")
    assert not hasattr(dossier, "exchange_rates")
    assert not hasattr(dossier, "profile")


def test_solve_discards_numeric_fields_in_explanation_json_text(tmp_path: Path):
    request = _request()
    world = World(requests=(request,), profiles=(_profile("user_a"),))

    def explain(_dossier: object) -> str:
        return '{"decision_explanation":"Pay USD 100 today.","amount_safe_to_pay":999}'

    decision = solve(world, request, ports=Ports(explain=explain))
    dest = tmp_path / "output.csv"
    write_output([decision], dest)
    rows = _read_table(dest)

    assert list(rows[0].keys()) == [
        "request_id",
        "amount_safe_to_pay",
        "affordability_status",
        "recommended_payment_method",
        "payment_plan",
        "earliest_date_for_full_payment",
        "spending_changes_needed",
        "decision_explanation",
    ]
    assert float(rows[0]["amount_safe_to_pay"]) == 100
    assert rows[0]["affordability_status"] == "affordable_now"
    assert rows[0]["decision_explanation"] == "Pay USD 100 today."
    assert "999" not in rows[0].values()


def test_solve_runs_explanation_for_a_request_with_no_evidence():
    request = _request()
    world = World(requests=(request,), profiles=(_profile("user_a"),))

    def explain(_dossier: object) -> str:
        return "No Evidence; the Decision still needs an Explanation."

    decision = solve(world, request, ports=Ports(explain=explain))

    assert decision.decision_explanation == (
        "No Evidence; the Decision still needs an Explanation."
    )


def test_solve_dossier_omits_rejected_evidence_interpretations():
    request, world = _message_event_world()
    seen: list[object] = []

    def interpret_message(_request_slice: object) -> EvidenceInterpretation:
        return EvidenceInterpretation(
            action="create", event_id="event_new", amount="25"
        )

    def explain(dossier: object) -> str:
        seen.append(dossier)
        return "Rejected invented income."

    solve(
        world,
        request,
        ports=Ports(interpret_message=interpret_message, explain=explain),
    )

    facts = getattr(seen[0], "evidence_facts")
    assert facts == ()
    assert all(getattr(fact, "event_id", "") != "event_new" for fact in facts)


def test_solve_sandbox_includes_only_the_request_user_evidence(tmp_path: Path):
    request, world = _two_user_world()

    decision = solve(world, request, sandbox_root=tmp_path)

    assert decision.request_id == "request_a"
    assert decision.affordability_status == "affordable_now"
    assert decision.recommended_payment_method == "full_payment"
    assert decision.payment_plan == "2025-08-03:100"
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


def test_solve_recommends_full_payment_when_the_amount_is_safe_today():
    request = _request()
    world = World(requests=(request,), profiles=(_profile("user_a"),))

    decision = solve(world, request)

    assert decision.affordability_status == "affordable_now"
    assert decision.recommended_payment_method == "full_payment"
    assert decision.payment_plan == "2025-08-03:100"
    assert decision.spending_changes_needed == "none"


def test_solve_does_not_recommend_full_payment_when_the_user_will_not_consider_it():
    request = _request()
    world = World(
        requests=(request,),
        profiles=(
            replace(
                _profile("user_a"),
                payment_methods_user_will_consider="installments",
            ),
        ),
    )

    decision = solve(world, request)

    assert decision.recommended_payment_method != "full_payment"
    assert decision.affordability_status != "affordable_now"


def test_solve_recommends_wait_when_full_payment_becomes_safe_later():
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

    assert decision.affordability_status == "affordable_later"
    assert decision.recommended_payment_method == "wait"
    assert decision.payment_plan == "2025-08-15:400"
    assert decision.spending_changes_needed == "none"


def test_solve_recommends_partial_payment_as_two_payments_summing_to_the_request():
    request = replace(_request(), requested_amount=400)
    world = World(
        requests=(request,),
        profiles=(
            replace(
                _profile("user_a"),
                payment_methods_user_will_consider="partial_payment",
            ),
        ),
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

    assert decision.affordability_status == "affordable_with_plan"
    assert decision.recommended_payment_method == "partial_payment"
    assert decision.payment_plan == "2025-08-03:150|2025-08-15:250"
    assert decision.amount_safe_to_pay == 150
    assert decision.earliest_date_for_full_payment == "2025-08-15"
    assert decision.spending_changes_needed == "none"


def test_solve_rejects_partial_payment_when_the_remainder_is_after_the_deadline():
    request = replace(
        _request(), requested_amount=400, desired_completion_date="2025-08-10"
    )
    world = World(
        requests=(request,),
        profiles=(
            replace(
                _profile("user_a"),
                payment_methods_user_will_consider="partial_payment",
            ),
        ),
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

    assert decision.recommended_payment_method != "partial_payment"
    assert decision.payment_plan == "none"
    assert decision.affordability_status == "not_affordable"


def test_solve_recommends_installments_that_match_a_supplied_payment_option():
    request = replace(
        _request(), requested_amount=400, desired_completion_date="2025-10-15"
    )
    option = PaymentOption(
        payment_option_id="option_installments",
        request_id="request_a",
        payment_method="installments",
        payment_amount=150.0,
        number_of_payments=3,
        first_payment_date="2025-08-20",
        payment_frequency_days="28",
        financing_fee=50.0,
        total_payable_amount=450.0,
    )
    world = World(
        requests=(request,),
        profiles=(
            replace(
                _profile("user_a"),
                payment_methods_user_will_consider="installments",
                max_installment_months="6",
            ),
        ),
        events=_later_salary_world_events(),
        payment_options=(option,),
    )

    decision = solve(world, request)

    assert decision.affordability_status == "affordable_with_plan"
    assert decision.recommended_payment_method == "installments"
    assert decision.payment_plan == "2025-08-20:150|2025-09-17:150|2025-10-15:150"
    assert decision.spending_changes_needed == "none"


def test_solve_rejects_installment_options_beyond_max_installment_months():
    request = replace(
        _request(), requested_amount=400, desired_completion_date="2025-10-15"
    )
    option = PaymentOption(
        payment_option_id="option_long",
        request_id="request_a",
        payment_method="installments",
        payment_amount=150.0,
        number_of_payments=18,
        first_payment_date="2025-08-20",
        payment_frequency_days="28",
        financing_fee=50.0,
        total_payable_amount=2700.0,
    )
    world = World(
        requests=(request,),
        profiles=(
            replace(
                _profile("user_a"),
                payment_methods_user_will_consider="installments",
                max_installment_months="6",
            ),
        ),
        events=_later_salary_world_events(),
        payment_options=(option,),
    )

    decision = solve(world, request)

    assert decision.recommended_payment_method == "not_recommended"
    assert decision.payment_plan == "none"


def test_solve_ranks_safe_installment_options_by_lower_total_paid():
    request = replace(
        _request(), requested_amount=400, desired_completion_date="2025-10-15"
    )
    cheap = PaymentOption(
        payment_option_id="option_b",
        request_id="request_a",
        payment_method="installments",
        payment_amount=150.0,
        number_of_payments=3,
        first_payment_date="2025-08-20",
        payment_frequency_days="28",
        financing_fee=50.0,
        total_payable_amount=450.0,
    )
    costly = PaymentOption(
        payment_option_id="option_a",
        request_id="request_a",
        payment_method="installments",
        payment_amount=220.0,
        number_of_payments=2,
        first_payment_date="2025-08-10",
        payment_frequency_days="28",
        financing_fee=40.0,
        total_payable_amount=480.0,
    )
    world = World(
        requests=(request,),
        profiles=(
            replace(
                _profile("user_a"),
                payment_methods_user_will_consider="installments",
                max_installment_months="6",
            ),
        ),
        events=_later_salary_world_events(),
        payment_options=(costly, cheap),
    )

    decision = solve(world, request)

    assert decision.recommended_payment_method == "installments"
    assert decision.payment_plan == "2025-08-20:150|2025-09-17:150|2025-10-15:150"


def test_solve_uses_a_stop_spending_change_only_when_needed_for_a_safe_plan():
    request = replace(_request(), requested_amount=350)
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            _monthly_streaming("event_s1", "2025-05-01"),
            _monthly_streaming("event_s2", "2025-06-01"),
            _monthly_streaming("event_s3", "2025-07-01"),
        ),
    )

    decision = solve(world, request)

    assert decision.amount_safe_to_pay == 250
    assert decision.affordability_status == "affordable_with_plan"
    assert decision.recommended_payment_method == "full_payment"
    assert decision.payment_plan == "2025-08-03:350"
    assert decision.spending_changes_needed == "stop:event_s3"


def test_solve_uses_a_reduce_spending_change_on_a_flexible_non_protected_event():
    request = replace(_request(), requested_amount=250)
    world = World(
        requests=(request,),
        profiles=(_profile("user_a"),),
        events=(
            _monthly_dining("event_d1", "2025-05-01"),
            _monthly_dining("event_d2", "2025-06-01"),
            _monthly_dining("event_d3", "2025-07-01"),
        ),
    )

    decision = solve(world, request)

    assert decision.affordability_status == "affordable_with_plan"
    assert decision.recommended_payment_method == "full_payment"
    assert decision.payment_plan == "2025-08-03:250"
    assert decision.spending_changes_needed == "reduce_to:event_d3:40"


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


@pytest.mark.parametrize(
    "sample_row",
    _sample_rows(),
    ids=lambda row: row["request_id"],
)
def test_solve_sample_request_decision_invariants(sample_row: dict[str, str]):
    request, decision = _solve_sample(sample_row)
    profile = next(
        item for item in _dataset_world().profiles if item.user_id == request.user_id
    )
    options = [
        item
        for item in _dataset_world().payment_options
        if item.request_id == request.request_id
    ]
    considered = {
        part for part in profile.payment_methods_user_will_consider.split("|") if part
    }
    method = decision.recommended_payment_method
    if method in {"full_payment", "partial_payment", "installments"}:
        assert method in considered
    if method == "wait":
        assert "full_payment" in considered
        assert decision.earliest_date_for_full_payment > request.request_date
        assert decision.affordability_status == "affordable_later"
    if method == "full_payment" and decision.spending_changes_needed == "none":
        if decision.earliest_date_for_full_payment == request.request_date:
            assert decision.affordability_status == "affordable_now"
        else:
            assert decision.affordability_status == "affordable_with_plan"
    if method == "partial_payment":
        assert request.allows_partial_payment
        assert decision.affordability_status == "affordable_with_plan"
        assert 0 < decision.amount_safe_to_pay < request.requested_amount
        assert (
            decision.earliest_date_for_full_payment <= request.desired_completion_date
        )
        first, second = decision.payment_plan.split("|")
        assert first == _plan_entry(
            request.request_date, Decimal(str(decision.amount_safe_to_pay))
        )
        remainder = Decimal(str(request.requested_amount)) - Decimal(
            str(decision.amount_safe_to_pay)
        )
        assert second == _plan_entry(decision.earliest_date_for_full_payment, remainder)
    if method == "installments":
        assert decision.affordability_status == "affordable_with_plan"
        max_months = profile.max_installment_months.strip()
        assert max_months
        assert any(
            _installment_plan(option) == decision.payment_plan
            and option.number_of_payments <= int(max_months)
            for option in options
            if option.payment_method == "installments"
        )
    if method == "not_recommended":
        assert decision.affordability_status == "not_affordable"
        assert decision.payment_plan == "none"
    _assert_spending_changes(decision.spending_changes_needed, profile, request)


@pytest.mark.parametrize(
    "sample_row",
    [
        row
        for row in _sample_rows()
        if row["request_id"]
        in {
            "request_01",
            "request_02",
            "request_05",
            "request_07",
            "request_09",
            "request_10",
            "request_12",
            "request_14",
            "request_15",
            "request_16",
            "request_17",
            "request_20",
            "request_22",
            "request_24",
        }
    ],
    ids=lambda row: row["request_id"],
)
def test_solve_sample_request_ranked_decision(sample_row: dict[str, str]):
    _request, decision = _solve_sample(sample_row)

    assert decision.affordability_status == sample_row["affordability_status"]
    assert (
        decision.recommended_payment_method == sample_row["recommended_payment_method"]
    )
    assert decision.payment_plan == sample_row["payment_plan"]
    assert decision.spending_changes_needed == sample_row["spending_changes_needed"]


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


def _plan_entry(day: str, amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    if quantized == quantized.to_integral():
        text = str(int(quantized))
    else:
        text = f"{quantized:.2f}"
    return f"{day}:{text}"


def _installment_plan(option: PaymentOption) -> str:
    first = date.fromisoformat(option.first_payment_date)
    step = int(option.payment_frequency_days)
    amount = Decimal(str(option.payment_amount))
    return "|".join(
        _plan_entry((first + timedelta(days=index * step)).isoformat(), amount)
        for index in range(option.number_of_payments)
    )


def _assert_spending_changes(raw: str, profile: UserProfile, request: Request) -> None:
    if raw == "none":
        return
    parts = raw.split("|")
    assert 1 <= len(parts) <= 3
    seen: set[str] = set()
    protected = {
        part for part in profile.expense_categories_to_protect.split("|") if part
    }
    can_stop = {
        part
        for part in profile.expense_categories_user_is_willing_to_stop.split("|")
        if part
    }
    can_reduce = {
        part
        for part in profile.expense_categories_user_is_willing_to_reduce.split("|")
        if part
    }
    events = {
        event.event_id: event
        for event in _dataset_world().events
        if event.user_id == request.user_id
    }
    for part in parts:
        if part.startswith("stop:"):
            event_id = part.split(":", 1)[1]
            assert event_id not in seen
            seen.add(event_id)
            event = events[event_id]
            assert event.category not in protected
            assert event.category in can_stop
            assert event.flexibility in {"stoppable", "reducible_or_stoppable"}
        elif part.startswith("reduce_to:"):
            _kind, event_id, _amount = part.split(":", 2)
            assert event_id not in seen
            seen.add(event_id)
            event = events[event_id]
            assert event.category not in protected
            assert event.category in can_reduce
            assert event.flexibility in {"reducible", "reducible_or_stoppable"}
        else:
            raise AssertionError(part)


def _later_salary_world_events() -> tuple[FinancialEvent, ...]:
    return (
        replace(
            _event("event_salary", "user_a"),
            event_type="income",
            description="Next confirmed salary",
            category="salary",
            direction="credit",
            amount="300",
            event_date="2025-09-15",
            settlement_date="2025-09-15",
            status="scheduled",
        ),
        replace(
            _event("event_pending", "user_a"),
            amount="200",
            event_date="2025-08-04",
            settlement_date="2025-08-04",
            status="pending",
        ),
    )


def _monthly_dining(event_id: str, settlement_date: str) -> FinancialEvent:
    return replace(
        _event(event_id, "user_a"),
        description="Weekend food delivery",
        category="dining",
        amount="80",
        event_date=settlement_date,
        settlement_date=settlement_date,
        flexibility="reducible",
        minimum_allowed_amount="40",
    )


def _monthly_streaming(event_id: str, settlement_date: str) -> FinancialEvent:
    return replace(
        _event(event_id, "user_a"),
        description="Family streaming plan",
        category="streaming",
        amount="50",
        event_date=settlement_date,
        settlement_date=settlement_date,
        flexibility="stoppable",
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
