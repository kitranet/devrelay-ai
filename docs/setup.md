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
| `INFERENCE_PROVIDER` | `nebius` | Select `nebius` or deterministic offline `mock` provider |
| `AUTHORIZED_REPOSITORIES` | `{}` | JSON mapping of repository IDs to absolute local roots |
| `REPOSITORY_MAX_FILES` | `2000` | Maximum regular files considered |
| `REPOSITORY_MAX_FILE_SIZE_BYTES` | `1000000` | Maximum individual file size |
| `REPOSITORY_MAX_TOTAL_BYTES` | `20000000` | Maximum combined file sizes |
| `REPOSITORY_MAX_DEPTH` | `20` | Maximum relative path depth |
| `REPOSITORY_MAX_PROCESSING_SECONDS` | `10` | Scanner processing deadline |

For example, configure a repository root in PowerShell with:

```powershell
$env:AUTHORIZED_REPOSITORIES = '{"devrelay":"C:/DevRelay-AI"}'
```

The scanner accepts only the configured ID (`devrelay`) in API requests. It never accepts a client-provided path. Keep this API bound to a trusted local interface; this phase does not implement user authentication or multi-user authorization.

The analysis route is `POST http://127.0.0.1:8000/api/v1/repositories/analyze` with JSON body `{"repository_id":"devrelay"}`. It returns summary counts, repository-relative file and symbol references, imports, dependency manifests, test/config/README paths, and sanitized warnings. It does not read environment files, credentials, SSH keys, or secret directories, and it skips all symlinks and common generated/binary content. It parses Python with `ast` without importing or executing it. File count, individual and aggregate size, depth, and processing time are bounded.

The example environment selects `INFERENCE_PROVIDER=mock` so local development does not need billing access. Set `INFERENCE_PROVIDER=mock` to explicitly select deterministic, offline test responses. Responses identify themselves with `provider="mock"`, `is_mock=true`, and a `devrelay-mock-v1` model name. Mock is never selected automatically after a Nebius error. Phase 2 has no public inference route; the provider is available through the application inference service for local wiring and tests.

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
