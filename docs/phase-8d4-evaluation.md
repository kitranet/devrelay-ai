# Phase 8D.4/8D.5 continuity-pipeline evaluation

## Scenario and trust boundary

The Northstar nightly-reporting scenario is synthetic and is located in
`tests/fixtures/continuity_pipeline`. The judge-facing symptom and request are
in [the incident brief](continuity-pipeline-incident.md). Keep
[the evaluator ground truth](continuity-pipeline-ground-truth.md) outside the
model context. It describes the expected unused validity threshold and
unconditional publication behavior; the planner must discover any such facts
from supplied source excerpts rather than from the evaluator document.

The incident request asks the planner to trace orchestration, validation,
transformation, retry, configuration, and publishing; distinguish observed
facts from hypotheses; and recommend evidence collection and regression
checks. The application does not execute the fixture or apply code changes.

## Implemented workflow

- The configured-ID scanner performs bounded static analysis and discovers
  Python modules, symbols, imports, dependency manifests, tests, and file hashes.
- The planner selects bounded excerpts from analyzed Python function/class
  ranges, attaches exact paths, line ranges, content hashes, and checks their
  source snapshot before use. The default cap is seven files, 7,000 total
  characters, 2,000 characters per file, and 60 lines per excerpt.
- Repository text and task descriptions are treated as untrusted evidence.
  Instructions inside code, comments, strings, and documentation are explicitly
  ignored by the planner prompt. Sensitive-looking excerpts are excluded.
- Structured plans include relevant files, citations, findings marked observed
  or suspected, unresolved questions, risks, and next steps. References are
  checked against the analyzed symbol/import map or exact supplied excerpts.
  Unsupported citations are rejected/downgraded and cannot appear as verified
  evidence.
- A plan-only handoff can be created from a server-stored plan after validating
  its digest, provider provenance, source hashes, and current analysis snapshot.
  It includes evidence hashes, findings, questions, next steps, and validation
  recommendations. It contains no code diff.
- A loopback-only, development-only plan review can record acknowledge,
  request-changes, or reject. Reports remain labeled awaiting review until a
  decision exists. Reviewer labels are unverified and state is bounded,
  process-local prototype data.
- The deterministic code proposal remains calculator-only. Runtime validation
  remains `not_run`; no target repository code is executed or modified.

## Offline evaluation

Run the static evaluation and tests with an isolated test environment:

```powershell
Set-Location C:\devrelay-ai
$env:INFERENCE_PROVIDER = 'mock'
$env:NEBIUS_LIVE_INFERENCE_ENABLED = 'false'
$env:NEBIUS_API_KEY = ''
.\.venv\Scripts\python.exe -m scripts.phase8d4_evaluation
.\.venv\Scripts\python.exe -m pytest -q
```

The machine-readable report is
[`docs/evaluation/phase-8d4-results.json`](evaluation/phase-8d4-results.json).
The runner makes no model or task API request. It measures fixture-specific
static file coverage, deterministic excerpt selection, character budgets,
location/hash availability, and fixture immutability. It does not score model
reasoning. Offline tests cover path traversal, symlink/source changes, sensitive
excerpt exclusion, prompt-injection isolation, citation validation, plan
integrity, handoff creation, review state, and calculator regression behavior.

Relevant-file coverage against the five manually defined core files is a
fixture-specific measure only. Citation precision, root-cause quality,
investigation completeness, live latency, token usage, and cost cannot be
measured with the mock. A real plan requires separate explicit authorization
for exactly one request, with quota storage and provider checks in place.

## Live test boundary

A prepared live-recording script is
[`frontend/scripts/record-continuity-live-demo.mjs`](../frontend/scripts/record-continuity-live-demo.mjs).
It requires `DEVRELAY_LIVE_DEMO_AUTHORIZED=YES`, an already configured secret,
Nebius explicit opt-in, and one available durable request quota. The script
refuses to run unless preflight reports the expected provider, model access,
and exactly one remaining request. It submits one planning request and does
not retry or fall back. Do not run it without fresh authorization for that
specific request. Its output is a genuine-provider recording only if the API
response itself reports Nebius and the configured model.

The existing calculator recorder remains a separate, explicitly mock-mode
fallback. Never splice calculator mock output or historical Nemotron metrics
into the continuity live recording.
