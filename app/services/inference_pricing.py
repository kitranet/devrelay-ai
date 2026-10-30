"""Versioned per-model reference prices used only for estimated token cost."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

NEBIUS_NEMOTRON_PRICING_SOURCE = (
    "https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference"
)
PRICING_AS_OF = "2026-10-25"


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    pricing_model: str
    price_per_million_input_tokens: Decimal
    price_per_million_output_tokens: Decimal
    source: str
    effective_as_of: str
    registry_version: str


DEFAULT_PRICES = {
    ("nebius", "nvidia/Nemotron-3_5-Lightning"): ModelPrice(
        provider="nebius",
        model="nvidia/Nemotron-3_5-Lightning",
        pricing_model="per_million_input_output_tokens",
        price_per_million_input_tokens=Decimal("0.06"),
        price_per_million_output_tokens=Decimal("0.24"),
        source=NEBIUS_NEMOTRON_PRICING_SOURCE,
        effective_as_of=PRICING_AS_OF,
        registry_version="devrelay-model-prices-v1",
    ),
}


class PricingRegistry:
    """Exact provider/model lookup; unsupported combinations have no estimate."""

    def __init__(self, overrides_json: str | None = None) -> None:
        self._prices = dict(DEFAULT_PRICES)
        if not overrides_json:
            return
        if len(overrides_json) > 16_384:
            raise ValueError("Inference pricing configuration is too large")
        try:
            decoded = json.loads(overrides_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Inference pricing configuration is invalid JSON") from exc
        if not isinstance(decoded, list) or len(decoded) > 32:
            raise ValueError("Inference pricing overrides must be a bounded JSON array")
        for item in decoded:
            self._prices[self._key(item)] = self._parse(item)

    @staticmethod
    def _key(item: Any) -> tuple[str, str]:
        if not isinstance(item, dict):
            raise ValueError("Each inference pricing override must be an object")
        provider = item.get("provider")
        model = item.get("model")
        if not isinstance(provider, str) or provider not in {"nebius", "mock"}:
            raise ValueError("Inference pricing provider is unsupported")
        if not isinstance(model, str) or not model or len(model) > 200:
            raise ValueError("Inference pricing model is invalid")
        return provider, model

    @classmethod
    def _parse(cls, item: Any) -> ModelPrice:
        provider, model = cls._key(item)
        required = {
            "provider", "model", "pricing_model", "price_per_million_input_tokens",
            "price_per_million_output_tokens", "source", "effective_as_of", "registry_version",
        }
        if set(item) != required:
            raise ValueError("Inference pricing override fields do not match the supported schema")
        try:
            input_rate = Decimal(str(item["price_per_million_input_tokens"]))
            output_rate = Decimal(str(item["price_per_million_output_tokens"]))
            date.fromisoformat(item["effective_as_of"])
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Inference pricing rates or date are invalid") from exc
        source = item["source"]
        version = item["registry_version"]
        pricing_model = item["pricing_model"]
        if (not input_rate.is_finite() or not output_rate.is_finite() or input_rate < 0 or output_rate < 0
                or not isinstance(source, str) or not source.startswith("https://") or len(source) > 500
                or not isinstance(version, str) or not version or len(version) > 100
                or not isinstance(pricing_model, str) or not pricing_model or len(pricing_model) > 100):
            raise ValueError("Inference pricing override values are invalid")
        return ModelPrice(
            provider=provider, model=model, pricing_model=pricing_model,
            price_per_million_input_tokens=input_rate,
            price_per_million_output_tokens=output_rate,
            source=source, effective_as_of=item["effective_as_of"], registry_version=version,
        )

    def find(self, provider: str, model: str) -> ModelPrice | None:
        return self._prices.get((provider, model))


def estimate_cost_usd(price: ModelPrice, input_tokens: int, output_tokens: int) -> Decimal:
    """Output tokens already include reasoning tokens; never add reasoning again."""
    return (
        Decimal(input_tokens) * price.price_per_million_input_tokens
        + Decimal(output_tokens) * price.price_per_million_output_tokens
    ) / Decimal(1_000_000)
