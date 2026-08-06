from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from flowflox_mcp import FlowFloxMcpError, list_authorized_tools


class DiscoverApprovedApisTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            tools = list_authorized_tools(self.runtime.credentials)
        except FlowFloxMcpError as error:
            yield self.create_text_message(str(error))
            return

        yield self.create_json_message(
            {
                "operations": [
                    {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "input_schema": tool.get("inputSchema", {"type": "object"}),
                    }
                    for tool in tools
                ]
            }
        )
