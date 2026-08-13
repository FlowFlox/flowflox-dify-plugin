"""Dify text-embedding adapter for the protected FlowFlox gateway."""

from collections.abc import Mapping

from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult
from dify_plugin.interfaces.model.openai_compatible.text_embedding import (
    OAICompatEmbeddingModel,
)


def embedding_credentials(credentials: Mapping) -> dict:
    """Translate the provider's connection fields to Dify's OAI adapter fields.

    The adapter calls only the FlowFlox gateway's OpenAI-compatible
    ``/embeddings`` endpoint. The configured connection may include ``/v1``
    already, which is the normal FlowFlox setup.
    """
    endpoint_url = str(credentials.get("api_base_url") or "").strip().rstrip("/")
    if not endpoint_url.endswith("/v1"):
        endpoint_url = f"{endpoint_url}/v1"
    return {
        **dict(credentials),
        "endpoint_url": endpoint_url,
    }


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
        return super()._invoke(
            model=model,
            credentials=embedding_credentials(credentials),
            texts=texts,
            user=user,
            input_type=input_type,
        )

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        return super().get_num_tokens(model, embedding_credentials(credentials), texts)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        super().validate_credentials(model, embedding_credentials(credentials))
