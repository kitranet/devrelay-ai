# DevRelay AI

An open-source engineering handoff agent with configurable Nebius-hosted NVIDIA Nemotron planning. The Python backend provides bounded static repository analysis, evidence-backed task planning, and a deterministic, human-reviewable calculator code proposal. Proposals are not applied and repository code is not executed.

## Quick start

Use Python 3.12 or newer. See [docs/setup.md](docs/setup.md) for environment setup and Nebius configuration.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The health check is available at `http://127.0.0.1:8000/health`. Repository analysis is available at `POST /api/v1/repositories/analyze`, and planning at `POST /api/v1/tasks/plan`; configure authorized repository IDs first as described in [docs/setup.md](docs/setup.md). API docs are at `/docs`.

Phase 4B adds `POST /api/v1/proposals/create` for the predefined division-by-zero calculator task and `GET /api/v1/proposals/{proposal_id}` to retrieve a review-only proposal. Phase 7B allows either a server-validated mock or Nebius plan to continue only when its integrity, provider provenance, evidence and content-hashed analysis snapshot are verified. The proposal remains one deterministic, allowlisted in-memory diff; model output is never translated into code. Static checks use unified-diff validation and Python AST parsing. Runtime validation reports `not_run` because no trusted sandbox is configured. No proposal endpoint applies code.

Phase 5A adds a disabled-by-default local review workflow and evidence-based handoff reports. Set `ENABLE_LOCAL_REVIEWS=true` only in development to enable loopback review requests. Reviewer labels are unverified, and an approval only accepts a proposal for further consideration; it does not apply code. Review and report storage is process-local and non-durable. See [docs/setup.md](docs/setup.md) for safe local demonstration steps.

Phase 5B adds a separately disabled, loopback-only runtime-validation authorization and evidence workflow for the fixed synthetic calculator proposal. The current checkout has no trusted sandbox executor, so readiness fails closed and authorized attempts return `sandbox_unavailable`; **no repository tests or code are run**. Do not enable this feature expecting execution. See [docs/setup.md](docs/setup.md) and [docs/architecture.md](docs/architecture.md) for the threat model and current limits.

For offline planning, set `INFERENCE_PROVIDER=mock`. The deterministic mock supports only named synthetic evaluation scenarios; unsupported requests return an explicit unsupported result. It does not represent NVIDIA Nemotron output.

Phase 6B adds an explicitly opted-in Nebius planning provider. The application defaults to mock even when an API key is configured; use `INFERENCE_PROVIDER=nebius` only after checking billing controls. Requests are bounded by prompt/output token limits and one in-flight call per process. Truncated or malformed answers are rejected, and successful plans expose only safe model, latency, and token-usage metadata. No automatic retry, mock fallback, code application, or repository execution is added. See [docs/setup.md](docs/setup.md) for the separately authorized smoke-test command; it has not been run as part of implementation.

## Local dashboard

The Next.js dashboard lives in `frontend/`. Configure the synthetic repository in the backend and start FastAPI on port 8001, then copy `frontend/.env.example` to `frontend/.env.local`, install with `npm ci`, and run `npm run dev` from that directory. The dashboard opens at `http://localhost:3000`. Full setup and test commands are in [docs/setup.md](docs/setup.md).

## Project docs

- [Architecture](docs/architecture.md)
- [Setup and testing](docs/setup.md)
- [Agent instructions](AGENTS.md)
- [Phase 7 evaluation and measured results](docs/phase-7-evaluation.md)
- [Repeatable demo script](docs/demo-script.md)
- [Security limitations](docs/security-limitations.md)

## Phase 7 demo and evaluation

Run the offline end-to-end evaluation against a temporary copy of the synthetic calculator fixture with the deterministic mock provider:

```powershell
Set-Location C:\devrelay-ai
.\.venv\Scripts\python.exe -m scripts.phase7_evaluation
.\.venv\Scripts\python.exe -m pytest
```

The evaluation JSON is checked in at `docs/evaluation/phase-7-results.json`. Mock metrics are kept separate from the historical live Nemotron observation; running the evaluation never contacts Nebius. Follow [docs/demo-script.md](docs/demo-script.md) for the full repository-to-handoff walkthrough and the offline fallback. No generated proposal is applied or executed.

## License

Apache-2.0. NVIDIA model terms are separate; consult the model provider and model license before production use.
