# DevRelay AI

An open-source engineering handoff agent powered by NVIDIA Nemotron and Nebius. The Python backend provides bounded static repository analysis, evidence-backed task planning, and a deterministic, human-reviewable calculator code proposal. Proposals are not applied and repository code is not executed.

## Quick start

Use Python 3.12 or newer. See [docs/setup.md](docs/setup.md) for environment setup and Nebius configuration.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The health check is available at `http://127.0.0.1:8000/health`. Repository analysis is available at `POST /api/v1/repositories/analyze`, and planning at `POST /api/v1/tasks/plan`; configure authorized repository IDs first as described in [docs/setup.md](docs/setup.md). API docs are at `/docs`.

Phase 4B adds `POST /api/v1/proposals/create` for the predefined division-by-zero calculator task and `GET /api/v1/proposals/{proposal_id}` to retrieve a review-only proposal. Static checks use unified-diff validation and Python AST parsing. Runtime validation reports `not_run` because no trusted sandbox is configured. No proposal endpoint applies code.

For offline planning, set `INFERENCE_PROVIDER=mock`. The deterministic mock supports only named synthetic evaluation scenarios; unsupported requests return an explicit unsupported result. It does not represent NVIDIA Nemotron output.

## Local dashboard

The Next.js dashboard lives in `frontend/`. Configure the synthetic repository in the backend and start FastAPI on port 8001, then copy `frontend/.env.example` to `frontend/.env.local`, install with `npm ci`, and run `npm run dev` from that directory. The dashboard opens at `http://localhost:3000`. Full setup and test commands are in [docs/setup.md](docs/setup.md).

## Project docs

- [Architecture](docs/architecture.md)
- [Setup and testing](docs/setup.md)
- [Agent instructions](AGENTS.md)

## License

Apache-2.0. NVIDIA model terms are separate; consult the model provider and model license before production use.
