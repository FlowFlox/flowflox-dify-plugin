from collections.abc import Generator, Mapping
from typing import Any

import requests
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel


PROFILE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "flowflox-auto-chat": ("chat",),
    "flowflox-chosen-chat": ("chat",),
    "flowflox-auto-code": ("chat", "code"),
    "flowflox-auto-reasoning": ("chat", "reasoning"),
    "flowflox-auto-tools": ("chat", "tools"),
    "flowflox-auto-vision": ("chat", "vision"),
}
CHOSEN_MODEL_PROFILE = "flowflox-chosen-chat"
AUTOMATIC_MODEL = "flowflox-auto"


def api_url(credentials: Mapping, path: str) -> str:
    base_url = str(credentials.get("api_base_url") or "").rstrip("/")
    if not base_url:
        raise CredentialsValidateFailedError("FlowFlox application URL is required.")
    if base_url.endswith("/v1"):
        return f"{base_url}{path.removeprefix('/v1')}"
    return f"{base_url}{path}"


def flowflox_headers(
    credentials: Mapping,
    required_capabilities: tuple[str, ...],
    *,
    runtime_only: bool,
    direct_model_test: bool = False,
) -> dict[str, str]:
    api_key = str(credentials.get("api_key") or "").strip()
    if not api_key:
        raise CredentialsValidateFailedError("FlowFlox internal integration credential is required.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if runtime_only:
        headers["X-FlowFlox-Runtime-Only"] = "true"
        headers["X-FlowFlox-Required-Capabilities"] = ",".join(required_capabilities)
    if direct_model_test:
        headers["X-FlowFlox-Direct-Model-Test"] = "true"
    return headers


def chosen_model(
    model_parameters: Mapping,
    credentials: Mapping,
    required_capabilities: tuple[str, ...],
) -> tuple[str, bool]:
    """Return this node's live model, otherwise the automatic Flox route."""
    # `test_model` is kept only for workspaces configured with plugin versions before 0.1.7.
    candidate = str(
        model_parameters.get("flowflox_model_id") or credentials.get("test_model") or ""
    ).strip()
    if not candidate:
        return AUTOMATIC_MODEL, True
    try:
        response = requests.get(
            api_url(credentials, "/v1/models"),
            headers=flowflox_headers(credentials, required_capabilities, runtime_only=False),
            timeout=15,
        )
        models = response.json().get("data") if response.ok else []
    except (requests.RequestException, AttributeError, ValueError):
        models = []
    for entry in models or []:
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("id") or "").strip() != candidate:
            continue
        capabilities = set((entry.get("flowflox") or {}).get("capabilities") or [])
        if set(required_capabilities).issubset(capabilities):
            return candidate, False
    return AUTOMATIC_MODEL, True


class FlowFloxLargeLanguageModel(LargeLanguageModel):
    """Dify LLM provider for FlowFlox's capability-routed runtime pool."""

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """Map only vendor exceptions; this provider raises Dify errors directly."""
        return {}

    def _invoke(
        self,
        model: str,
        credentials: Mapping,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator[LLMResultChunk, None, None]:
        required_capabilities = PROFILE_CAPABILITIES.get(model)
        if not required_capabilities:
            raise InvokeBadRequestError("Choose a Flox option for this task.")
        if tools and "tools" not in required_capabilities:
            raise InvokeBadRequestError(
                "This node uses tools. Choose Automatic — Tools for this task."
            )

        target_model, use_automatic_route = (
            chosen_model(model_parameters, credentials, required_capabilities)
            if model == CHOSEN_MODEL_PROFILE
            else (AUTOMATIC_MODEL, True)
        )
        body: dict[str, Any] = {
            "model": target_model,
            "messages": [self._message_to_openai(message) for message in prompt_messages],
            "stream": False,
        }
        for parameter in ("temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty"):
            if parameter in model_parameters:
                body[parameter] = model_parameters[parameter]
        if stop:
            body["stop"] = stop
        if user:
            body["user"] = user
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]

        try:
            response = requests.post(
                api_url(credentials, "/v1/chat/completions"),
                headers=flowflox_headers(
                    credentials,
                    required_capabilities,
                    runtime_only=use_automatic_route,
                    direct_model_test=not use_automatic_route,
                ),
                json=body,
                timeout=120,
            )
        except requests.RequestException as error:
            raise InvokeConnectionError("Could not reach FlowFlox's automatic runtime.") from error
        if model == CHOSEN_MODEL_PROFILE and not use_automatic_route and response.status_code in (404, 409, 503):
            body["model"] = AUTOMATIC_MODEL
            try:
                response = requests.post(
                    api_url(credentials, "/v1/chat/completions"),
                    headers=flowflox_headers(credentials, required_capabilities, runtime_only=True),
                    json=body,
                    timeout=120,
                )
            except requests.RequestException as error:
                raise InvokeConnectionError("Could not reach FlowFlox's automatic runtime.") from error
        if response.status_code in (401, 403):
            raise InvokeAuthorizationError("The FlowFlox integration credential was not accepted.")
        if response.status_code == 400:
            raise InvokeBadRequestError(self._response_error(response, "FlowFlox rejected this request."))
        if response.status_code in (404, 409, 503):
            raise InvokeServerUnavailableError(
                self._response_error(response, "No live FlowFlox runtime satisfies this capability profile.")
            )
        if not response.ok:
            raise InvokeServerUnavailableError("The FlowFlox automatic runtime did not generate a response.")

        try:
            completion = response.json()
            choice = (completion.get("choices") or [])[0]
            message = choice.get("message") or {}
        except (AttributeError, IndexError, ValueError, TypeError) as error:
            raise InvokeServerUnavailableError("FlowFlox returned an invalid completion response.") from error

        assistant_message = AssistantPromptMessage(
            content=str(message.get("content") or ""),
            tool_calls=self._tool_calls(message.get("tool_calls") or []),
        )
        usage_data = completion.get("usage") or {}
        prompt_tokens = int(usage_data.get("prompt_tokens") or self._get_num_tokens_by_gpt2(
            "\n".join(str(message.content or "") for message in prompt_messages)
        ))
        completion_tokens = int(usage_data.get("completion_tokens") or self._get_num_tokens_by_gpt2(
            str(assistant_message.content or "")
        ))
        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        if not stream:
            return LLMResult(
                model=model,
                prompt_messages=prompt_messages,
                message=assistant_message,
                usage=usage,
                # Do not pass FlowFlox's backend fingerprint through to Dify.
                system_fingerprint="",
            )
        return self._as_stream(model, prompt_messages, assistant_message, usage)

    def validate_credentials(self, model: str, credentials: Mapping) -> None:
        required_capabilities = PROFILE_CAPABILITIES.get(model)
        if not required_capabilities:
            raise CredentialsValidateFailedError("Unknown FlowFlox capability profile.")
        try:
            response = requests.get(
                api_url(credentials, "/v1/models"),
                headers=flowflox_headers(credentials, required_capabilities, runtime_only=True),
                timeout=15,
            )
        except requests.RequestException as error:
            raise CredentialsValidateFailedError("Could not reach the FlowFlox model registry.") from error
        if response.status_code in (401, 403):
            raise CredentialsValidateFailedError("The FlowFlox integration credential was not accepted.")
        if not response.ok:
            raise CredentialsValidateFailedError("The FlowFlox model registry is unavailable.")
        try:
            models = response.json().get("data") or []
        except (AttributeError, ValueError) as error:
            raise CredentialsValidateFailedError("The FlowFlox model registry returned an invalid response.") from error
        if not any(
            set(required_capabilities).issubset(
                set((entry.get("flowflox") or {}).get("capabilities") or [])
            )
            for entry in models
        ):
            raise CredentialsValidateFailedError(
                f"No live FlowFlox runtime currently verifies: {', '.join(required_capabilities)}."
            )

    def get_num_tokens(
        self,
        model: str,
        credentials: Mapping,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        text = "\n".join(str(message.content or "") for message in prompt_messages)
        return self._get_num_tokens_by_gpt2(text)

    @staticmethod
    def _response_error(response: requests.Response, fallback: str) -> str:
        try:
            return str(response.json().get("statusMessage") or response.json().get("message") or fallback)
        except (AttributeError, ValueError):
            return fallback

    @staticmethod
    def _tool_calls(tool_calls: list[Mapping]) -> list[AssistantPromptMessage.ToolCall]:
        return [
            AssistantPromptMessage.ToolCall(
                id=str(tool_call.get("id") or tool_call.get("index") or "flowflox-tool-call"),
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=str((tool_call.get("function") or {}).get("name") or ""),
                    arguments=str((tool_call.get("function") or {}).get("arguments") or "{}"),
                ),
            )
            for tool_call in tool_calls
            if (tool_call.get("function") or {}).get("name")
        ]

    @staticmethod
    def _message_to_openai(message: PromptMessage) -> dict[str, Any]:
        if isinstance(message, SystemPromptMessage):
            return {"role": "system", "content": message.content}
        if isinstance(message, AssistantPromptMessage):
            return {"role": "assistant", "content": message.content}
        if isinstance(message, ToolPromptMessage):
            return {
                "role": "tool",
                "name": message.name,
                "tool_call_id": message.tool_call_id,
                "content": message.content,
            }
        if isinstance(message, UserPromptMessage):
            if isinstance(message.content, str):
                return {"role": "user", "content": message.content}
            content: list[dict[str, Any]] = []
            for part in message.content or []:
                if part.type == PromptMessageContentType.TEXT:
                    content.append({"type": "text", "text": part.data})
                elif part.type == PromptMessageContentType.IMAGE:
                    image = part
                    if isinstance(image, ImagePromptMessageContent):
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": image.data, "detail": image.detail.value},
                        })
            return {"role": "user", "content": content}
        raise InvokeBadRequestError(f"Unsupported Dify prompt message: {type(message).__name__}.")

    @staticmethod
    def _as_stream(
        model: str,
        prompt_messages: list[PromptMessage],
        message: AssistantPromptMessage,
        usage: Any,
    ) -> Generator[LLMResultChunk, None, None]:
        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            system_fingerprint="",
            delta=LLMResultChunkDelta(index=0, message=message),
        )
        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            system_fingerprint="",
            delta=LLMResultChunkDelta(
                index=1,
                message=AssistantPromptMessage(content=""),
                finish_reason="stop",
                usage=usage,
            ),
        )
