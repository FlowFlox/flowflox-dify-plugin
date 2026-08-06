"""Minimal FlowFlox MCP client used by the FlowFlox Tools Dify plugin."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import requests


MCP_SERVER_URL = "https://gateway.flowflox.dev/v1/mcp"
REQUEST_TIMEOUT_SECONDS = 20


class FlowFloxMcpError(ValueError):
    """A safe error suitable for the Dify provider and tool UI."""


def _service_key(credentials: Mapping[str, Any]) -> str:
    key = str(credentials.get("flowflox_service_key") or "").strip()
    if not key:
        raise FlowFloxMcpError("A FlowFlox signed key is required.")
    if not key.startswith("ffx_svc_"):
        raise FlowFloxMcpError("The FlowFlox signed key is not valid.")
    return key


def _rpc(credentials: Mapping[str, Any], method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        response = requests.post(
            MCP_SERVER_URL,
            headers={
                "Authorization": f"Bearer {_service_key(credentials)}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": method,
                "params": dict(params or {}),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise FlowFloxMcpError("FlowFlox API tools could not be reached.") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise FlowFloxMcpError("FlowFlox API tools returned an invalid response.") from error

    if response.status_code in (401, 403):
        raise FlowFloxMcpError("The FlowFlox signed key was not accepted.")
    if not response.ok or not isinstance(payload, dict):
        raise FlowFloxMcpError("FlowFlox API tools are unavailable.")
    if isinstance(payload.get("error"), dict):
        raise FlowFloxMcpError("This FlowFlox API request was not allowed.")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise FlowFloxMcpError("FlowFlox API tools returned an invalid result.")
    return result


def list_authorized_tools(credentials: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = _rpc(credentials, "tools/list")
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise FlowFloxMcpError("FlowFlox did not return an API list.")
    return [tool for tool in tools if isinstance(tool, dict) and isinstance(tool.get("name"), str)]


def get_authorized_tool(credentials: Mapping[str, Any], operation: str) -> dict[str, Any]:
    """Return one currently granted operation without trusting client metadata."""
    requested_operation = str(operation or "").strip()
    if not requested_operation:
        raise FlowFloxMcpError("Choose an approved FlowFlox action first.")
    for tool in list_authorized_tools(credentials):
        if tool["name"] == requested_operation:
            return tool
    raise FlowFloxMcpError("That FlowFlox action is not granted to this signed key.")


def call_authorized_tool(
    credentials: Mapping[str, Any],
    operation: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    requested_operation = get_authorized_tool(credentials, operation)["name"]
    return _rpc(
        credentials,
        "tools/call",
        {"name": requested_operation, "arguments": dict(arguments)},
    )
