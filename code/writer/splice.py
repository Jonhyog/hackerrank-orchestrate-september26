import json
from dataclasses import replace
from typing import Any

_EXPLANATION_KEYS = ("decision_explanation",)


def splice(engine: Any, payload: object) -> Any:
    return replace(engine, decision_explanation=explanation_text(payload))


def explanation_text(payload: object) -> str:
    if payload is None:
        return ""
    if isinstance(payload, dict):
        return _from_mapping(payload)
    if isinstance(payload, str):
        parsed = _parse_object(payload)
        if parsed is not None:
            return _from_mapping(parsed)
        return payload
    return str(payload)


def _from_mapping(payload: dict[str, Any]) -> str:
    for key in _EXPLANATION_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _parse_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if "```" in stripped:
        block = stripped.split("```", 2)[1]
        if block.startswith("json"):
            block = block[4:]
        stripped = block.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
