from collections.abc import Generator, Mapping
import json
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


def clean_assistant_content(value: Any) -> str:
    """Remove a provider control marker that must never reach an end user.

    Some FlowFlox runtimes use the literal ``<tool_call>`` marker while
    deciding whether to issue a structured tool call.  Dify receives actual
    tool calls separately in ``message.tool_calls``.  Keeping this internal
    marker in the assistant text makes an otherwise normal, AI-written reply
    look like a static implementation detail in the chat preview.
    """
    return str(value or "").replace("<tool_call>", "").strip()


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
        raise CredentialsValidateFailedError("FlowFlox service credential is required.")
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
    # A scoped service credential intentionally has access only to the
    # automatic runtime. Do not make Dify's optional fixed-model comparison
    # turn that credential into a route-selection capability.
    if str(credentials.get("api_key") or "").strip().startswith("ffx_svc_"):
        return AUTOMATIC_MODEL, True
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
            "stream": stream,
        }
        if stream:
            # The FlowFlox gateway is OpenAI-compatible and can attach usage
            # to the terminal SSE event. Dify uses that event to finish an LLM
            # node cleanly after it has already rendered the text deltas.
            body["stream_options"] = {"include_usage": True}
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
                stream=stream,
            )
        except requests.RequestException as error:
            raise InvokeConnectionError("Could not reach FlowFlox's automatic runtime.") from error
        if model == CHOSEN_MODEL_PROFILE and not use_automatic_route and response.status_code in (404, 409, 503):
            response.close()
            body["model"] = AUTOMATIC_MODEL
            try:
                response = requests.post(
                    api_url(credentials, "/v1/chat/completions"),
                    headers=flowflox_headers(credentials, required_capabilities, runtime_only=True),
                    json=body,
                    timeout=120,
                    stream=stream,
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

        if stream:
            return self._stream_completion(
                model=model,
                credentials=credentials,
                response=response,
                prompt_messages=prompt_messages,
            )

        try:
            completion = response.json()
            choice = (completion.get("choices") or [])[0]
            message = choice.get("message") or {}
        except (AttributeError, IndexError, ValueError, TypeError) as error:
            raise InvokeServerUnavailableError("FlowFlox returned an invalid completion response.") from error

        assistant_message = AssistantPromptMessage(
            content=clean_assistant_content(message.get("content")),
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
        # Always return Dify's complete result type. Its base model interface
        # converts this into the one final stream event that the installed Dify
        # version expects, including usage information. Keeping that conversion
        # in Dify avoids an extra plugin-generated terminal event after Flox has
        # already returned an answer.
        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant_message,
            usage=usage,
            # Do not pass FlowFlox's backend fingerprint through to Dify.
            system_fingerprint="",
        )

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

    def _stream_completion(
        self,
        *,
        model: str,
        credentials: Mapping,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> Generator[LLMResultChunk, None, None]:
        """Translate FlowFlox's OpenAI-compatible SSE into Dify deltas.

        Returning a complete ``LLMResult`` makes Dify emit one final message,
        even if the runtime generated tokens incrementally. A Dify model plugin
        can instead yield ``LLMResultChunk`` instances as each SSE delta arrives.
        This preserves normal text streaming while buffering only tool-call
        arguments until the runtime marks the tool-call turn complete.
        """
        index = 0
        completed = False
        generated_text = ""
        tool_calls: dict[int, dict[str, str]] = {}

        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = str(raw_line).strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue

                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    # OpenAI-compatible servers may send keep-alive payloads
                    # between SSE events. Ignore them rather than stopping an
                    # otherwise healthy answer.
                    continue
                if not isinstance(payload, Mapping):
                    continue

                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0]
                if not isinstance(choice, Mapping):
                    continue
                delta = choice.get("delta")
                delta = delta if isinstance(delta, Mapping) else {}
                content = str(delta.get("content") or "").replace("<tool_call>", "")
                generated_text += content

                raw_tool_calls = delta.get("tool_calls")
                if isinstance(raw_tool_calls, list):
                    for raw_tool_call in raw_tool_calls:
                        if not isinstance(raw_tool_call, Mapping):
                            continue
                        try:
                            tool_index = int(raw_tool_call.get("index", len(tool_calls)))
                        except (TypeError, ValueError):
                            tool_index = len(tool_calls)
                        state = tool_calls.setdefault(
                            tool_index,
                            {"id": "", "type": "function", "name": "", "arguments": ""},
                        )
                        if raw_tool_call.get("id"):
                            state["id"] = str(raw_tool_call["id"])
                        if raw_tool_call.get("type"):
                            state["type"] = str(raw_tool_call["type"])
                        function = raw_tool_call.get("function")
                        if not isinstance(function, Mapping):
                            continue
                        if function.get("name"):
                            state["name"] = str(function["name"])
                        if function.get("arguments"):
                            state["arguments"] += str(function["arguments"])

                finish_reason = str(choice.get("finish_reason") or "").strip() or None
                if not content and not finish_reason:
                    continue

                if finish_reason:
                    message = AssistantPromptMessage(
                        content=content,
                        tool_calls=self._stream_tool_calls(tool_calls),
                    )
                    usage = self._stream_usage(
                        model=model,
                        credentials=credentials,
                        prompt_messages=prompt_messages,
                        content=generated_text,
                        value=payload.get("usage"),
                    )
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=list(prompt_messages),
                        system_fingerprint="",
                        delta=LLMResultChunkDelta(
                            index=index,
                            message=message,
                            finish_reason=finish_reason,
                            usage=usage,
                        ),
                    )
                    completed = True
                    break

                yield LLMResultChunk(
                    model=model,
                    prompt_messages=list(prompt_messages),
                    system_fingerprint="",
                    delta=LLMResultChunkDelta(
                        index=index,
                        message=AssistantPromptMessage(content=content),
                    ),
                )
                index += 1

            if not completed:
                raise InvokeServerUnavailableError(
                    "FlowFlox ended the response before sending a completion event."
                )
        except requests.RequestException as error:
            raise InvokeConnectionError("The FlowFlox response stream was interrupted.") from error
        finally:
            response.close()

    def _stream_usage(
        self,
        *,
        model: str,
        credentials: Mapping,
        prompt_messages: list[PromptMessage],
        content: str,
        value: Any,
    ) -> Any:
        usage_data = value if isinstance(value, Mapping) else {}
        prompt_tokens = int(usage_data.get("prompt_tokens") or self._get_num_tokens_by_gpt2(
            "\n".join(str(message.content or "") for message in prompt_messages)
        ))
        completion_tokens = int(usage_data.get("completion_tokens") or self._get_num_tokens_by_gpt2(content))
        return self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    @staticmethod
    def _stream_tool_calls(
        values: Mapping[int, Mapping[str, str]],
    ) -> list[AssistantPromptMessage.ToolCall]:
        return [
            AssistantPromptMessage.ToolCall(
                id=value["id"] or f"flowflox-tool-call-{tool_index}",
                type=value["type"] or "function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=value["name"],
                    arguments=value["arguments"] or "{}",
                ),
            )
            for tool_index, value in sorted(values.items())
            if value["name"]
        ]

    @staticmethod
    def _message_to_openai(message: PromptMessage) -> dict[str, Any]:
        if isinstance(message, SystemPromptMessage):
            return {"role": "system", "content": message.content}
        if isinstance(message, AssistantPromptMessage):
            # An Agent sends its earlier function request back with the tool
            # result on the next model turn.  Keep the OpenAI tool-call record
            # on that assistant message so the result remains paired with the
            # call that produced it.  Dropping this metadata turns a valid
            # multi-step tool conversation into an orphaned tool result.
            payload: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                payload["tool_calls"] = [
                    {
                        "id": str(getattr(call, "id", "") or "flowflox-tool-call"),
                        "type": str(getattr(call, "type", "") or "function"),
                        "function": {
                            "name": str(getattr(getattr(call, "function", None), "name", "") or ""),
                            "arguments": str(
                                getattr(getattr(call, "function", None), "arguments", "{}") or "{}"
                            ),
                        },
                    }
                    for call in tool_calls
                ]
            return payload
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
