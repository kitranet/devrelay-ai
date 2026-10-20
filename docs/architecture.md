# Backend architecture

The backend uses FastAPI as its HTTP boundary and Pydantic models for validated settings and data contracts. `app/api` contains route handlers; `app/models` contains API schemas; `app/services` is reserved for application use cases; `app/integrations` contains external provider adapters; `app/core` owns settings, logging, and shared error mapping.

The Nebius adapter calls the Token Factory OpenAI-compatible `POST /chat/completions` endpoint over HTTPS. Base URL, model, key, and timeout are configurable. Credentials are represented by Pydantic `SecretStr`, supplied only in the authorization header, and omitted from logs. Provider details are converted to sanitized domain errors.

The initial service exposes `GET /health`; the model client is independently testable with `httpx.MockTransport`. No shell execution, repository-writing agent, persistent store, or frontend is included in this phase.

Nebius's official [Nemotron 3 Super cookbook quickstart](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md) confirms the configured regional base URL, model identifier, and chat completions usage.
