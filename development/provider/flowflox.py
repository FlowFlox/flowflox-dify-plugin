from collections.abc import Mapping

import requests
from dify_plugin import ModelProvider
from dify_plugin.errors.model import CredentialsValidateFailedError


def models_url(credentials: Mapping) -> str:
    base_url = str(credentials.get("api_base_url") or "").rstrip("/")
    if not base_url:
        raise CredentialsValidateFailedError("FlowFlox application URL is required.")
    return f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"


class FlowFloxProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        api_key = str(credentials.get("api_key") or "").strip()
        if not api_key:
            raise CredentialsValidateFailedError("FlowFlox internal integration credential is required.")
        try:
            response = requests.get(
                models_url(credentials),
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
        except requests.RequestException as error:
            raise CredentialsValidateFailedError("Could not reach the FlowFlox model registry.") from error
        if response.status_code in (401, 403):
            raise CredentialsValidateFailedError("The FlowFlox integration credential was not accepted.")
        if not response.ok:
            raise CredentialsValidateFailedError("The FlowFlox model registry is unavailable.")
