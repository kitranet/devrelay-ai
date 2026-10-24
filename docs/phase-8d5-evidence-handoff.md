# Phase 8D.5 — Evidence-grounded plan and plan-only handoff

This extension adds bounded source excerpts to the existing structured planner
and a plan-only review/handoff path for the synthetic continuity-pipeline
incident. It does not add a general code proposal for that repository.

## Local offline evaluation

Use the synthetic fixture ID `continuity-pipeline-fixture`. Run
`python -m scripts.phase8d4_evaluation` to refresh the static-analysis report.
It selects evidence without calling the inference service. The complete backend
suite includes mocked provider and API tests for excerpt safety, source hashes,
strict citations, stale-plan rejection, review integrity, and plan-only report
state.

The deterministic mock has an explicit generic continuity scenario so the UI
can exercise the workflow offline. It is labeled as mock and does not diagnose
source behavior. Do not describe its output as Nemotron reasoning.

## One later live planning request

The exact neutral prompt is in `docs/continuity-pipeline-incident.md`. The
current configured live model is `nvidia/Nemotron-3_5-Lightning`. The existing
configuration remains bounded: 6,000 estimated prompt tokens, 1,024 completion
tokens, a 30-second provider timeout, one in-flight request, and no automatic
retry or provider fallback. Thinking is disabled for the prepared Nemotron
scenario (`NEBIUS_PLANNING_DISABLE_THINKING=true`). Live requests require both explicit provider selection and
the independent live-inference switch; durable SQLite request quota must have
one remaining reservation. Those request counts are not dollar spending caps.

A separate live test has not been authorized or run as part of this phase. Do
not run the script below until the user explicitly authorizes that particular
request. Do not put the ground-truth document in the prompt. The script refuses
unless an additional one-run confirmation variable is set and its provider and
quota preflight succeeds:

```powershell
Set-Location C:\devrelay-ai
$env:DEVRELAY_LIVE_DEMO_AUTHORIZED = 'YES'
node .\frontend\scripts\record-continuity-live-demo.mjs
```

The backend script inherits `NEBIUS_API_KEY` from the local process but does
not print it or pass it to the frontend build/server. It uses only the
continuity fixture, loopback listeners, a generated temporary Basic Auth
password, and a fresh one-request quota file under the ignored local state
directory. The video must be checked for actual provider/model labels and
verified evidence before use. A failed or insufficient-context response is
retained as an honest partial recording and is never retried.

The script's single paid operation is `POST
http://127.0.0.1:8001/api/v1/tasks/plan` for the request in the incident brief.
The dashboard sends it through the authenticated local Next.js proxy. The
bounded settings are the existing 6,000 estimated prompt tokens, 1,024
completion tokens, 30-second provider timeout, one in-flight request, and one
durable request reservation. It does not raise limits or treat quota as a
dollar cap.

## Handoff and safety semantics

A handoff generated before a review decision is labeled `awaiting human
review`. Development-only local review records a decision about the plan only;
reviewer identity is not verified. The report stays process-local and is not a
durable audit record. No proposal, patch, merge, deployment, or execution is
part of the continuity workflow. Runtime validation is `not_run`.
