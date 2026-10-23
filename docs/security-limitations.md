# Security and reliability limitations

This document describes the current local hackathon prototype. It is not a production security certification.

## Current controls

- Repository identifiers resolve only through configured `AUTHORIZED_REPOSITORIES`; API callers cannot submit arbitrary filesystem paths.
- The scanner is static, parses Python with `ast`, and never imports/evaluates repository code. It applies file count, per-file/aggregate size, depth, and processing-time limits; skips symlinks and common generated, binary, and secret paths.
- Planning context is assembled from bounded static-analysis metadata, not arbitrary README/source text. Provider output is untrusted, parsed against Pydantic schemas, and its source references are checked against the analysis evidence.
- Plans are stored with server-side provider/provenance and content-hashed analysis snapshot identity. The proposal gate rechecks the stored plan and current snapshot.
- Proposal generation supports one exact synthetic repository/task/transformation and creates a deterministic diff in memory. It does not translate model text into patch content or write files.
- Mock is the application default. Nebius requires explicit opt-in; external requests are bounded. There is no automatic retry or provider fallback.
- Human approval remains required. Local review is disabled by default, limited to development and loopback, uses unverified labels, and stores bounded process-local records. Approval is not execution or merge authorization.
- Runtime validation reports `not_run`; the checked-out application has no trusted sandbox executor. Host execution and fallback are not available.
- Test configuration forces safe mock settings and blocks unmocked outbound network requests.

## Risks and limitations

| Severity | Risk | Current handling / remaining work |
|---|---|---|
| High | No authentication or multi-user authorization for the main local API | Bind only to loopback for the demo. Do not expose through a public interface or reverse proxy. Production requires authentication, authorization, and tenant isolation. |
| High | No trusted isolated runtime executor | Runtime remains `not_run`; do not interpret static syntax checks as tests. A separately reviewed, pinned, isolated Linux executor is required before execution can be considered. |
| High | Review identity and audit are not durable or verified | Labels are unverified local input; decisions/audit history are bounded process-local data and disappear on restart. This is not a tamper-proof audit log. |
| Medium | Repository prompt injection is mitigated by static context minimization but not semantically classified | README prose and source comments are not sent as full content in current planning context. Test markers ensure these contents do not enter the request. Future extractors must preserve this boundary and treat all repository-derived text as untrusted. |
| Medium | Model-authored plan prose can contain unsafe suggestions | Plans are validated structurally and cited, but prose is not a command policy engine. It is displayed as untrusted recommendation text; the proposal diff is separately fixed and allowlisted, and no execution route exists. Human reviewers must not copy/run suggested commands without independent review. |
| Medium | Scanner support is Python-focused and a bounded prototype | It does not provide exhaustive language/framework or semantic dependency analysis. Relevant-file ground truth is fixture-specific. |
| Medium | Nebius limits are per-process token/concurrency bounds, not spend caps | Multiple workers/processes can multiply in-flight capacity. There is no account-level dollar cap or pricing source. Use provider billing controls and one process for a live demo. |
| Medium | In-memory plans/proposals/reviews/handoffs are ephemeral | Restart or bounded-store eviction loses state; do not treat records as durable evidence. |
| Low | OS-dependent symlink test coverage | Windows may skip creating symlinks when privileges are unavailable. No `.github/workflows` CI is configured in this checkout, so Linux execution has not been verified. Add a suitable Linux CI job and require the escape test to run there. |
| Low | Mock quality is intentionally narrow | Mock results are deterministic scenario outputs, not model-quality evidence. Reports label them `provider=mock`, `is_mock=true`. |

## Adversarial behavior covered

The backend suite covers forged client metadata, tampered stored plan integrity, stale source and analysis snapshots, unsupported references and transformations, traversal and sensitive paths, malformed/truncated provider output, provider failures, review loopback and development restrictions, arbitrary runtime command fields, and the absence of a proposal apply route. Phase 7 tests additionally verify repository prompt-injection text is not forwarded and hostile model plan prose cannot alter the fixed proposal or trigger execution.

The existing symlink tests are platform-sensitive. On Windows, they skip if the process lacks the OS privilege required to create the fixture symlink. Since no Linux CI configuration is present, this checkout does not yet have verified Linux symlink-test evidence. Do not report the symlink escape test as passed when it was skipped.

## Before any public or execution-capable demo

Keep the demo local and read-only. Before exposing the API or adding execution, separately design and review authentication, authorization, CSRF/origin protections, durable audit and retention, cross-process rate/spend controls, a hardened isolated executor, cleanup verification, and incident handling. These are blockers for production or public exposure, not features implied by this prototype.
