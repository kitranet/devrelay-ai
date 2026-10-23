# Phase 7A — End-to-End Engineering Handoff Audit

Audit baseline: branch `devrelay-phase6-nebius`, commit `aa6efc0b13615e92eac0f33c7ab82861be9bc955`.

This document records source- and test-backed behavior in this checkout. It is an audit artifact, not a claim that roadmap items are implemented. No live inference, review decision, proposed-code execution, or repository mutation was performed as part of this audit.

## Executive assessment

The read-only analysis and evidence-backed planning path is implemented and has useful offline coverage. The calculator proposal/review/handoff path is a deliberately narrow synthetic demonstration: proposal generation is deterministic and only accepts a mock plan. Human review is a loopback-only development prototype with unverified labels and process-local records. Runtime validation is not operational: the production executor is unavailable and fails closed. Consequently, the most convincing safe demo today is static analysis → a grounded plan → deterministic mock-only proposal → optional local review → generated handoff report, with runtime status honestly shown as `not_run`. A live Nemotron plan can be demonstrated separately, but cannot currently be continued into proposal generation.

## Capability inventory

| Capability | Status | Evidence and limits |
|---|---|---|
| Authorized repository selection | Implemented; tested | API requests contain repository IDs, resolved only through `AUTHORIZED_REPOSITORIES`; the client cannot supply a path. `app/core/config.py`, `app/api/routes/repositories.py`, `tests/test_repository_analysis.py`, `tests/test_repository_api.py`. |
| Repository ingestion | Implemented as bounded local scanning; not an upload/clone pipeline | Scanner walks configured roots and emits metadata; it does not ingest GitHub repositories or persist snapshots. `app/services/repository_analysis.py`. |
| Python structure extraction | Implemented; tested | Uses `ast.parse` to emit modules, functions/classes and import relationships without importing or executing target code. Malformed Python produces warnings. `app/services/repository_analysis.py`, `tests/test_repository_analysis.py`. |
| Dependency identification | Partially implemented; tested | Reads recognized dependency manifests as data and returns manifest entries. This is manifest discovery, not package resolution, vulnerability analysis, or a complete transitive dependency graph. `app/services/repository_analysis.py`; dashboard renders imports/manifests in `frontend/src/components/dashboard.tsx`. |
| Tests/configuration/README discovery and file metadata | Implemented; tested | Scanner classifies paths and emits size/time metadata, test/readme/config paths and warnings. No test suite from a target repository is run. `app/models/repository.py`, `app/services/repository_analysis.py`. |
| Evidence references | Implemented; tested | Plans can retain only analyzed file paths and exact analyzed symbol/import references; duplicate citations are deduplicated and rejected citations are separated, downgrade status to `insufficient_context`, and appear as unverified in the UI. `app/services/task_planning.py`, `tests/test_task_planning.py`, `frontend/src/components/dashboard.tsx`. |
| Task planning | Implemented with two distinct modes | Mock is deterministic and limited to named synthetic scenarios (`app/services/mock_inference.py`, `tests/test_mock_provider.py`). Nebius/Nemotron is a real configurable provider, explicit opt-in, bounded and structured-output validated (`app/integrations/nebius.py`, `app/services/inference.py`, `app/services/task_planning.py`). It is not the default and no live call was made for this audit. |
| Proposal generation | Narrow deterministic simulation, not general AI code generation | Only the predefined calculator task/target is accepted; only a planned mock result qualifies. A fixed diff is created in memory after source-hash, path, diff, AST and acceptance checks. It is never written/applied/executed. `app/services/proposal_generation.py`, `tests/test_proposals.py`. |
| Human approval/review | Partial local prototype | Disabled by default; development-only and loopback-restricted. Labels are unverified; decisions are bound to version/source/diff hashes and justification. Approval means further consideration only. Records are bounded process memory, not durable/tamper-proof. `app/services/review_workflow.py`, `app/api/routes/reviews.py`, `tests/test_reviews_handoffs.py`. |
| Engineering handoff | Implemented for stored synthetic proposal flow | Re-analyzes current static repository and combines stored plan, proposal, review, warnings and runtime status. It does not call a model; records disappear on restart/eviction. `app/services/handoff_reports.py`, `tests/test_reviews_handoffs.py`. |
| Runtime validation | Interface and authorization workflow only; execution unavailable | Fixed IDs/paths and approval/hash checks exist. The configured `UnavailableSandboxExecutor` always fails closed; no trusted sandbox is present and no host code is run. A test fake is orchestration simulation only. `app/services/runtime_validation.py`, `tests/test_reviews_handoffs.py`. |
| Dashboard | Implemented local workflow UI; not a team product | Next.js UI supports workspace choice, analysis, planning, proposal, review, runtime readiness/evidence and Markdown handoff export through an allowlisted backend proxy. No identity provider, collaboration, durable workspaces, or production auth. `frontend/src/components/dashboard.tsx`, `frontend/src/lib/api.ts`, `frontend/src/app/api/backend/[...path]/route.ts`. |

## End-to-end calculator journey

| Stage | Result in this checkout |
|---|---|
| 1. Select and authorize repository | Configure `planning-fixture` to `tests/fixtures/planning_repo`; UI submits the ID. Unknown IDs are denied. |
| 2. Analyze | `POST /api/v1/repositories/analyze` scans statically. The fixture contains calculator/API/service modules, dependencies, imports, and tests. The dashboard shows files, symbols, imports/manifests and warnings. |
| 3. Find relevant code | Static AST evidence exposes `package/calculator.py` and the `divide` function, along with the corresponding calculator test path. It does not infer runtime behavior by running the fixture. |
| 4. Submit task | `POST /api/v1/tasks/plan` with `{"repository_id":"planning-fixture","task_description":"Fix the division by zero defect in the calculator"}`. |
| 5. Generate plan | Mock mode returns deterministic fixture output; explicit Nebius mode calls the configured Nemotron model. Prior authorized live testing reported a planned result, but the audit itself made no provider call. |
| 6. Validate plan | Provider content must be complete JSON and pass `PlanGeneration` Pydantic validation; then references/files are checked against the analysis. Unsupported references are not shown as verified and force `insufficient_context`. |
| 7. Display plan | UI displays status, provider/model, usage/latency where present, relevant files, citations, steps, risks, validation, expected changes, approval requirement and `not_started`. Unsupported citations are labeled unverified. |
| 8. Proposal and review transition | Proposal generation is enabled only for a `planned`, mock, predefined calculator result. **A live Nebius plan cannot enter proposal generation** (`ProposalGenerationService.create` rejects non-mock plans). This is the key demo continuity gap if the presentation expects a Nemotron plan to flow into the proposal/review/handoff screens. Review remains separately disabled unless explicitly enabled locally in development. |
| 9. Final behavior | Proposal is an in-memory fixed diff with static checks; no file changes or execution. Review approval is not apply authorization. Runtime is reported `not_run`/`sandbox_unavailable`; no trusted executor exists. Handoff report is generated from stored records and current static analysis. |

## Critical demo gaps and risk register

Severity here means demo/release impact in this local prototype, not a claim of exploitable production deployment.

| Severity | Finding | Evidence / impact | Recommended treatment |
|---|---|---|---|
| High (demo continuity) | Live Nemotron plan cannot be continued into proposal/review/handoff | Proposal service explicitly requires `provider=mock` and `is_mock=true`. The UI correspondingly shows proposal action only for mock plans. A demo must present live planning and mock proposal as separate scenarios, or the scope must be reviewed for a safe linkage. Do not remove the guard casually: proposal generator is a fixed deterministic fixture path, not a general model-generated patch validator. |
| High (deployment security) | Main API has no user authentication/authorization identity | Repository IDs constrain roots, but are not user access control. Setup documentation says keep API on trusted local interface and states authentication is absent. Exposing the backend beyond localhost could expose authorized repository analysis/planning. Keep demo loopback-bound; add authentication before shared/network deployment. |
| High (execution readiness) | No actual trusted runtime executor | Production executor reports unavailable and never launches. UI/docs correctly say `not_run`; presenting a test as passed would be false. Leave execution unavailable until a separately reviewed sandbox implementation and immutable image are verified. |
| Medium | Review, plan, proposal and handoff stores are process-local | Restart/eviction loses the records; audit is not durable or tamper-proof. Fine for a short demo, unsuitable as a durable engineering workflow. |
| Medium | Repository-derived metadata and task text are untrusted prompt input | Raw source files are not put in the prompt, which reduces exposure, but task text and paths, symbol/import names, dependency manifest values and warnings are still context. Provider output is validated structurally and for references, not proven semantically safe or correct. Treat all generated descriptions as proposals for human inspection. |
| Medium | Scanner's real OS symlink escape test can be skipped on Windows | `tests/test_proposals.py::test_symlink_escape_target_is_rejected` catches Windows privilege errors and skips. Scanner symlink/junction logic has separately mocked coverage, but the OS-level symlink behavior needs a CI job that can create symlinks. Run the relevant suite in Ubuntu CI; retain Windows coverage for junction/path behavior. Enabling Windows Developer Mode or granting symlink privilege can also permit a local run. |
| Medium | Provider cost is not a hard account-level cap | App bounds estimated prompt size, completion tokens, timeout and per-process in-flight requests; no retry/fallback exists. Token estimates are heuristic and ceilings are not dollar limits. Use provider-side billing limits; never infer a dollar cap from app settings. |
| Low | Documentation gives a setup-time output default that is easy to confuse with prior live-test overrides | `docs/setup.md` states default `NEBIUS_MAX_OUTPUT_TOKENS=1024`; code agrees. Prior live requests used a process override of 2048. The effective value is environment-dependent, so a demo operator should record effective startup configuration without printing secrets. |

Security controls verified in code/tests include configured-ID-only repository access, bounded static scanner, AST-only parsing, skipped symlinks/junctions, sensitive/generated path exclusions, sanitized provider errors, test network isolation, no automatic inference retry/fallback, Pydantic/evidence rejection, fixed proposal path and source hash, review hash/version checks, fixed runtime IDs, and fail-closed unavailable executor. These controls reduce risk but do not make this prototype production-authenticated or sandbox-ready.

## Repeatable evaluation plan

Run these against copied synthetic fixtures; never execute the fixture source as part of model-provider tests. Store raw prompts/responses only in a deliberately secured evaluation environment if ever needed; ordinary CI should retain sanitized metrics and synthetic outputs only.

| ID / case | Automated measurement and pass condition | Human review / notes |
|---|---|---|
| E1 Calculator zero-divisor task | Plan Pydantic-valid; target `package/calculator.py`; identifies `divide`; includes test path; valid citations only; mandatory approval and execution `not_started`. | Score whether it notices the desired zero-divisor behavior is unspecified and asks/records that assumption instead of inventing product behavior. |
| E2 API validation task | Relevant API module and API test file covered; all citations in static analysis; schema valid. | Judge whether the proposed validation behavior is appropriate to stated task and existing conventions. |
| E3 Service/dependency investigation | Target service and imported dependency identified; test path included; relevant manifest/import coverage measured. | Judge whether dependency impact is explained without claiming transitive resolution. |
| E4 Unknown/ambiguous task | Expected `unsupported` or `insufficient_context`, no invented files/steps or unsupported citation. | Confirm explanation is actionable. |
| E5 Empty/non-Python repository | `insufficient_context`, no model-invented modules. | Check clear user-facing reason. |
| E6 Citation adversarial cases | Exact analyzed citation accepted; nonexistent path, wrong line/range rejected; duplicates deduplicated; partial validity yields verified/rejected separation and downgrade. | Inspect whether UI makes rejected evidence visually unmistakable. |
| E7 Approval/execution boundaries | Every plan requires human approval and has `not_started`; proposal awaits review; no apply endpoint; unavailable sandbox returns no claim of test execution. | Confirm labels distinguish review approval from execution authorization. |
| E8 Repository immutability | Hash/tree snapshot before and after analysis, plan, proposal, review, handoff remains unchanged. | Confirm no generated artifacts land inside fixture. |
| E9 Provider reliability | Offline HTTPX mock cases for success, HTTP error, timeout, truncated/malformed JSON; exactly one transport attempt and no mock fallback after Nebius failure. | Review sanitized diagnostics. Do not use genuine provider calls in CI. |
| E10 Cost/latency | Record provider-reported input/output/reasoning/total tokens, measured latency, model/provider, response validation, and estimate cost only when an authoritative rate is configured. | Cost must be labeled estimated; report unavailable when current price cannot be verified. Never report estimate as a billed amount. |

### Metric definitions

- **Plan completeness**: count of predefined expected outcomes met divided by the rubric total; separately report each item, rather than presenting one score alone.
- **Citation precision**: validated returned citations / all returned citations; also report unsupported-reference count. If no citations were returned, precision is `N/A`, not 100%.
- **Relevant-file coverage**: expected relevant fixture paths identified / expected paths. Report precision and recall separately to expose irrelevant files.
- **Dependency coverage**: expected direct import/manifest facts surfaced / expected facts. This does not measure transitive dependency resolution.
- **Schema validity**: Pydantic acceptance boolean, plus sanitized error category on rejection.
- **Gate compliance**: assertions that approval is required, execution remains `not_started`, no write/apply/execute route was used, and fixture hash is unchanged.
- **Unsupported/insufficient-context handling**: expected status and no invented references for each negative case.
- **Performance/cost**: measured latency and provider-reported token usage. Cost is computed as `input_tokens * verified_input_rate + output_tokens * verified_output_rate`; reasoning billing treatment/rates must follow the provider's current pricing schedule. If rate or token class is uncertain, report cost as unavailable. Mock runs have no provider latency/cost benchmark meaning.

Automated measurements are appropriate for schema, exact file/reference gates, state transitions, no-write invariance, provider retry count and diagnostics. Plan quality, usefulness, clarity, risk completeness, and whether the assumption handling is appropriate require a small human rubric and ideally two reviewers. Do not call synthetic deterministic mock outputs benchmark results for Nemotron.

## Demo scenario and expected outputs

**Scenario:** “Fix the division by zero defect in the calculator.” Use only `planning-fixture` mapped to `tests/fixtures/planning_repo`.

1. Show the authorized repository ID and run static analysis. Expected: calculator module/function, imports, dependency manifest, test files and traceable source lines; no repository code execution.
2. Submit the task above. For an offline/repeatable demo use mock and visibly label the output as deterministic mock, not Nemotron. For a separate live-model segment, explicitly opt in and show provider/model/token/latency diagnostics; do not imply this live plan can create the current mock-only proposal.
3. Inspect relevant files, plan steps, proposed changes, risks, validation items and verified citations. Expected live outcome from prior user-authorized run was `planned`, five verified references, zero unsupported, four steps and two proposed changes; this is historical evidence, not a new measurement in this audit.
4. In the mock scenario only, create the fixed proposal. Expected: one in-memory diff for `package/calculator.py`, source hash and static checks passed, lifecycle `awaiting_review`, approval required, runtime `not_run`; fixture file unchanged.
5. If local review has deliberately been enabled for development, record a pseudonymous unverified label and justification. Explain that “approve” means further consideration only.
6. Generate and export the handoff report. Expected: static analysis, plan/proposal, decision if present, questions/risks, and runtime explicitly not run.
7. Close by stating no code was applied or executed and no trusted sandbox is configured.

## Phase 7B / 7C priorities

### Phase 7B — Demo reliability and evaluation (recommended next)

1. Add an offline end-to-end acceptance test over the dashboard/API mock path, including fixture immutability and all transition states.
2. Publish the evaluation rubric and machine-readable expected outcomes for the three existing synthetic scenarios; produce a small sanitized report with no fabricated live metrics.
3. Resolve demo continuity intentionally: either present the live Nemotron plan and deterministic mock proposal as separate labeled flows, or design a separately reviewed proposal eligibility contract that does not imply arbitrary model-generated patches are safe. Do not simply remove the mock-only guard.
4. Add/verify Linux CI for the real symlink escape test and full backend/frontend checks; keep Windows-specific validation too.
5. Clarify effective live configuration and operator checklist (provider, model, thinking flag, tokens, timeout, concurrency) without exposing credentials; keep mock the default.

### Phase 7C — only after demo and threat-model review

1. Add authenticated identity and authorization before any shared or non-loopback deployment; keep reviewer labels explicitly unverified until identity is real.
2. If durable handoffs are required, design bounded persistent storage, retention, access control and audit integrity; current in-memory stores are prototype-only.
3. Build a separately reviewed, fail-closed Linux sandbox executor with immutable verified image digest, no credentials/network, read-only source snapshot, strict resource limits, cleanup verification and adversarial tests. Do not enable runtime execution before this exists.
4. Expand repository language/dependency support only with bounded parsers, provenance and tests; avoid broad architectural redesign until evaluation demonstrates need.

## Validation record

Fresh offline validation on 2026-10-23:

- Backend: `C:\\devrelay-ai\\.venv\\Scripts\\python.exe -m pytest -q` — **120 passed, 1 skipped, 1 warning**. The skipped test is the OS-level proposal symlink-escape test because this Windows process lacks symlink creation privilege (`WinError 1314`). Warning: Starlette `TestClient` uses the deprecated `anyio.abc.BlockingPortal` alias.
- Frontend: `npm.cmd test` — **3 test files passed, 27 tests passed**.
- Frontend lint: `npm.cmd run lint` — passed.
- Frontend typecheck: `npm.cmd run typecheck` — passed.
- Frontend production build: `npm.cmd run build` — passed. Next.js reported its existing `frontend/.env.local` as an environment file; its contents were not inspected or reported. The build generated normal ignored `.next` output.
- Live Nebius calls, backend server startup, plan approval and code execution: **not performed**.

The only intended working-tree addition is this audit document. `git diff --check` and final `git status` are recorded in the completion report. Previous committed-baseline notes are not substituted for this fresh test run.
