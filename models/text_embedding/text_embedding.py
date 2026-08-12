"""Dify text-embedding adapter for the protected FlowFlox gateway."""

import json
from collections.abc import Mapping

import requests

from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult
from dify_plugin.interfaces.model.openai_compatible.text_embedding import (
    OAICompatEmbeddingModel,
)


# The FlowFlox gateway has a CloudFront behaviour dedicated to API clients.
# Keep a stable, explicit client profile so Dify's request library is routed
# through that behaviour instead of the website renderer.
GATEWAY_USER_AGENT = "curl/8.7.1"


def embedding_credentials(credentials: Mapping) -> dict:
    """Translate provider connection fields to Dify's OAI adapter fields."""
    endpoint_url = str(credentials.get("api_base_url") or "").strip().rstrip("/")
    if not endpoint_url.endswith("/v1"):
        endpoint_url = f"{endpoint_url}/v1"
    return {
        **dict(credentials),
        "endpoint_url": endpoint_url,
    }


def embedding_headers(credentials: Mapping) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": GATEWAY_USER_AGENT,
    }
    api_key = str(credentials.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


class FlowFloxTextEmbeddingModel(OAICompatEmbeddingModel):
    """Use EmbeddingGemma through FlowFlox without exposing a RunPod URL."""

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: str | None = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        del input_type
        provider_credentials = embedding_credentials(credentials)
        endpoint_url = self._join_endpoint_url(
            provider_credentials.get("endpoint_url", ""), "embeddings"
        )
        context_size = self._get_context_size(model, provider_credentials)
        max_chunks = self._get_max_chunks(model, provider_credentials)
        inputs: list[str] = []
        used_tokens = 0

        for text in texts:
            num_tokens = self._get_num_tokens_by_gpt2(text)
            if num_tokens >= context_size:
                cutoff = int((len(text) * context_size) // num_tokens)
                inputs.append(text[:cutoff])
            else:
                inputs.append(text)

        embeddings: list[list[float]] = []
        for start in range(0, len(inputs), max_chunks):
            payload: dict[str, object] = {
                "input": inputs[start : start + max_chunks],
                "model": provider_credentials.get("endpoint_model_name", model),
                "encoding_format": "float",
            }
            if user:
                payload["user"] = user
            response = requests.post(
                endpoint_url,
                headers=embedding_headers(provider_credentials),
                data=json.dumps(payload),
                timeout=(10, 300),
            )
            response.raise_for_status()
            response_data = response.json()
            embeddings.extend(entry["embedding"] for entry in response_data["data"])
            used_tokens += int((response_data.get("usage") or {}).get("total_tokens") or 0)

        return TextEmbeddingResult(
            embeddings=embeddings,
            usage=self._calc_response_usage(model, provider_credentials, used_tokens),
            model=model,
        )

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        return super().get_num_tokens(model, embedding_credentials(credentials), texts)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        provider_credentials = embedding_credentials(credentials)
        endpoint_url = self._join_endpoint_url(
            provider_credentials.get("endpoint_url", ""), "embeddings"
        )
        response = requests.post(
            endpoint_url,
            headers=embedding_headers(provider_credentials),
            data=json.dumps({
                "input": ["ping"],
                "model": provider_credentials.get("endpoint_model_name", model),
            }),
            timeout=(10, 300),
        )
        try:
            response.raise_for_status()
            if "model" not in response.json():
                raise ValueError("FlowFlox returned an invalid embedding response.")
        except Exception as error:
            from dify_plugin.errors.model import CredentialsValidateFailedError

            raise CredentialsValidateFailedError(str(error)) from error
        finally:
            response.close()
