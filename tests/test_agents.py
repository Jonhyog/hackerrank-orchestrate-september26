from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agents import PromptOutcome, UsageLog, sdk_ports
from agents.prompt import cursor_prompt
from evidence import EvidenceInterpretation
from slice import RequestSlice
from solve import solve
from sources import FinancialEvent, Image, Message, Request, UserProfile, World
from utils.currency import Currency

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\xdac\xf8\xff"
    b"\xff?\x03\x00\x01\xfe\xa4\x0e\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_image_port_returns_fill_from_stage_sandbox_only(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "image_a.png").write_bytes(_MIN_PNG)
    sandbox_root = tmp_path / "sandbox"
    usage = UsageLog()
    seen_cwd: list[Path] = []

    def prompt(text: str, cwd: Path) -> PromptOutcome:
        seen_cwd.append(cwd)
        names = {path.name for path in cwd.iterdir()}
        assert names == {"image_a.png", "candidate_event.csv"}
        assert (cwd / "image_a.png").read_bytes() == _MIN_PNG
        event_text = (cwd / "candidate_event.csv").read_text(encoding="utf-8")
        assert "event_blank" in event_text
        assert "event_other" not in event_text
        assert "secret_note" not in event_text
        return PromptOutcome(
            text='{"action":"fill_amount","event_id":"event_blank","amount":"1849"}'
        )

    ports = sdk_ports(
        sandbox_root=sandbox_root,
        media_dir=media_dir,
        usage_log=usage,
        prompt=prompt,
    )
    assert ports.interpret_image is not None
    interpretation = ports.interpret_image(_image_slice())

    assert interpretation == EvidenceInterpretation(
        action="fill_amount",
        event_id="event_blank",
        amount="1849",
    )
    assert seen_cwd
    assert seen_cwd[0] != Path(__file__).resolve().parents[1]
    assert seen_cwd[0].is_relative_to(sandbox_root)


def test_image_port_skips_when_request_has_no_image(tmp_path: Path):
    def prompt(_text: str, _cwd: Path) -> PromptOutcome:
        raise AssertionError("image prompt must not run")

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=tmp_path / "media",
        usage_log=UsageLog(),
        prompt=prompt,
    )
    request_slice = RequestSlice(
        request_id="request_a",
        profile=None,
        events=(_event("event_blank", amount=""),),
        messages=(),
        image=None,
        payment_options=(),
    )

    assert ports.interpret_image is not None
    assert ports.interpret_image(request_slice) is None


def test_image_port_records_token_usage_for_the_sdk_call(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "image_a.png").write_bytes(_MIN_PNG)
    usage = UsageLog()

    def prompt(_text: str, _cwd: Path) -> PromptOutcome:
        return PromptOutcome(
            text='{"action":"fill_amount","event_id":"event_blank","amount":"1849"}',
            input_tokens=21,
            output_tokens=9,
            total_tokens=30,
        )

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=media_dir,
        usage_log=usage,
        prompt=prompt,
        model="composer-2.5",
    )
    assert ports.interpret_image is not None
    ports.interpret_image(_image_slice())

    assert len(usage.records) == 1
    record = usage.records[0]
    assert record.stage == "image"
    assert record.request_id == "request_a"
    assert record.model == "composer-2.5"
    assert record.input_tokens == 21
    assert record.output_tokens == 9
    assert record.total_tokens == 30


def test_message_port_returns_cancel_from_stage_sandbox_only(tmp_path: Path):
    seen_cwd: list[Path] = []

    def prompt(_text: str, cwd: Path) -> PromptOutcome:
        seen_cwd.append(cwd)
        names = {path.name for path in cwd.iterdir()}
        assert names == {"messages.csv", "candidate_events.csv"}
        messages_text = (cwd / "messages.csv").read_text(encoding="utf-8")
        events_text = (cwd / "candidate_events.csv").read_text(encoding="utf-8")
        assert "message_a" in messages_text
        assert "Landlord cancelled the charge." in messages_text
        assert "event_a" in events_text
        header = "event_id,event_date,settlement_date,amount,description,status"
        assert header in events_text
        assert "image_a" not in messages_text
        assert "image_a.png" not in names
        return PromptOutcome(
            text='[{"action":"cancel","event_id":"event_a"}]'
        )

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=tmp_path / "media",
        usage_log=UsageLog(),
        prompt=prompt,
    )
    assert ports.interpret_message is not None
    interpretations = ports.interpret_message(_message_slice())

    assert interpretations == (
        EvidenceInterpretation(action="cancel", event_id="event_a"),
    )
    assert seen_cwd
    assert seen_cwd[0] != Path(__file__).resolve().parents[1]
    assert seen_cwd[0].is_relative_to(tmp_path / "sandbox")
    assert (seen_cwd[0] / "image").exists() is False


def test_message_port_skips_when_user_has_no_in_scope_messages(tmp_path: Path):
    def prompt(_text: str, _cwd: Path) -> PromptOutcome:
        raise AssertionError("message prompt must not run")

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=tmp_path / "media",
        usage_log=UsageLog(),
        prompt=prompt,
    )
    request_slice = RequestSlice(
        request_id="request_a",
        profile=None,
        events=(_event("event_a", amount="50"),),
        messages=(),
        image=None,
        payment_options=(),
    )

    assert ports.interpret_message is not None
    assert ports.interpret_message(request_slice) is None


def test_image_and_message_ports_use_separate_sandboxes(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "image_a.png").write_bytes(_MIN_PNG)
    seen_cwd: list[Path] = []

    def prompt(text: str, cwd: Path) -> PromptOutcome:
        seen_cwd.append(cwd)
        if "candidate_event.csv" in {path.name for path in cwd.iterdir()}:
            return PromptOutcome(
                text='{"action":"fill_amount","event_id":"event_blank","amount":"1849"}'
            )
        return PromptOutcome(text='[{"action":"cancel","event_id":"event_a"}]')

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=media_dir,
        usage_log=UsageLog(),
        prompt=prompt,
    )
    request_slice = RequestSlice(
        request_id="request_a",
        profile=None,
        events=(
            _event("event_blank", amount=""),
            _event("event_a", amount="50"),
        ),
        messages=_message_slice().messages,
        image=Image("image_a", "user_a", "request_a", "event_blank"),
        payment_options=(),
    )
    assert ports.interpret_image is not None
    assert ports.interpret_message is not None
    ports.interpret_image(request_slice)
    ports.interpret_message(request_slice)

    assert len(seen_cwd) == 2
    assert seen_cwd[0] != seen_cwd[1]
    assert {path.name for path in seen_cwd} == {"image", "message"}
    repo_root = Path(__file__).resolve().parents[1]
    sandbox = tmp_path / "sandbox"
    assert all(cwd != repo_root and cwd.is_relative_to(sandbox) for cwd in seen_cwd)


def test_solve_applies_sdk_image_port_through_the_apply_gate(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "image_a.png").write_bytes(_MIN_PNG)

    def prompt(_text: str, _cwd: Path) -> PromptOutcome:
        return PromptOutcome(
            text='{"action":"fill_amount","event_id":"event_blank","amount":"1849"}'
        )

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=media_dir,
        usage_log=UsageLog(),
        prompt=prompt,
    )
    request = Request(
        request_id="request_a",
        user_id="user_a",
        request_date="2025-08-03",
        request_type="purchase",
        requested_amount=100.0,
        desired_completion_date="2025-09-01",
        allows_partial_payment=True,
        request_text="laptop",
    )
    world = World(
        requests=(request,),
        profiles=(
            UserProfile(
                user_id="user_a",
                home_currency=Currency.USD,
                current_available_balance=500.0,
                minimum_balance_to_keep=100.0,
                financial_priorities="education",
                expense_categories_to_protect="rent",
                expense_categories_user_is_willing_to_reduce="dining",
                expense_categories_user_is_willing_to_stop="streaming",
                payment_methods_user_will_consider="full_payment",
                max_installment_months="",
            ),
        ),
        events=(_event("event_blank", amount=""),),
        images=(Image("image_a", "user_a", "request_a", "event_blank"),),
    )

    decision = solve(world, request, ports=ports, sandbox_root=tmp_path / "ledger")

    assert decision.request_id == "request_a"
    ledger = tmp_path / "ledger" / "request_a" / "financial_events.csv"
    events_text = ledger.read_text(encoding="utf-8")
    assert "1849" in events_text


def test_solve_rejects_invented_event_from_sdk_message_port(tmp_path: Path):
    def prompt(_text: str, _cwd: Path) -> PromptOutcome:
        return PromptOutcome(
            text='[{"action":"create","event_id":"event_new","amount":"25"}]'
        )

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=tmp_path / "media",
        usage_log=UsageLog(),
        prompt=prompt,
    )
    request = Request(
        request_id="request_a",
        user_id="user_a",
        request_date="2025-08-03",
        request_type="purchase",
        requested_amount=100.0,
        desired_completion_date="2025-09-01",
        allows_partial_payment=True,
        request_text="laptop",
    )
    world = World(
        requests=(request,),
        profiles=(
            UserProfile(
                user_id="user_a",
                home_currency=Currency.USD,
                current_available_balance=500.0,
                minimum_balance_to_keep=100.0,
                financial_priorities="education",
                expense_categories_to_protect="rent",
                expense_categories_user_is_willing_to_reduce="dining",
                expense_categories_user_is_willing_to_stop="streaming",
                payment_methods_user_will_consider="full_payment",
                max_installment_months="",
            ),
        ),
        events=(_event("event_a", amount="50"),),
        messages=_message_slice().messages,
    )

    decision = solve(world, request, ports=ports, sandbox_root=tmp_path / "ledger")

    assert decision.request_id == "request_a"
    ledger = tmp_path / "ledger" / "request_a" / "financial_events.csv"
    events_text = ledger.read_text(encoding="utf-8")
    assert "event_new" not in events_text
    assert "event_a" in events_text


def test_image_port_skips_when_png_is_absent(tmp_path: Path):
    def prompt(_text: str, _cwd: Path) -> PromptOutcome:
        raise AssertionError("image prompt must not invent an amount")

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=tmp_path / "media",
        usage_log=UsageLog(),
        prompt=prompt,
    )
    assert ports.interpret_image is not None
    assert ports.interpret_image(_image_slice()) is None


def test_image_port_parses_fenced_json(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "image_a.png").write_bytes(_MIN_PNG)

    def prompt(_text: str, _cwd: Path) -> PromptOutcome:
        return PromptOutcome(
            text=(
                "Here is the extraction:\n"
                "```json\n"
                '{"action":"fill_amount","event_id":"event_blank","amount":"1849"}\n'
                "```\n"
            )
        )

    ports = sdk_ports(
        sandbox_root=tmp_path / "sandbox",
        media_dir=media_dir,
        usage_log=UsageLog(),
        prompt=prompt,
    )
    assert ports.interpret_image is not None
    assert ports.interpret_image(_image_slice()) == EvidenceInterpretation(
        action="fill_amount",
        event_id="event_blank",
        amount="1849",
    )


def test_cursor_prompt_uses_one_shot_local_agent_on_stage_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cwd = tmp_path / "request_a" / "image"
    cwd.mkdir(parents=True)
    (cwd / "image_a.png").write_bytes(_MIN_PNG)
    captured: dict[str, object] = {}

    def fake_prompt(message: object, options: Any) -> object:
        captured["message"] = message
        captured["cwd"] = options.local.cwd
        captured["api_key"] = options.api_key
        captured["model"] = options.model
        return SimpleNamespace(
            status="finished",
            result='{"action":"fill_amount","event_id":"event_blank","amount":"1849"}',
            usage=SimpleNamespace(input_tokens=12, output_tokens=4, total_tokens=16),
        )

    monkeypatch.setattr("agents.prompt.Agent.prompt", fake_prompt)

    outcome = cursor_prompt(
        "extract",
        cwd,
        api_key="test-key",
        model="composer-2.5",
    )

    assert outcome.text.startswith("{")
    assert outcome.input_tokens == 12
    assert outcome.output_tokens == 4
    assert outcome.total_tokens == 16
    assert captured["cwd"] == str(cwd)
    assert captured["cwd"] != str(Path(__file__).resolve().parents[1])
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "composer-2.5"
    assert getattr(captured["message"], "images", None)


def _image_slice() -> RequestSlice:
    return RequestSlice(
        request_id="request_a",
        profile=None,
        events=(
            _event("event_blank", amount=""),
            _event("event_other", amount="50"),
        ),
        messages=(_message("secret_note"),),
        image=Image("image_a", "user_a", "request_a", "event_blank"),
        payment_options=(),
    )


def _event(event_id: str, amount: str) -> FinancialEvent:
    return FinancialEvent(
        event_id=event_id,
        user_id="user_a",
        event_type="expense",
        description="rent",
        category="housing",
        direction="debit",
        amount=amount,
        currency=Currency.USD,
        event_date="2025-07-01",
        settlement_date="2025-07-01",
        status="settled",
        linked_event_id="",
        flexibility="fixed",
        minimum_allowed_amount="",
    )


def _message_slice() -> RequestSlice:
    return RequestSlice(
        request_id="request_a",
        profile=None,
        events=(_event("event_a", amount="50"),),
        messages=(
            Message(
                message_id="message_a",
                user_id="user_a",
                request_id="request_a",
                related_event_id="event_a",
                sent_at="2025-08-01T09:00:00Z",
                source_type="landlord",
                message_text="Landlord cancelled the charge.",
            ),
        ),
        image=Image("image_a", "user_a", "request_a", "event_blank"),
        payment_options=(),
    )


def _message(message_id: str) -> Message:
    return Message(
        message_id=message_id,
        user_id="user_a",
        request_id="request_a",
        related_event_id="",
        sent_at="2025-08-01T09:00:00Z",
        source_type="employer",
        message_text="note",
    )

