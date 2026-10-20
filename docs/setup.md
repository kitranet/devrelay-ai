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
| `TASK_PLANNING_TIMEOUT_SECONDS` | `60` | Total task-planning deadline |
| `TASK_CONTEXT_MAX_CHARS` | `16000` | Maximum serialized repository context sent to inference |

For example, configure a repository root in PowerShell with:

```powershell
$env:AUTHORIZED_REPOSITORIES = '{"devrelay":"C:/DevRelay-AI"}'
```

The scanner accepts only the configured ID (`devrelay`) in API requests. It never accepts a client-provided path. Keep this API bound to a trusted local interface; this phase does not implement user authentication or multi-user authorization.

The analysis route is `POST http://127.0.0.1:8000/api/v1/repositories/analyze` with JSON body `{"repository_id":"devrelay"}`. It returns summary counts, repository-relative file and symbol references, imports, dependency manifests, test/config/README paths, and sanitized warnings. It does not read environment files, credentials, SSH keys, or secret directories, and it skips all symlinks and common generated/binary content. It parses Python with `ast` without importing or executing it. File count, individual and aggregate size, depth, and processing time are bounded.

## Task planning API

Request `POST /api/v1/tasks/plan` with a repository ID already configured in `AUTHORIZED_REPOSITORIES`:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/tasks/plan `
  -ContentType 'application/json' `
  -Body '{"repository_id":"devrelay","task_description":"Investigate the unfamiliar request parser and its dependencies"}'
```

The response includes status, relevant files, traceable source references, proposed steps, likely changes, risks, dependencies, validation requirements, provider/mock identity, and approval state. Every plan is `not_started` and requires human approval. A plan with invalid evidence is downgraded to `insufficient_context`; unknown or ambiguous mock tasks return `unsupported`. Clear harmful requests are rejected, and repositories without Python modules return `insufficient_context`. Planning does not modify files or execute repository code. Configure the inference provider explicitly; Nebius errors are never retried via mock.

The offline evaluation scenarios use `tests/fixtures/planning_repo`: a division-by-zero defect (`package/calculator.py`), API input validation (`package/api.py`), and investigation of a function and its imported dependency (`package/service.py`, `package/dependencies.py`). Each scenario has corresponding tests under `tests/`. The mock handles these predefined cases only; evaluation checks structured output, expected paths/tests, and source-reference validity, not AI reasoning quality.

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
