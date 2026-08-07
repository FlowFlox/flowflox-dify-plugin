from collections.abc import Generator
import json
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from flowflox_app_connection import load_app_connection
from flowflox_errors import FlowFloxMcpError
from flowflox_mcp import list_authorized_tools


class DiscoverApprovedApisTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            tools = list_authorized_tools(load_app_connection(self.session, tool_parameters))
        except FlowFloxMcpError as error:
            yield self.create_text_message(str(error))
            return

        # An Agent needs a readable tool result in addition to the structured
        # payload. This lets the planner discover eligible APIs dynamically,
        # rather than relying on a canvas branch or keyword trigger per API.
        payload = {
            "operations": [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("inputSchema", {"type": "object"}),
                }
                for tool in tools
            ]
        }
        yield self.create_json_message(payload)
        yield self.create_text_message(json.dumps(payload, ensure_ascii=False, sort_keys=True))
