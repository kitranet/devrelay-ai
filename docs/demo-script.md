# DevRelay AI demonstration script

For the final sub-three-minute public video, use [phase-8d-video-script.md](phase-8d-video-script.md) and the novice-oriented [Windows recording checklist](recording-checklist.md). That recording uses the synthetic fixture and deterministic mock provider. This API-level walkthrough remains the longer operator reference.

## Demonstration goal

Show a receiving engineer how DevRelay moves from an explicitly authorized repository to a traceable task plan, a fixed deterministic proposal, a human-review gate, and a handoff report. The proposal is a preview only. No code is applied or executed.

## Optional mode: separately authorized live Nemotron planning

This mode has one paid external model request only if the operator separately authorizes it. Repository analysis, proposal generation, review storage, and handoff generation are local deterministic application behavior. The model is not asked to generate a patch.

### Prerequisites

- Python 3.12+, project dependencies installed, and the synthetic fixture present.
- A valid Nebius Token Factory credential supplied locally through an approved secret mechanism. Never paste it into the terminal transcript, screenshots, chat, or demo recording.
- Billing and model access checked in provider controls. Token ceilings are not a dollar spending cap.
- Keep FastAPI bound to `127.0.0.1`; do not expose the development dashboard or review endpoints publicly.

Start the backend in PowerShell after setting the approved local environment values. Do not print the environment or key:

```powershell
Set-Location C:\devrelay-ai
$env:ENVIRONMENT = "development"
$env:INFERENCE_PROVIDER = "nebius"
$env:NEBIUS_PLANNING_DISABLE_THINKING = "true"
$env:NEBIUS_MAX_OUTPUT_TOKENS = "2048"
$env:NEBIUS_MAX_IN_FLIGHT_REQUESTS = "1"
$env:AUTHORIZED_REPOSITORIES = '{"planning-fixture":"C:/devrelay-ai/tests/fixtures/planning_repo"}'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The API key must already be available to that process. Do not `echo` it or put it in command history. For local human-review controls, set `ENABLE_LOCAL_REVIEWS=true` before backend startup; that enables unverified development-only review on loopback. It does not authorize code application or execution.

### Walkthrough

1. **Repository** — In the dashboard choose `planning-fixture`. Explain that the API accepts this configured ID, never a browser-supplied filesystem path.
2. **Analyze** — Run Repository intelligence. Show the calculator module, test module, imports, `requirements.txt`, and traceable AST source references. State that analysis is static and does not import repository code.
3. **Nemotron plan** — Enter: `Fix the division by zero defect in the calculator`. Submit once only after authorization. Expected provider metadata is `nebius` and the configured Nemotron model; if it says `mock`, stop and do not describe it as a live result. A failed or incomplete provider response is shown as an error; do not retry as part of the same authorized run.
4. **Evidence** — Inspect verified references and any unsupported references separately. A plan with unsupported evidence is not proposal-eligible. The plan remains `not_started` and requires human approval.
5. **Deterministic proposal** — Create the calculator proposal using the fixed `calculator-zero-denominator-value-error-v1` transformation. Explain that the returned unified diff is generated from a fixed allowlisted transformation, not authored or executed by Nemotron. Confirm lifecycle `awaiting_review`, approval required, and runtime `not_run`.
6. **Human review** — Present the diff, source/diff hashes, risks, and questions. The reviewer label is unverified local text. A person may record a justified local review decision when review controls are enabled, but the decision means further consideration only; it does not apply the diff. The prepared Phase 7C evaluation does not submit a review decision.
7. **Handoff** — Generate or download the Markdown handoff report. Point out provider provenance, verified evidence, deterministic proposal identity, human-decision state, unresolved questions, and runtime status `not_run`.

Do not click or invoke an apply/execute action. There is no supported apply endpoint and no trusted sandbox executor in this checkout.

### API request examples

Analysis:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/repositories/analyze `
  -ContentType 'application/json' `
  -Body '{"repository_id":"planning-fixture"}'
```

One planning request (paid only with explicit Nebius opt-in and a configured credential):

```powershell
$body = '{"repository_id":"planning-fixture","task_description":"Fix the division by zero defect in the calculator"}'
$plan = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/tasks/plan `
  -ContentType 'application/json' -Body $body
```

Proposal and handoff:

```powershell
$proposalBody = '{"repository_id":"planning-fixture","task_id":"' + $plan.task_id + '","transformation_id":"calculator-zero-denominator-value-error-v1"}'
$proposal = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/proposals/create `
  -ContentType 'application/json' -Body $proposalBody
$handoffBody = '{"proposal_id":"' + $proposal.proposal_id + '"}'
$handoff = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/handoffs `
  -ContentType 'application/json' -Body $handoffBody
```

## Offline fallback: deterministic mock

Use this fallback if Nebius access, billing, network, or model availability is unavailable. It makes no external requests and requires no credentials. Set the provider explicitly to avoid ambiguity:

```powershell
Set-Location C:\devrelay-ai
$env:ENVIRONMENT = "development"
$env:INFERENCE_PROVIDER = "mock"
$env:ENABLE_LOCAL_REVIEWS = "false"
$env:AUTHORIZED_REPOSITORIES = '{"planning-fixture":"C:/devrelay-ai/tests/fixtures/planning_repo"}'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Repeat the same repository, analysis, task, proposal, and handoff flow. Identify the plan as `provider=mock`, `is_mock=true`, model `devrelay-mock-v1`; never imply this is a Nemotron result. The deterministic mock supports only named synthetic scenarios. For a repeatable no-server evaluation, run `python -m scripts.phase7_evaluation` from the repository root; it uses a temporary fixture copy and emits the machine-readable report.

## Expected demo result

- Analysis sees Python modules, calculator tests, imports, and `requirements.txt` without executing fixture code.
- The plan identifies `package/calculator.py` and `tests/test_calculator.py` with verified references, subject to provider output validation.
- Proposal generation is eligible only for the exact fixture/task/transformation and current snapshot; it returns the fixed in-memory diff.
- The proposal remains `awaiting_review`, with `human_approval_required=true` and runtime validation `not_run`.
- Handoff preserves the originating provider, citations, proposal hashes, review state, risks, and remaining work.
- Original fixture file hashes remain unchanged.
