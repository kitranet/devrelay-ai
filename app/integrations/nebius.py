"""Nebius Token Factory chat completions client."""

import logging

import httpx

from app.core.config import Settings
from app.core.errors import MissingCredentialsError, ModelProviderError, ModelTimeoutError
from app.models.inference import ChatMessage, InferenceResponse

logger = logging.getLogger(__name__)


class NebiusClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._http_client = http_client

    async def complete(self, messages: list[ChatMessage], max_tokens: int = 1024) -> InferenceResponse:
        if self.settings.nebius_api_key is None or not self.settings.nebius_api_key.get_secret_value():
            raise MissingCredentialsError("NEBIUS_API_KEY is required for model inference.")

        endpoint = f"{self.settings.nebius_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.nebius_model,
            "messages": [message.model_dump() for message in messages],
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.settings.nebius_api_key.get_secret_value()}"}

        try:
            if self._http_client is None:
                async with httpx.AsyncClient(timeout=self.settings.nebius_timeout_seconds) as client:
                    response = await client.post(endpoint, json=payload, headers=headers)
            else:
                response = await self._http_client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.settings.nebius_timeout_seconds,
                )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("Model response content was not text")
            return InferenceResponse(model=body.get("model", self.settings.nebius_model), content=content)
        except httpx.TimeoutException as exc:
            logger.warning("Nebius inference timed out")
            raise ModelTimeoutError("Nebius inference request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("Nebius inference returned HTTP %s", exc.response.status_code)
            raise ModelProviderError(f"Nebius inference request failed with HTTP {exc.response.status_code}.") from exc
        except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("Nebius inference failed: %s", type(exc).__name__)
            raise ModelProviderError("Nebius inference failed or returned an invalid response.") from exc
