from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from flowflox_actions import FlowFloxActionInputError, action_failure, action_result, parse_action_arguments
from flowflox_mcp import FlowFloxMcpError, call_authorized_tool, get_authorized_tool


class CallApprovedApiTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        operation = str(tool_parameters.get("operation") or "").strip()
        try:
            arguments = parse_action_arguments(tool_parameters.get("arguments_json"))
        except FlowFloxActionInputError as error:
            yield self.create_json_message(action_failure(operation, str(error)))
            return

        try:
            definition = get_authorized_tool(self.runtime.credentials, operation)
            result = call_authorized_tool(
                self.runtime.credentials,
                operation,
                arguments,
            )
        except FlowFloxMcpError as error:
            yield self.create_json_message(action_failure(operation, str(error)))
            return

        yield self.create_json_message(
            action_result(
                operation,
                result,
                title=str(definition.get("title") or operation),
                description=str(definition.get("description") or ""),
            )
        )
