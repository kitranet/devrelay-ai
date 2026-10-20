# DevRelay AI

An open-source autonomous engineering handoff agent powered by NVIDIA Nemotron and Nebius. This repository currently contains the Phase 1 Python backend foundation.

## Quick start

Use Python 3.12 or newer. See [docs/setup.md](docs/setup.md) for environment setup and Nebius configuration.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The health check is available at `http://127.0.0.1:8000/health`. Repository analysis is available at `POST /api/v1/repositories/analyze`; configure authorized repository IDs first as described in [docs/setup.md](docs/setup.md). API docs are at `/docs`.

## Project docs

- [Architecture](docs/architecture.md)
- [Setup and testing](docs/setup.md)
- [Agent instructions](AGENTS.md)

## License

Apache-2.0. NVIDIA model terms are separate; consult the model provider and model license before production use.
