# Local setup

## Requirements

- Python 3.12 or newer
- A Nebius Token Factory API key only for genuine inference (unit tests do not need one)

## Install and run (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`; health is at `/health`, and interactive API documentation is at `/docs`.

## Configuration

Set values in the local, git-ignored `.env` file or the process environment. `NEBIUS_API_KEY` is optional until inference is requested. Never commit `.env` or paste credentials into source code or logs.

| Variable | Default | Purpose |
|---|---|---|
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.us-central1.nebius.com/v1/` | HTTPS Nebius Token Factory API base; only `api.tokenfactory[.<region>].nebius.com` hosts are accepted |
| `NEBIUS_MODEL` | `nvidia/nemotron-3-super-120b-a12b` | Model identifier |
| `NEBIUS_API_KEY` | unset | Runtime API key for inference |
| `NEBIUS_TIMEOUT_SECONDS` | `30` | Per-request timeout; range 0–600 (exclusive of 0) |
| `LOG_LEVEL` | `INFO` | Standard Python logging level |

## Tests

```powershell
python -m pytest
```

## Genuine inference smoke test

Set `NEBIUS_API_KEY` securely in the process environment or ignored `.env`, then run:

```powershell
python -m scripts.inference_smoke_test
```

This sends a real request and may incur provider charges. It is separate from the tests and has not been run as part of setup unless explicitly reported.
