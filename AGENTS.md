# Repository guidance

- Keep the backend modular: HTTP routes in `app/api`, schemas in `app/models`, business logic in `app/services`, provider adapters in `app/integrations`, and configuration/cross-cutting code in `app/core`.
- Never commit `.env`, API keys, tokens, or local virtual environments. Use `.env.example` with placeholders only.
- Do not log authorization headers, request headers, environment dumps, or full provider response bodies.
- All outbound model calls must have bounded timeouts and return sanitized errors.
- Do not add arbitrary shell execution or autonomous repository modification.
- Repository analysis must remain static: never import, execute, or evaluate target repository code.
- Only scan repositories mapped by configured IDs in `AUTHORIZED_REPOSITORIES`; do not accept client-supplied filesystem paths.
- Keep scanner file count, size, depth, and processing time limits enforced. Skip symlinks, secrets, and generated/binary directories.
- Mock inference must be selected explicitly and marked with `provider="mock"` and `is_mock=true`; never fall back silently from Nebius errors.
- Run `python -m pytest` before proposing backend changes.
- Preserve the repository license and existing files unless a task explicitly requests changes.
