"""App-scoped connection state for the FlowFlox Tools Dify plugin.

The FlowFlox service key is accepted only by the Connect FlowFlox node.  It is
exchanged for a connection-specific capability and is never returned by a
tool, placed in an action output, or read by the catalog/action tools.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from collections.abc import Mapping
from typing import Any

from flowflox_errors import FlowFloxMcpError


_APP_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", re.IGNORECASE
)
_STORAGE_KEY_PREFIX = "flowflox-tools:app-connection:v1:"
APP_CONTEXT_PARAMETER = "dify_app_id"


@dataclass(frozen=True)
class FlowFloxAppConnection:
    """The non-service credential used after a Dify app is connected."""

    id: str
    app_id: str
    runtime_token: str
    name: str = "FlowFlox"


def _normalize_dify_app_id(value: Any) -> str:
    """Normalize one Dify app ID without accepting a partial identifier."""
    app_id = str(value or "").strip().lower()
    if not _APP_ID_PATTERN.fullmatch(app_id):
        return ""
    return app_id


def require_dify_app_id(
    session: Any,
    tool_parameters: Mapping[str, Any] | None = None,
) -> str:
    """Return the current app ID, including Agent-tool calls safely configured per app.

    Direct Dify Tool nodes receive ``session.app_id``. Dify's stock Agent
    strategy invokes tools through a backwards-invocation path that currently
    omits that field. The catalogue and gateway tools therefore expose a
    *form* parameter named ``dify_app_id``. It is bound once in the Agent node
    to the Dify-owned ``sys.app_id`` variable, so the model never sees or
    chooses it. This preserves one stored FlowFlox capability per Dify app
    without falling back to a shared provider credential.

    The direct setup tool deliberately does not pass ``tool_parameters`` here:
    creating a connection always requires the host-provided session app ID.
    """
    app_id = _normalize_dify_app_id(getattr(session, "app_id", ""))
    if app_id:
        return app_id

    app_id = _normalize_dify_app_id((tool_parameters or {}).get(APP_CONTEXT_PARAMETER))
    if app_id:
        return app_id

    if tool_parameters is not None:
        raise FlowFloxMcpError(
            "Set the FlowFlox app context field to Dify's system App ID (sys.app_id) in this Agent node."
        )
    raise FlowFloxMcpError(
        "FlowFlox must be connected from inside a saved Dify app before its API tools can run."
    )


def app_connection_storage_key(app_id: str) -> str:
    normalized_app_id = str(app_id or "").strip().lower()
    if not _APP_ID_PATTERN.fullmatch(normalized_app_id):
        raise FlowFloxMcpError("The active Dify app could not be identified safely.")
    return f"{_STORAGE_KEY_PREFIX}{normalized_app_id}"


def _connection_from_payload(payload: Any, expected_app_id: str) -> FlowFloxAppConnection:
    if not isinstance(payload, dict):
        raise FlowFloxMcpError("This Dify app does not have a valid FlowFlox connection. Connect it again.")
    connection_id = str(payload.get("id") or "").strip()
    app_id = str(payload.get("app_id") or "").strip().lower()
    runtime_token = str(payload.get("runtime_token") or "").strip()
    name = str(payload.get("name") or "FlowFlox").strip() or "FlowFlox"
    if not connection_id or app_id != expected_app_id or not runtime_token.startswith("ffx_app_"):
        raise FlowFloxMcpError("This Dify app does not have a valid FlowFlox connection. Connect it again.")
    return FlowFloxAppConnection(
        id=connection_id,
        app_id=app_id,
        runtime_token=runtime_token,
        name=name,
    )


def save_app_connection(session: Any, connection: FlowFloxAppConnection) -> None:
    """Persist only the app-specific capability, never the service key."""
    app_id = require_dify_app_id(session)
    if connection.app_id != app_id:
        raise FlowFloxMcpError("The FlowFlox connection belongs to a different Dify app.")
    try:
        session.storage.set(
            app_connection_storage_key(app_id),
            json.dumps(asdict(connection), separators=(",", ":")).encode("utf-8"),
        )
    except Exception as error:  # Dify reports storage failures through its plugin bridge.
        raise FlowFloxMcpError("FlowFlox could not save this app connection. Try connecting again.") from error


def load_app_connection(
    session: Any,
    tool_parameters: Mapping[str, Any] | None = None,
) -> FlowFloxAppConnection:
    """Load this app's capability and never fall back to a shared key."""
    app_id = require_dify_app_id(session, tool_parameters)
    try:
        raw = session.storage.get(app_connection_storage_key(app_id))
    except Exception as error:
        raise FlowFloxMcpError(
            "Connect FlowFlox in this Dify app before using its API catalog or actions."
        ) from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FlowFloxMcpError("This Dify app does not have a valid FlowFlox connection. Connect it again.") from error
    return _connection_from_payload(payload, app_id)
