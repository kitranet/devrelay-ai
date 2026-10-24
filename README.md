# DevRelay AI

An open-source engineering handoff agent with configurable Nebius-hosted NVIDIA Nemotron planning. The Python backend provides bounded static repository analysis, evidence-backed task planning, and a deterministic, human-reviewable calculator code proposal. Proposals are not applied and repository code is not executed.

## Quick start

Use Python 3.12 or newer and Node.js/npm for the dashboard. DevRelay is configured for local use: FastAPI listens on `127.0.0.1:8001`, and Next.js must be explicitly bound to `127.0.0.1:3000`. The application defaults to deterministic mock inference; live Nebius requests require explicit provider selection and a separate kill switch. The dashboard fails closed unless server-only Basic Authentication credentials and an exact `DEMO_AUTH_ORIGIN` are configured. Follow the Windows-specific [setup and production preflight](docs/windows-hosting.md); general dependency and API details are in [docs/setup.md](docs/setup.md).

The health check is available at `http://127.0.0.1:8001/health`. Repository analysis is available at `POST /api/v1/repositories/analyze`, and planning at `POST /api/v1/tasks/plan`; configure only authorized repository IDs as described in [docs/setup.md](docs/setup.md). API docs are available locally at `/docs` on the backend and must not be publicly exposed.

Phase 4B adds `POST /api/v1/proposals/create` for the predefined division-by-zero calculator task and `GET /api/v1/proposals/{proposal_id}` to retrieve a review-only proposal. Phase 7B allows either a server-validated mock or Nebius plan to continue only when its integrity, provider provenance, evidence and content-hashed analysis snapshot are verified. The proposal remains one deterministic, allowlisted in-memory diff; model output is never translated into code. Static checks use unified-diff validation and Python AST parsing. Runtime validation reports `not_run` because no trusted sandbox is configured. No proposal endpoint applies code.

Phase 5A adds a disabled-by-default local review workflow and evidence-based handoff reports. Set `ENABLE_LOCAL_REVIEWS=true` only in development to enable loopback review requests. Reviewer labels are unverified, and an approval only accepts a proposal for further consideration; it does not apply code. Review and report storage is process-local and non-durable. See [docs/setup.md](docs/setup.md) for safe local demonstration steps.

Phase 5B adds a separately disabled, loopback-only runtime-validation authorization and evidence workflow for the fixed synthetic calculator proposal. The current checkout has no trusted sandbox executor, so readiness fails closed and authorized attempts return `sandbox_unavailable`; **no repository tests or code are run**. Do not enable this feature expecting execution. See [docs/setup.md](docs/setup.md) and [docs/architecture.md](docs/architecture.md) for the threat model and current limits.

For offline planning, set `INFERENCE_PROVIDER=mock`. The deterministic mock supports only named synthetic evaluation scenarios; unsupported requests return an explicit unsupported result. It does not represent NVIDIA Nemotron output.

Phase 6B adds an explicitly opted-in Nebius planning provider. The application defaults to mock even when an API key is configured; use `INFERENCE_PROVIDER=nebius` only after checking billing controls. Requests are bounded by prompt/output token limits and one in-flight call per process. Truncated or malformed answers are rejected, and successful plans expose only safe model, latency, and token-usage metadata. No automatic retry, mock fallback, code application, or repository execution is added. See [docs/setup.md](docs/setup.md) for the separately authorized smoke-test command; it has not been run as part of implementation.

## Local dashboard

The Next.js dashboard lives in `frontend/`. Configure only the synthetic repository in the backend. The dashboard fails closed unless server-side `DEMO_AUTH_USERNAME`, `DEMO_AUTH_PASSWORD`, and exact `DEMO_AUTH_ORIGIN` values are set. Keep both services bound to loopback and open the exact configured origin. See the [Windows hosting runbook](docs/windows-hosting.md) for separate development and production-mode startup, and [docs/deployment.md](docs/deployment.md) for the Linux-only Nginx/systemd proposal. No public tunnel has been created or enabled.

## Project docs

- [Architecture](docs/architecture.md)
- [Setup and testing](docs/setup.md)
- [Agent instructions](AGENTS.md)
- [Phase 7 evaluation and measured results](docs/phase-7-evaluation.md)
- [Repeatable demo script](docs/demo-script.md)
- [Timed Phase 8D video storyboard and narration](docs/phase-8d-video-script.md)
- [Windows recording and YouTube checklist](docs/recording-checklist.md)
- [Security limitations](docs/security-limitations.md)
- [Phase 8B deployment and judge guide](docs/deployment.md)
- [Phase 8D.4 continuity scenario and evaluation limits](docs/phase-8d4-evaluation.md)
- [Phase 8D.5 evidence-grounded plan and handoff runbook](docs/phase-8d5-evidence-handoff.md)
- [Synthetic incident brief](docs/continuity-pipeline-incident.md)
- [Evaluator ground truth](docs/continuity-pipeline-ground-truth.md)
- [Phase 8D.4 video storyboard](docs/phase-8d4-video-storyboard.md)

## Phase 8D.4 continuity scenario

The synthetic Northstar nightly-reporting fixture is a separate multi-file
Python repository for evaluating cross-module analysis. Configure its absolute
path under `continuity-pipeline-fixture` in `AUTHORIZED_REPOSITORIES` before
selecting it in the dashboard. The neutral request is in
`docs/continuity-pipeline-incident.md`; keep evaluator ground truth out of the
model prompt. Run `python -m scripts.phase8d4_evaluation` for offline static
analysis and bounded excerpt-selection measurements. The deterministic mock
can exercise the plan-only interface, but it does not interpret source
semantics and is not evidence of Nemotron reasoning. A plan-only handoff and
plan review are now supported; both remain unreviewed until a local reviewer
records a decision. Reviewer labels are unverified and data is process-local.
The deterministic proposal remains calculator-only. A future genuine plan
requires separate authorization for one live request and the existing durable
quota controls. See the [Phase 8D.5 runbook](docs/phase-8d5-evidence-handoff.md)
and [continuity storyboard](docs/phase-8d4-video-storyboard.md).

## Phase 7 demo and evaluation

Run the offline end-to-end evaluation against a temporary copy of the synthetic calculator fixture with the deterministic mock provider:

```powershell
Set-Location C:\devrelay-ai
.\.venv\Scripts\python.exe -m scripts.phase7_evaluation
.\.venv\Scripts\python.exe -m pytest
```

The evaluation JSON is checked in at `docs/evaluation/phase-7-results.json`. Mock metrics are kept separate from the historical live Nemotron observation; running the evaluation never contacts Nebius. Follow [docs/demo-script.md](docs/demo-script.md) for the full repository-to-handoff walkthrough and the offline fallback. No generated proposal is applied or executed.

For the public video, follow the [timed 2:55 storyboard and narration](docs/phase-8d-video-script.md) and [Windows recording checklist](docs/recording-checklist.md). The repeatable screen walkthrough uses clearly labeled mock inference; any historical Nemotron metrics are shown separately and are not presented as part of that mock run.

## License

Apache-2.0. NVIDIA model terms are separate; consult the model provider and model license before production use.

## Judge-accessible demo preparation

Phase 8B adds a fail-closed demo authentication gate, an operator kill switch for paid inference, a durable single-host request quota, and Linux reverse-proxy/service templates. No public deployment has been performed. Start with the mock provider; live Nemotron requires explicit provider selection, the kill switch, a configured secret, and quota capacity. See [docs/deployment.md](docs/deployment.md) for architecture, judge instructions, and the unvalidated deployment procedure. Do not expose FastAPI or Next.js ports directly.
