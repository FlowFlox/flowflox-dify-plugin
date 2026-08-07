"""A FlowFlox API step that runs only when its Dify branch is reached."""

from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from flowflox_actions import (
    FlowFloxActionInputError,
    action_context_text,
    action_failure,
    action_result,
    parse_action_arguments,
)
from flowflox_app_connection import load_app_connection
from flowflox_errors import FlowFloxMcpError
from flowflox_mcp import call_authorized_tool, get_authorized_tool


class ConditionalApiActionTool(Tool):
    """Run exactly one approved API after an explicit router/condition step."""

    def _emit_action_envelope(self, envelope: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Pass the safe structured envelope to later canvas steps and an LLM."""
        yield self.create_json_message(envelope)
        yield self.create_text_message(action_context_text(envelope))

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        operation = str(tool_parameters.get("operation") or "").strip()
        if not operation:
            yield from self._emit_action_envelope(
                action_failure("", "A previous router or condition must provide an approved operation name.")
            )
            return

        try:
            arguments = parse_action_arguments(tool_parameters.get("arguments_json"))
        except FlowFloxActionInputError as error:
            yield from self._emit_action_envelope(action_failure(operation, str(error)))
            return

        try:
            connection = load_app_connection(self.session, tool_parameters)
            definition = get_authorized_tool(connection, operation)
            result = call_authorized_tool(connection, operation, arguments)
        except FlowFloxMcpError as error:
            yield from self._emit_action_envelope(action_failure(operation, str(error)))
            return

        yield from self._emit_action_envelope(
            action_result(
                operation,
                result,
                title=str(definition.get("title") or operation),
                description=str(definition.get("description") or ""),
            )
        )
