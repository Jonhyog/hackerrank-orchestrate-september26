from pathlib import Path

from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, SDKImage, UserMessage

from agents.ports import PromptOutcome


def cursor_prompt(
    text: str,
    cwd: Path,
    *,
    api_key: str,
    model: str,
) -> PromptOutcome:
    pngs = sorted(cwd.glob("*.png"))
    message: str | UserMessage = text
    if pngs:
        message = UserMessage(text=text, images=[SDKImage.from_file(str(pngs[0]))])
    result = Agent.prompt(
        message,
        AgentOptions(
            api_key=api_key,
            model=model or "composer-2.5",
            local=LocalAgentOptions(cwd=str(cwd)),
        ),
    )
    if getattr(result, "status", "finished") == "error":
        raise RuntimeError("evidence agent run failed")
    usage = getattr(result, "usage", None)
    return PromptOutcome(
        text=str(getattr(result, "result", "") or ""),
        input_tokens=_usage_field(usage, "input_tokens"),
        output_tokens=_usage_field(usage, "output_tokens"),
        total_tokens=_usage_field(usage, "total_tokens"),
    )


def _usage_field(usage: object | None, name: str) -> int:
    if usage is None:
        return 0
    value = getattr(usage, name, 0)
    return int(value or 0)
