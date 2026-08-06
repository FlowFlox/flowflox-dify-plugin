"""A configurable Dify Tool node that represents one FlowFlox API action."""

from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities import ParameterOption
from dify_plugin.entities.tool import ToolInvokeMessage

from flowflox_actions import FlowFloxActionInputError, action_failure, action_result, parse_action_arguments
from flowflox_mcp import FlowFloxMcpError, call_authorized_tool, get_authorized_tool, list_authorized_tools


class FlowFloxApiActionTool(Tool):
    """Expose a single selected FlowFlox action as a composable Tool node."""

    def _fetch_parameter_options(self, parameter: str) -> list[ParameterOption]:
        if parameter != "operation":
            return []
        try:
            tools = list_authorized_tools(self.runtime.credentials)
        except FlowFloxMcpError:
            # Dify shows the credential validation error separately. Do not
            # leak transport detail into the action picker.
            return []

        return [
            ParameterOption(
                value=str(tool["name"]),
                label={
                    "en_US": " · ".join(
                        part for part in (
                            str(tool.get("title") or "").strip(),
                            str(tool.get("description") or "").strip(),
                        ) if part
                    ) or str(tool["name"]),
                },
            )
            for tool in tools
        ]

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        operation = str(tool_parameters.get("operation") or "").strip()
        try:
            arguments = parse_action_arguments(tool_parameters.get("input"))
        except FlowFloxActionInputError as error:
            yield self.create_json_message(action_failure(operation, str(error)))
            return

        try:
            definition = get_authorized_tool(self.runtime.credentials, operation)
            result = call_authorized_tool(self.runtime.credentials, operation, arguments)
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
