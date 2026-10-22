"""Make one genuine Nebius Token Factory inference request."""

import asyncio

from app.core.config import Settings
from app.integrations.nebius import NebiusClient
from app.models.inference import ChatMessage


async def main() -> None:
    settings = Settings()
    if settings.inference_provider != "nebius":
        raise RuntimeError("Set INFERENCE_PROVIDER=nebius explicitly before running the live smoke test.")
    client = NebiusClient(settings)
    result = await client.complete(
        [ChatMessage(role="user", content="Reply with the single word: ready")],
        max_tokens=settings.nebius_max_output_tokens,
    )
    usage = result.usage
    print(f"Inference completed. Model: {result.model}; provider: {result.provider}; finish: {result.finish_reason}; latency_ms: {result.latency_ms}.")
    if usage is not None:
        print(
            "Tokens: "
            f"input={usage.input_tokens if usage.input_tokens is not None else 'n/a'}, "
            f"output={usage.output_tokens if usage.output_tokens is not None else 'n/a'}, "
            f"reasoning={usage.reasoning_tokens if usage.reasoning_tokens is not None else 'n/a'}, "
            f"total={usage.total_tokens if usage.total_tokens is not None else 'n/a'}."
        )


if __name__ == "__main__":
    asyncio.run(main())
