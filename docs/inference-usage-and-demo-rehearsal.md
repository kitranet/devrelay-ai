# Inference usage and local demo rehearsal

This guide supports a presenter-led rehearsal of the synthetic Northstar nightly-report incident. The dashboard can prefill the incident request when the authorized repository ID contains `continuity-pipeline`. The request asks for investigation steps and evidence only; the root cause is not included in the planner context.

## Five-minute rehearsal

1. Start FastAPI on `127.0.0.1:8001` and the production Next.js dashboard on `127.0.0.1:3000`, following [the Windows hosting runbook](windows-hosting.md). Use `INFERENCE_PROVIDER=mock`, keep `NEBIUS_LIVE_INFERENCE_ENABLED=false`, and expose only the authorized synthetic continuity fixture.
2. Open the exact configured local dashboard origin and sign in with the temporary credentials created for this rehearsal. Do not put credentials in a recording or shell history.
3. Select the continuity pipeline fixture. Read the incident card and confirm the task asks to investigate orchestration, validation, transformation, retries, configuration, and publishing without presuming a cause.
4. Choose **Analyze repository**. Expand the module, dependency, test, and warning sections. Explain that analysis is static and never imports or runs fixture code.
5. Choose **Generate plan**. In mock mode the result is deterministic simulated output, not Nemotron. Inspect the supplied source excerpts, their hashes, verified references, findings, and unresolved question. Treat mock prose as a workflow demonstration, not an interpretation of the source.
6. If the mock result is eligible, use the plan-only review and handoff controls. Review is a local, unverified label; it does not approve code or authorize execution. The pipeline scenario does not qualify for the separate calculator-only code proposal.
7. Show **Inference runs and estimated cost**. Mock attempts should show no external call and no token estimate. Explain the retention, sanitized fields, published-rate estimate, and that actual billing is not available.
8. Close by showing that runtime validation is `not_run`, repository files remain unchanged, and no plan was executed.

The dashboard may show fewer rows or a different deterministic summary depending on the selected fixture's current static analysis. Do not present mock output as a genuine model result. The historical live Nemotron observation in the evaluation documents is separate from the current mock rehearsal.

## Per-run telemetry

The backend creates an attempt record in local SQLite before invoking a provider. It stores a random run ID, timestamp, authorized repository ID, task ID, configured provider/model, request status, provider HTTP status when received, duration, safe error code, finish reason, provider token counts, quota reservation state, plan/citation validation status and counts, and the pricing metadata used for an estimate. It does not store prompts, task text, repository excerpts, response bodies, authorization headers, or credentials.

Records are bounded to 5,000 and retained for 90 days by default (configurable from 1 to 365 days). Set `INFERENCE_TELEMETRY_DB_PATH` to a protected local state directory when running outside development. On POSIX systems the directory and SQLite file are restricted to the owner. On Windows, protect the state directory with the user's filesystem ACLs and backups.

The history endpoint is `GET /api/v1/inference/attempts`; it is loopback-only in FastAPI and is exposed to the browser only through the authenticated Next.js route allowlist. It is a usage history, not an immutable or durable audit ledger.

Cost is only estimated for an exact provider/model entry with both input and output token counts. The reference registry currently prices `nebius` + `nvidia/Nemotron-3_5-Lightning` at $0.06 per million input tokens and $0.24 per million output tokens. Reasoning tokens are already part of output tokens and are not added a second time. The rates are sourced from [Nebius Token Factory's NVIDIA Nemotron model pricing](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference), recorded in the registry as of 2026-10-25. Confirm current rates before relying on a new estimate.

An estimate is not a provider invoice. DevRelay cannot query actual billed cost. Missing usage remains unknown; it is never rendered as zero. A provider quota reserves request count and is not a dollar spending cap. Unknown models or missing pricing entries have no estimate.

## Earlier live attempts

Telemetry begins when this feature is installed. Earlier attempts are not reconstructed from browser recordings, quota counts, or recollection. In particular, the earlier continuity request that timed out may have consumed a quota reservation, but its token usage and outcome were not preserved. It is therefore absent from local history and has no invented cost. Do not reset the quota to make it appear in history.

## Live inference

Rehearse with mock mode. A live Nemotron request requires a separate explicit operator authorization, `INFERENCE_PROVIDER=nebius`, `NEBIUS_LIVE_INFERENCE_ENABLED=true`, a configured server-side key, a healthy persistent request-quota database, and a remaining request allowance. A live request is billable and cannot be undone. Do not enable it during this mock rehearsal.
