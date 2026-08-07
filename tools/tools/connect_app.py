"""Connect exactly one scoped FlowFlox key to the active Dify app."""

from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from flowflox_app_connection import save_app_connection
from flowflox_errors import FlowFloxMcpError
from flowflox_mcp import connect_dify_app, list_authorized_tools


class ConnectAppTool(Tool):
    """Exchange the app owner's key for an app-bound FlowFlox capability."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        service_key = str(tool_parameters.get("flowflox_service_key") or "").strip()
        connection_name = str(tool_parameters.get("connection_name") or "").strip()
        try:
            connection = connect_dify_app(self.session, service_key, connection_name)
            tools = list_authorized_tools(connection)
            if not tools:
                raise FlowFloxMcpError(
                    "This FlowFlox key has no approved APIs. Grant an active API before connecting the app."
                )
            save_app_connection(self.session, connection)
        except FlowFloxMcpError as error:
            yield self.create_json_message({"connected": False, "error": str(error)})
            return

        # Do not return the service key or the app capability. Downstream
        # nodes use the active Dify app context instead.
        yield self.create_json_message(
            {
                "connected": True,
                "connection": {
                    "id": connection.id,
                    "name": connection.name,
                    "app_id": connection.app_id,
                },
                "approved_action_count": len(tools),
            }
        )
