"""FlowFlox app-connection and MCP client used by the Dify Tools plugin."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import requests

from flowflox_errors import FlowFloxMcpError

MCP_SERVER_URL = "https://gateway.flowflox.dev/v1/mcp"
APP_CONNECTION_EXCHANGE_URL = "https://gateway.flowflox.dev/v1/dify/app-connections/exchange"
REQUEST_TIMEOUT_SECONDS = 20


def _authorization_code(code: str) -> str:
    """Accept only a short-lived setup code, never a durable service key."""
    code = str(code or "").strip()
    if not code:
        raise FlowFloxMcpError("A one-time FlowFlox Dify authorization code is required.")
    if not code.startswith("ffx_dac_"):
        raise FlowFloxMcpError("The FlowFlox Dify authorization code is not valid.")
    return code


def _app_runtime_token(connection: Any) -> str:
    token = str(getattr(connection, "runtime_token", "") or "").strip()
    if not token.startswith("ffx_app_"):
        raise FlowFloxMcpError("This Dify app does not have a valid FlowFlox authorization. Authorize it again.")
    return token


def connect_dify_app(session: Any, authorization_code: str) -> Any:
    """Exchange one setup code for a capability bound to one Dify app."""
    # Import here to avoid a circular import: app connection storage imports
    # FlowFloxMcpError from this module.
    from flowflox_app_connection import FlowFloxAppConnection, require_dify_app_id

    app_id = require_dify_app_id(session)
    try:
        response = requests.post(
            APP_CONNECTION_EXCHANGE_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={"app_id": app_id, "authorization_code": _authorization_code(authorization_code)},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise FlowFloxMcpError("FlowFlox could not authorize this Dify app.") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise FlowFloxMcpError("FlowFlox returned an invalid Dify authorization response.") from error

    if response.status_code in (401, 403):
        raise FlowFloxMcpError("The Dify authorization code expired, was already used, or belongs to another app.")
    if response.status_code == 409:
        raise FlowFloxMcpError("This Dify app or API credential is already connected elsewhere. Create a separate app authorization in FlowFlox.")
    if not response.ok or not isinstance(payload, dict):
        raise FlowFloxMcpError("FlowFlox could not authorize this Dify app.")

    raw_connection = payload.get("connection")
    runtime_token = str(payload.get("runtime_token") or "").strip()
    if not isinstance(raw_connection, dict):
        raise FlowFloxMcpError("FlowFlox returned an invalid Dify app connection.")
    connection_id = str(raw_connection.get("id") or "").strip()
    returned_app_id = str(raw_connection.get("app_id") or "").strip().lower()
    returned_name = str(raw_connection.get("name") or "FlowFlox").strip() or "FlowFlox"
    if not connection_id or returned_app_id != app_id or not runtime_token.startswith("ffx_app_"):
        raise FlowFloxMcpError("FlowFlox returned an invalid Dify app connection.")
    return FlowFloxAppConnection(
        id=connection_id,
        app_id=returned_app_id,
        runtime_token=runtime_token,
        name=returned_name,
    )


def _rpc(connection: Any, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        response = requests.post(
            MCP_SERVER_URL,
            headers={
                "Authorization": f"Bearer {_app_runtime_token(connection)}",
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
        raise FlowFloxMcpError("This Dify app's FlowFlox authorization is no longer active. Authorize it again.")
    if not response.ok or not isinstance(payload, dict):
        raise FlowFloxMcpError("FlowFlox API tools are unavailable.")
    if isinstance(payload.get("error"), dict):
        raise FlowFloxMcpError("This FlowFlox API request was not allowed.")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise FlowFloxMcpError("FlowFlox API tools returned an invalid result.")
    return result


def list_authorized_tools(connection: Any) -> list[dict[str, Any]]:
    result = _rpc(connection, "tools/list")
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise FlowFloxMcpError("FlowFlox did not return an API list.")
    return [tool for tool in tools if isinstance(tool, dict) and isinstance(tool.get("name"), str)]


def get_authorized_tool(connection: Any, operation: str) -> dict[str, Any]:
    """Return one currently granted operation without trusting client metadata."""
    requested_operation = str(operation or "").strip()
    if not requested_operation:
        raise FlowFloxMcpError("Choose an approved FlowFlox action first.")
    for tool in list_authorized_tools(connection):
        if tool["name"] == requested_operation:
            return tool
    raise FlowFloxMcpError("That FlowFlox action is not granted to this Dify app.")


def call_authorized_tool(
    connection: Any,
    operation: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    requested_operation = get_authorized_tool(connection, operation)["name"]
    return _rpc(
        connection,
        "tools/call",
        {"name": requested_operation, "arguments": dict(arguments)},
    )
