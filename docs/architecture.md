# Backend architecture

The backend uses FastAPI as its HTTP boundary and Pydantic models for validated settings and data contracts. `app/api` contains route handlers; `app/models` contains API schemas; `app/services` is reserved for application use cases; `app/integrations` contains external provider adapters; `app/core` owns settings, logging, and shared error mapping.

The Nebius adapter calls the Token Factory OpenAI-compatible `POST /chat/completions` endpoint over HTTPS. Base URL, model, key, and timeout are configurable. Credentials are represented by Pydantic `SecretStr`, supplied only in the authorization header, and omitted from logs. Provider details are converted to sanitized domain errors.

The initial service exposes `GET /health`; the model client is independently testable with `httpx.MockTransport`. No shell execution, repository-writing agent, persistent store, or frontend is included in this phase.

## Repository intelligence

`POST /api/v1/repositories/analyze` accepts a configured repository ID, never a path. IDs map through `AUTHORIZED_REPOSITORIES` to absolute roots supplied by the operator. `RepositoryScanner` walks with bounded file count, per-file and aggregate bytes, traversal depth, and processing time. It skips secret paths, generated directories, binaries, and all symlinks. Python is parsed with `ast`; TOML, INI, requirements, and lock manifests are parsed as data. Target code is never imported or executed. Results contain repository-relative POSIX paths and line references, not absolute root paths.

Inference provider selection is explicit through `INFERENCE_PROVIDER=nebius|mock`. The mock provider is deterministic and offline, labels results with `provider=mock` and `is_mock=true`, and never claims Nemotron provenance. Nebius failures are returned as errors; there is no mock fallback.

## Engineering task planning

`POST /api/v1/tasks/plan` accepts a configured repository ID and a 10–4,000 character task description. `TaskPlanningService` runs the existing bounded scanner, selects a bounded context of files, modules, AST symbols, imports, manifest entries and test paths, and calls the already configured `InferenceService`. The provider must return a JSON `PlanGeneration`; Pydantic validates its structure before evidence checks run. No source is executed or changed.

Every cited source reference must match a function, class, or import reference emitted by repository analysis. Relevant and expected-change paths must exist in that analysis. Unsupported references are returned in `unsupported_references` and downgrade a plan to `insufficient_context`. Clear harmful task intents are rejected before inference, and repositories without analyzed Python modules return `insufficient_context`. Plans remain `not_started` and require human approval. Provider errors are surfaced; the planner never switches providers after failure. `TASK_PLANNING_TIMEOUT_SECONDS` and `TASK_CONTEXT_MAX_CHARS` bound planning work.

The mock provider supports only the three synthetic evaluation scenarios documented in setup. Unknown or ambiguous tasks return `unsupported`, with no steps or claimed files. These tests measure deterministic schema and evidence handling, not model reasoning accuracy.

Nebius's official [Nemotron 3 Super cookbook quickstart](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md) confirms the configured regional base URL, model identifier, and chat completions usage.
