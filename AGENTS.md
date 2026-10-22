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
- Local Phase 5A reviews are disabled by default, development-only, loopback-only, and use unverified reviewer labels. Review approval means further consideration only; it never applies, executes, merges, or deploys code.
- Bind review decisions to proposal version, source hash, diff hash, and a non-empty justification. Preserve single-decision transitions and bounded in-memory audit history; do not call it durable or immutable.
- Generate handoff reports from stored plans/proposals/reviews and current static analysis only. Mark mock output, unverified identity, assumptions, missing evidence, and runtime `not_run` accurately.
- Report runtime validation as `not_run` until a trusted isolated executor exists. Never imply host execution or successful tests from static parsing.
- Run `python -m pytest` before proposing backend changes.
- Preserve the repository license and existing files unless a task explicitly requests changes.

- Phase 5B runtime-validation authorization is a separate, disabled-by-default, development-only local control. It is not authentication and never bypasses review, proposal-version, source-hash, or diff-hash checks.
- Runtime requests must remain limited to fixed test case IDs and fixed repository-relative paths. Never accept a client command, shell string, test path, image, host path, or arbitrary repository.
- Never execute repository code on the host. The configured production executor must fail closed unless all sandbox checks pass; there is no host fallback. Never claim a test passed from a fake executor or `sandbox_unavailable` evidence.
- Runtime evidence and one-use reservations are bounded process-local prototype data, not durable audit records. Sanitize and bound logs, redact secrets/absolute paths, and verify cleanup before a successful result.
- Preserve the current status honestly: no trusted sandbox launcher or verified immutable local image is configured in this checkout. Do not enable runtime execution or claim sandbox readiness until a separately reviewed executor actually enforces the required isolation controls.
