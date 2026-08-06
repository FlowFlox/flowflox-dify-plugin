"""Shared input and output contract for FlowFlox API action tools."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


class FlowFloxActionInputError(ValueError):
    """Raised when a workflow action receives an invalid input object."""


def parse_action_arguments(value: Any) -> dict[str, Any]:
    """Accept Dify object bindings as well as a JSON string from an Agent."""
    if value is None or value == "":
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        raise FlowFloxActionInputError("FlowFlox API input must be a JSON object.")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise FlowFloxActionInputError("FlowFlox API input must be valid JSON.") from error
    if not isinstance(parsed, dict):
        raise FlowFloxActionInputError("FlowFlox API input must be a JSON object.")
    return parsed


def _content_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, Mapping) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(part for part in parts if part).strip()


def _json_from_text(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def action_result(
    operation: str,
    result: Mapping[str, Any],
    *,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Return one stable envelope that downstream Dify nodes can bind to."""
    content = result.get("content")
    text = _content_text(content)
    structured_content = result.get("structuredContent")
    data = structured_content if structured_content is not None else _json_from_text(text)
    failed = bool(result.get("isError"))
    error = text if failed else None
    if failed and not error:
        error = "The FlowFlox action could not complete."

    return {
        "ok": not failed,
        "operation": operation,
        "action": {
            "name": operation,
            "title": title or operation,
            "description": description or "",
        },
        "data": data,
        "text": text,
        "error": error,
    }


def action_failure(operation: str, message: str) -> dict[str, Any]:
    """Keep expected action failures inside the same downstream contract."""
    return {
        "ok": False,
        "operation": operation,
        "action": {
            "name": operation,
            "title": operation or "FlowFlox API action",
            "description": "",
        },
        "data": None,
        "text": "",
        "error": message,
    }
