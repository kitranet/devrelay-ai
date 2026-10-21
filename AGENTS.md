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
- Task plans may use only files and line references present in the authorized repository analysis. Keep plans `not_started`, require human approval, and report unsupported evidence rather than inventing it.
- Planning must remain read-only and static; do not execute or modify analyzed repository code.
- Proposal generation is limited to the predefined synthetic calculator scenario. It must create a diff in memory, validate source hashes and static patch safety, and never write, apply, or execute proposed code.
- Keep proposal lifecycle at `awaiting_review` with `human_approval_required=true`; do not add apply/approve behavior without an explicit later scope.
- Report runtime validation as `not_run` until a trusted isolated executor exists. Never imply host execution or successful tests from static parsing.
- Run `python -m pytest` before proposing backend changes.
- Preserve the repository license and existing files unless a task explicitly requests changes.
