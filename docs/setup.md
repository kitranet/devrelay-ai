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
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.nebius.com/v1/` | HTTPS Nebius Token Factory API base; only `api.tokenfactory[.<region>].nebius.com` hosts are accepted |
| `NEBIUS_MODEL` | `nvidia/Nemotron-3_5-Lightning` | Model identifier |
| `NEBIUS_API_KEY` | unset | Runtime API key for inference |
| `NEBIUS_TIMEOUT_SECONDS` | `30` | Per-request timeout; range 0–600 (exclusive of 0) |
| `NEBIUS_MAX_OUTPUT_TOKENS` | `1024` | Maximum completion token budget per request |
| `NEBIUS_MAX_PROMPT_TOKENS` | `6000` | Maximum estimated prompt tokens; estimator uses serialized UTF-8 size and is not the provider tokenizer |
| `NEBIUS_MAX_IN_FLIGHT_REQUESTS` | `1` | Per-process concurrent paid request limit; keep at one for initial integration |
| `LOG_LEVEL` | `INFO` | Standard Python logging level |
| `INFERENCE_PROVIDER` | `mock` | Select `mock` by default; set `nebius` explicitly to make paid requests |
| `ENABLE_LOCAL_REVIEWS` | `false` | Enables unverified local review only when `ENVIRONMENT=development`; keep disabled for production |
| `ENABLE_ISOLATED_RUNTIME_VALIDATION` | `false` | Enables the separate local authorization/evidence workflow in development; does not make a sandbox available |
| `ENVIRONMENT` | `development` | Application environment; local reviews cannot be enabled outside development |
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

## Safe proposal API (Phase 4B)

Proposal generation is available only for the fixed synthetic calculator scenario and requires the task plan to have been created earlier in the same running backend process. The API keeps only a bounded number of plans and proposals in memory, so restart clears them.

First create the task plan:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/tasks/plan `
  -ContentType 'application/json' `
  -Body '{"repository_id":"planning-fixture","task_description":"Fix the division by zero defect in the calculator"}'
```

Use the returned `task_id` to create a static proposal:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/proposals/create `
  -ContentType 'application/json' `
  -Body '{"repository_id":"planning-fixture","task_id":"<task_id from plan response>"}'
```

The response contains the unified diff, target path and source hash, static findings, `provider=mock`, `is_mock=true`, `lifecycle_state=awaiting_review`, and `human_approval_required=true`. Retrieve a proposal with `GET /api/v1/proposals/{proposal_id}`. The source file remains unchanged. No approval or apply route exists. Runtime validation is explicitly `not_run`; the host does not execute repository tests or code. The optional isolated-runtime protocol is not backed by a sandbox implementation. The dashboard exposes the generate button only for this predefined mock plan and displays the diff, findings, hash, and runtime status.

The static checks reject stale source, traversal, absolute paths, duplicate targets, sensitive paths, symlinks/junctions, binary/oversized targets, malformed or oversized diffs, and invalid Python syntax. Proposal generation reuses the existing authorized repository scanner and does not accept client paths or patches. This scenario is intentionally fixed; arbitrary model-authored changes and arbitrary repository modifications are out of scope.

## Frontend dashboard (local development)

The Next.js dashboard is in `frontend/`. It uses a server-side proxy allowlist for `/health`, repository analysis, task planning, proposal creation, review status/history/submission, and handoff report generation/retrieval. Configure the backend with the synthetic repository and mock provider from the repository root:

```powershell
$env:INFERENCE_PROVIDER = "mock"
$env:AUTHORIZED_REPOSITORIES = '{"planning-fixture":"C:/devrelay-ai/tests/fixtures/planning_repo"}'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

In a second PowerShell terminal:

```powershell
Set-Location C:\devrelay-ai\frontend
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm ci
npm run dev
```

Open `http://localhost:3000`. `NEXT_PUBLIC_REPOSITORY_IDS` contains only configured IDs (comma-separated), never filesystem paths. `NEXT_PUBLIC_LOCAL_REVIEWER_ID` is an unverified display label only; use a pseudonym. The backend's `AUTHORIZED_REPOSITORIES` remains the authorization boundary. `BACKEND_API_URL` is server-side only and must point to a local loopback backend; no model credentials are read by the frontend. The frontend scripts select Next.js Webpack mode because Turbopack's CSS worker exited before connecting on this Windows development host.

Restart FastAPI after changing its environment. Restart the Next.js development server after changing `frontend/.env.local`, especially the public repository IDs. Use `npm test`, `npm run lint`, `npm run typecheck`, and `npm run build` in `frontend/`. The dashboard is local-development only: no authentication, no repository discovery endpoint, no code changes or execution, and no production deployment configuration are included.

The example environment and application default select `INFERENCE_PROVIDER=mock`, including when `NEBIUS_API_KEY` is configured. Live inference requires explicit `INFERENCE_PROVIDER=nebius`; the Nebius client also refuses direct calls unless this opt-in is set. Mock responses identify themselves with `provider="mock"`, `is_mock=true`, and `devrelay-mock-v1`. Nebius failures never fall back to mock. Planning output carries safe provider/model/completion/latency/token diagnostics; it never carries prompts, provider response bodies, headers, or model reasoning. No streaming is used.

Paid calls are bounded by a 1,024-token completion maximum, a 6,000 estimated prompt-token maximum, the existing task-context character limit, and one in-flight request per backend process by default. The prompt estimator is an approximate local guard, not a tokenizer guarantee. The concurrency gate is process-local; run a single backend worker for the initial integration or use a separately reviewed shared limiter before multi-worker use. HTTPX is configured without automatic retries. Token ceilings are not dollar caps. No model price table is configured, and trial credit is not a hard spending limit; use provider-side billing controls for account-level limits.

## Local review and engineering handoff (Phase 5A)

Review decisions are disabled by default. The backend refuses `ENABLE_LOCAL_REVIEWS=true` unless `ENVIRONMENT=development`, and review/history routes require direct loopback client and host addresses. Keep FastAPI bound to `127.0.0.1`; do not publish or reverse-proxy these endpoints. Reviewer identifiers are unverified local labels, not authenticated identities. Use a pseudonymous label and keep credentials, private keys, secrets, and unnecessary personal data out of justifications and questions. Credential-like patterns are rejected. Approval accepts a proposal for further consideration only. It never applies or executes code.

For a local demo, first configure and start the synthetic mock backend as shown above. In that backend PowerShell process, set the flag before starting FastAPI:

```powershell
$env:ENVIRONMENT = "development"
$env:INFERENCE_PROVIDER = "mock"
$env:ENABLE_LOCAL_REVIEWS = "true"
$env:AUTHORIZED_REPOSITORIES = '{"planning-fixture":"C:/devrelay-ai/tests/fixtures/planning_repo"}'
Set-Location C:\devrelay-ai
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Restart FastAPI after changing the flag. The dashboard can then create a mock plan and proposal, show the local reviewer warning, and enable approve/request-changes/reject controls. Every decision requires a non-empty justification and is bound to the proposal version, source hash and diff hash. Repeating a decision or submitting stale hashes returns a conflict. No approval button is shown as active when `/api/v1/reviews/status` reports disabled.

The API routes are:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/v1/reviews/status` | Read local review flag and unverified identity status |
| `POST` | `/api/v1/reviews` | Submit one justified local decision |
| `GET` | `/api/v1/reviews/{proposal_id}` | Retrieve bounded review and audit history |
| `POST` | `/api/v1/handoffs` | Generate a structured report for a known proposal |
| `GET` | `/api/v1/handoffs/{report_id}` | Retrieve a generated report |

Example decision body (substitute the proposal ID, version, and hashes from the proposal response):

```json
{
  "proposal_id": "00000000-0000-0000-0000-000000000000",
  "decision": "approve",
  "reviewer_identifier": "local-reviewer",
  "justification": "The static diff matches the stated zero-denominator behavior.",
  "proposal_version": 1,
  "source_sha256": "<64-character source hash>",
  "diff_sha256": "<64-character diff hash>",
  "outstanding_questions": ["Run the calculator tests in an isolated environment."]
}
```

The handoff report is generated from current static analysis, the stored plan/proposal, and recorded review history without calling a model. It marks task and proposal text as mock output, reviewer identity as unverified, static analysis as evidence, and runtime validation as `not_run`. It includes source references, hashes, risks, assumptions, missing evidence, outstanding questions and next engineer actions. The dashboard can copy or download the report as Markdown.

Generate and retrieve a report from PowerShell using a proposal ID returned by the proposal endpoint:

```powershell
$handoff = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/handoffs `
  -ContentType 'application/json' `
  -Body '{"proposal_id":"<proposal UUID>"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/v1/handoffs/$($handoff.report_id)"
```

Review, audit, and report records are bounded in-memory prototype data. They disappear when FastAPI restarts or an older record is evicted; the audit history is not tamper-proof. Production use requires authenticated identity, role checks, durable audit storage, retention controls, and an independently reviewed execution system. None are part of this phase.

## Tests

```powershell
python -m pytest
```

Frontend checks (from `frontend/`):

```powershell
npm test
npm run lint
npm run typecheck
npm run build
```

## Genuine inference smoke test

This is a separately authorized manual action. It sends one real paid request; no automated test invokes it. Configure the API key through an approved local secret store or the ignored `.env` file; never put it in chat or a tracked file. In the same PowerShell process, explicitly opt in and use the reviewed defaults:

```powershell
$env:INFERENCE_PROVIDER = "nebius"
$env:NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
$env:NEBIUS_MODEL = "nvidia/Nemotron-3_5-Lightning"
$env:NEBIUS_MAX_OUTPUT_TOKENS = "1024"
$env:NEBIUS_MAX_PROMPT_TOKENS = "6000"
$env:NEBIUS_MAX_IN_FLIGHT_REQUESTS = "1"
# Ensure NEBIUS_API_KEY is set locally through your approved secret mechanism.
python -m scripts.inference_smoke_test
```

The script makes one request, prints only safe completion metadata, and does not print the answer or key. It propagates sanitized failures; an incomplete `length` response is not success. This action may incur provider charges. Token limits are not a guaranteed spending cap, so check the provider billing controls before proceeding. Do not run this as part of automated tests.


## Phase 5B: isolated runtime validation status

The runtime-validation control is separate from review approval. It requires a current proposal in `review_approved`, matching proposal version/source hash/diff hash, the fixed synthetic repository and target, and a separate local authorization label plus purpose. The label is unverified and is not authentication. The only accepted case is `calculator_unit_tests` (fixed command ID `calculator_pytest_suite_v1`); clients cannot submit commands, paths, or arbitrary tests.

The API exposes:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/v1/runtime-validation/readiness` | Report feature, host and sandbox readiness checks |
| `POST` | `/api/v1/runtime-validation` | Submit one version/hash-bound local execution authorization and receive evidence |
| `GET` | `/api/v1/runtime-validation/{evidence_id}` | Retrieve evidence held in this process |

To inspect readiness, use `Invoke-RestMethod http://127.0.0.1:8001/api/v1/runtime-validation/readiness`. The feature defaults off. If deliberately demonstrating the authorization flow locally, set `ENVIRONMENT=development`, `ENABLE_LOCAL_REVIEWS=true`, and `ENABLE_ISOLATED_RUNTIME_VALIDATION=true` in the backend process environment, then restart FastAPI. This will **not** enable code execution: the current executor fails closed because this checkout has no verified Linux sandbox, immutable local image, or hardened launcher. A request may create `sandbox_unavailable` evidence while explicitly recording that no test code ran. Do not treat this response as a test result or enable the setting in production.

The request body uses IDs and hashes from the current approved proposal:

```json
{
  "proposal_id": "00000000-0000-0000-0000-000000000000",
  "proposal_version": 2,
  "source_sha256": "<64 lowercase hex characters from the proposal>",
  "diff_sha256": "<64 lowercase hex characters from the proposal>",
  "test_case": "calculator_unit_tests",
  "authorization": {
    "authorizer_identifier": "local-authorizer",
    "purpose": "Validate the reviewed calculator proposal."
  }
}
```

Call with `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/runtime-validation -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 5)`. Configure the dashboard's `NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID` as an unverified pseudonymous label. Do not put secrets or personal information in the purpose. Readiness/evidence APIs do not expose repository absolute paths. Evidence and replay-prevention state are bounded and process-local, not durable or tamper-proof.

No Docker or WSL installation, image download, or container smoke test was performed. The unit-test fake executor is only an orchestration test double and never runs repository code. This phase therefore does not satisfy the prerequisite for an authenticated runtime inference or sandbox test. A trusted sandbox executor and independently reviewed host controls are a prerequisite milestone before runtime testing can be enabled.
