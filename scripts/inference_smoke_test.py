"""Make one genuine Nebius Token Factory inference request."""

import asyncio

from app.core.config import Settings
from app.integrations.nebius import NebiusClient
from app.models.inference import ChatMessage


async def main() -> None:
    settings = Settings()
    client = NebiusClient(settings)
    result = await client.complete(
        [ChatMessage(role="user", content="Reply with the single word: ready")],
        max_tokens=32,
    )
    print(f"Inference succeeded using model {result.model}: {result.content}")


if __name__ == "__main__":
    asyncio.run(main())
