from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from flowflox_mcp import FlowFloxMcpError, list_authorized_tools


class FlowfloxToolsProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            tools = list_authorized_tools(credentials)
        except FlowFloxMcpError as error:
            raise ToolProviderCredentialValidationError(str(error)) from error
        if not tools:
            raise ToolProviderCredentialValidationError(
                "This FlowFlox key has no approved APIs. Grant an active API to the credential first."
            )
