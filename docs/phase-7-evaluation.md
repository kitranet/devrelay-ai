# Phase 7 end-to-end evaluation

## Scope and method

This evaluation covers the synthetic Python calculator fixture only. The repeatable run uses the configured deterministic `mock` provider and a temporary copy of `tests/fixtures/planning_repo`; it makes no external requests and does not import or execute fixture files. The runner is `scripts/phase7_evaluation.py`, and its machine-readable output is `docs/evaluation/phase-7-results.json`.

The workflow checks authorized repository analysis, dependency-manifest discovery, a structured plan, explicit mock provenance, verified citations, plan completeness against a small manual ground truth, the deterministic allowlisted proposal, the review gate, diff presentation, handoff generation, honest `not_run` runtime reporting, and byte-for-byte repository immutability. Ground truth for relevant-file coverage is deliberately narrow and explicit: `package/calculator.py` and `tests/test_calculator.py`. Coverage is the fraction of those two files included in the plan; it is not a general relevance benchmark. Citation accuracy is verified plan citations divided by verified plus unsupported citations.

## Evaluation checkpoints

| Area | Automated evidence | Measurement |
|---|---|---|
| Repository authorization and analysis | Repository API tests and offline workflow runner | Analyze response and synthetic repository identity |
| Dependencies | Static-analysis tests and workflow runner | `requirements.txt` discovered; manifest contents remain source-derived |
| Plan completeness | Deterministic mock scenario plus manual expected outcomes | Zero-denominator behavior, a focused regression test, and calculator-test validation are expected |
| Schema and evidence | Planning tests and Pydantic parse in runner | Schema-valid plan; exact analyzed citations; unsupported count |
| Provenance and snapshot | Proposal tests | Forged metadata, altered stored metadata, and stale whole-repository snapshot rejected |
| Proposal eligibility | Proposal tests | Only the named fixture, exact task, and fixed transformation qualify |
| Review boundary | Review/handoff tests and workflow runner | Proposal stays `awaiting_review`; approval remains required; review routes are disabled by default and loopback-only when enabled |
| Immutability/execution | Proposal tests and workflow runner | Fixture hashes unchanged; apply route absent; runtime remains `not_run` |
| Provider failure | Nebius and planning tests | Timeout, API failure, malformed/truncated response; no retry or fallback |
| Adversarial repository content | Phase 7 evaluation tests | README prompt-injection marker is not forwarded as model context; static scanner does not execute it |
| Hostile plan prose | Phase 7 evaluation tests | Arbitrary execution instruction remains untrusted plan text and is never copied into the deterministic proposal or executed |
| Path/symlink controls | Scanner and proposal tests | Traversal rejected; escape symlink test is skipped on Windows when OS symlink creation is unavailable |
| Local-review authorization | Review tests | Disabled-by-default and development/loopback enforcement |

The backend suite also exercises additional API, model, repository scanner, and test-network-isolation cases. See the final run report for actual counts; do not interpret a test count as a model-quality score.

## Results and metrics

`docs/evaluation/phase-7-results.json` records the last actual offline mock workflow run and maps adversarial cases to their backend test names. The mock section reports workflow elapsed time only; the mock provider does not supply model latency, token counts, or cost, so those fields are null. The complete-suite counts below come from the actual validation commands, not the runner's 14 workflow checkpoints.

Validation snapshot for 2026-10-23:

- Backend: `python -m pytest -q --basetemp=.pytest-tmp-phase7c` — 130 passed, 1 skipped, 0 failed; one Starlette/AnyIO `BlockingPortal` deprecation warning.
- Frontend Vitest: 27 passed, 0 failed.
- ESLint, TypeScript typecheck, and Next.js production build: passed.
- `git diff --check`: passed; Git emitted only the existing LF-to-CRLF conversion warnings.
- No live Nebius request was made. The proposal-target symlink test skipped because Windows returned `WinError 1314`; scanner symlink behavior also has a simulated-entry test.

The following live inference metrics are preserved as a historical user-provided Phase 6B.2 observation. They were not reproduced in this evaluation and must not be presented as measurements of the mock run:

- Model: `nvidia/Nemotron-3_5-Lightning`
- Input/output/reasoning tokens: 1,349 / 381 / 0
- Latency: 2,823 ms
- Citations: 5 verified, 0 unsupported
- Estimated cost: `$0.00017238`

The cost is the supplied estimate, not a billing statement. There is no account-level dollar cap in the application. This Phase 7 evaluation made zero Nebius requests.

## Repeat the offline evaluation

From the repository root in PowerShell:

```powershell
$env:INFERENCE_PROVIDER = "mock"
$env:ENABLE_LOCAL_REVIEWS = "false"
Set-Location C:\devrelay-ai
.\.venv\Scripts\python.exe -m scripts.phase7_evaluation
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-phase7c
```

The runner constructs explicit settings with `_env_file=None`, mock inference, no key, and a temporary authorized fixture. It prints JSON to stdout, writes `docs/evaluation/phase-7-results.json` by default, and exits nonzero if a workflow checkpoint fails. Run backend pytest in a normal PowerShell process outside the restricted Codex Windows sandbox: the sandbox can block local asyncio/socketpair behavior. The repository's `tests/conftest.py` overrides inherited provider/key settings and blocks unmocked external network requests. `.pytest-tmp-phase7c` is a disposable local test directory ignored by Git.

Frontend checks, when validating a checkout with frontend changes, are:

```powershell
Set-Location C:\devrelay-ai\frontend
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

## Interpretation and limitations

- This measures contract behavior and deterministic synthetic coverage, not the semantic quality of Nemotron output.
- The 14 workflow checkpoints are API-level tests through FastAPI's local test client, not a browser-driven full-stack E2E run. The 27 frontend tests are Vitest component/library tests; no Playwright/browser automation is configured.
- One fixture cannot establish broad language, framework, or repository support.
- Relevant-file coverage ground truth is manually defined for this task; human review is still needed for whether the plan is technically appropriate.
- The review system is a local prototype with unverified identity and in-memory history.
- There is no trusted sandbox; no runtime tests are executed by proposal generation or the handoff workflow.
- No `.github/workflows` configuration exists in this checkout. The Windows symlink-escape test can be skipped if the host cannot create symlinks; Linux CI coverage remains unresolved until a suitable CI runner is configured and the test is observed passing there.
