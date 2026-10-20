# Repository guidance

- Keep the backend modular: HTTP routes in `app/api`, schemas in `app/models`, business logic in `app/services`, provider adapters in `app/integrations`, and configuration/cross-cutting code in `app/core`.
- Never commit `.env`, API keys, tokens, or local virtual environments. Use `.env.example` with placeholders only.
- Do not log authorization headers, request headers, environment dumps, or full provider response bodies.
- All outbound model calls must have bounded timeouts and return sanitized errors.
- Do not add arbitrary shell execution or autonomous repository modification.
- Run `python -m pytest` before proposing backend changes.
- Preserve the repository license and existing files unless a task explicitly requests changes.
