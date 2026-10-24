import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";

function authorizedRequest(url: string, init?: ConstructorParameters<typeof NextRequest>[1]) {
  const headers = new Headers(init?.headers);
  headers.set("authorization", `Basic ${Buffer.from("test-judge:test-only-password").toString("base64")}`);
  if (init?.method && init.method !== "GET" && init.method !== "HEAD" && !headers.has("origin")) {
    headers.set("origin", "http://localhost");
  }
  return new NextRequest(url, { ...init, headers });
}

afterEach(() => {
  delete process.env.BACKEND_API_URL;
  process.env.DEMO_AUTH_USERNAME = "test-judge";
  process.env.DEMO_AUTH_PASSWORD = "test-only-password";
  process.env.DEMO_AUTH_ORIGIN = "http://localhost";
});

describe("local backend proxy", () => {
  beforeEach(() => {
    process.env.DEMO_AUTH_USERNAME = "test-judge";
    process.env.DEMO_AUTH_PASSWORD = "test-only-password";
    process.env.DEMO_AUTH_ORIGIN = "http://localhost";
  });

  it("denies direct unauthenticated proxy-handler calls before contacting FastAPI", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const response = await GET(new NextRequest("http://localhost/api/backend/health"), {
      params: Promise.resolve({ path: ["health"] }),
    });
    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("forwards only the repository analysis endpoint to the configured loopback backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"summary":{"repository_id":"planning-fixture"}}', {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    process.env.BACKEND_API_URL = "http://127.0.0.1:8001";
    const request = authorizedRequest("http://localhost/api/backend/api/v1/repositories/analyze", {
      method: "POST", headers: { "Content-Type": "application/json", origin: "http://localhost" }, body: JSON.stringify({ repository_id: "planning-fixture" }),
    });
    const response = await POST(request, { params: Promise.resolve({ path: ["api", "v1", "repositories", "analyze"] }) });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ summary: { repository_id: "planning-fixture" } });
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://127.0.0.1:8001/api/v1/repositories/analyze");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[0]?.[1]?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("rejects unlisted backend routes and remote upstream addresses", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const unknown = await GET(authorizedRequest("http://localhost/api/backend/openapi.json"), { params: Promise.resolve({ path: ["openapi.json"] }) });
    expect(unknown.status).toBe(404);

    process.env.BACKEND_API_URL = "https://example.com";
    const request = authorizedRequest("http://localhost/api/backend/health");
    const forbidden = await GET(request, { params: Promise.resolve({ path: ["health"] }) });
    expect(forbidden.status).toBe(500);
    expect(await forbidden.json()).toMatchObject({ error: { code: "backend_configuration_error" } });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards proposal creation while keeping proposal apply routes unavailable", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"proposal_id":"proposal-id"}', {
      status: 201, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    process.env.BACKEND_API_URL = "http://127.0.0.1:8001";
    const create = authorizedRequest("http://localhost/api/backend/api/v1/proposals/create", {
      method: "POST", headers: { "Content-Type": "application/json", origin: "http://localhost" }, body: JSON.stringify({ repository_id: "planning-fixture", task_id: "plan-id" }),
    });
    const response = await POST(create, { params: Promise.resolve({ path: ["api", "v1", "proposals", "create"] }) });
    expect(response.status).toBe(201);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://127.0.0.1:8001/api/v1/proposals/create");
    const apply = authorizedRequest("http://localhost/api/backend/api/v1/proposals/proposal-id/apply", { method: "POST", headers: { origin: "http://localhost" }, body: "{}" });
    const unavailable = await POST(apply, { params: Promise.resolve({ path: ["api", "v1", "proposals", "proposal-id", "apply"] }) });
    expect(unavailable.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("proxies local review status, history, and handoff routes with strict UUID paths", async () => {
    // fetch consumes a Response body once; each upstream call needs its own response.
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{"enabled":false}', {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    process.env.BACKEND_API_URL = "http://127.0.0.1:8001";
    const status = await GET(authorizedRequest("http://localhost/api/backend/api/v1/reviews/status"), {
      params: Promise.resolve({ path: ["api", "v1", "reviews", "status"] }),
    });
    expect(status.status).toBe(200);
    const history = await GET(authorizedRequest("http://localhost/api/backend/api/v1/reviews/2b7a47fb-5c38-481a-a35c-b4f4cc0d7047"), {
      params: Promise.resolve({ path: ["api", "v1", "reviews", "2b7a47fb-5c38-481a-a35c-b4f4cc0d7047"] }),
    });
    expect(history.status).toBe(200);
    const handoffId = "01e6d118-3477-45df-9a1a-0cfaf17d4ae8";
    const handoff = await GET(authorizedRequest(`http://localhost/api/backend/api/v1/handoffs/${handoffId}`), {
      params: Promise.resolve({ path: ["api", "v1", "handoffs", handoffId] }),
    });
    expect(handoff.status).toBe(200);
    const malformed = await GET(authorizedRequest("http://localhost/api/backend/api/v1/handoffs/not-a-uuid"), {
      params: Promise.resolve({ path: ["api", "v1", "handoffs", "not-a-uuid"] }),
    });
    expect(malformed.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("proxies only the plan-review and plan-only handoff endpoints with strict task/report UUIDs", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{"handoff_type":"plan_only"}', {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    process.env.BACKEND_API_URL = "http://127.0.0.1:8001";
    const taskId = "2b7a47fb-5c38-481a-a35c-b4f4cc0d7047";
    const reportId = "01e6d118-3477-45df-9a1a-0cfaf17d4ae8";
    const review = await POST(authorizedRequest("http://localhost/api/backend/api/v1/reviews/plans", {
      method: "POST", headers: { "Content-Type": "application/json", origin: "http://localhost" }, body: "{}",
    }), { params: Promise.resolve({ path: ["api", "v1", "reviews", "plans"] }) });
    expect(review.status).toBe(200);
    const history = await GET(authorizedRequest(`http://localhost/api/backend/api/v1/reviews/plans/${taskId}`), {
      params: Promise.resolve({ path: ["api", "v1", "reviews", "plans", taskId] }),
    });
    expect(history.status).toBe(200);
    const handoff = await POST(authorizedRequest("http://localhost/api/backend/api/v1/handoffs/plans", {
      method: "POST", headers: { "Content-Type": "application/json", origin: "http://localhost" }, body: "{}",
    }), { params: Promise.resolve({ path: ["api", "v1", "handoffs", "plans"] }) });
    expect(handoff.status).toBe(200);
    const report = await GET(authorizedRequest(`http://localhost/api/backend/api/v1/handoffs/plans/${reportId}`), {
      params: Promise.resolve({ path: ["api", "v1", "handoffs", "plans", reportId] }),
    });
    expect(report.status).toBe(200);
    const malformed = await GET(authorizedRequest("http://localhost/api/backend/api/v1/handoffs/plans/not-a-uuid"), {
      params: Promise.resolve({ path: ["api", "v1", "handoffs", "plans", "not-a-uuid"] }),
    });
    expect(malformed.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("allows only runtime-validation readiness, request, and UUID evidence routes", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{"status":"disabled"}', {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    process.env.BACKEND_API_URL = "http://127.0.0.1:8001";
    const readiness = await GET(authorizedRequest("http://localhost/api/backend/api/v1/runtime-validation/readiness"), {
      params: Promise.resolve({ path: ["api", "v1", "runtime-validation", "readiness"] }),
    });
    expect(readiness.status).toBe(200);
    const payload = JSON.stringify({ authorization: { authorizer_identifier: "local_authorizer", purpose: "Verify this reviewed test patch." } });
    const requested = await POST(authorizedRequest("http://localhost/api/backend/api/v1/runtime-validation", {
      method: "POST", headers: { "Content-Type": "application/json", origin: "http://localhost" }, body: payload,
    }), { params: Promise.resolve({ path: ["api", "v1", "runtime-validation"] }) });
    expect(requested.status).toBe(200);
    const evidenceId = "01e6d118-3477-45df-9a1a-0cfaf17d4ae8";
    const evidence = await GET(authorizedRequest(`http://localhost/api/backend/api/v1/runtime-validation/${evidenceId}`), {
      params: Promise.resolve({ path: ["api", "v1", "runtime-validation", evidenceId] }),
    });
    expect(evidence.status).toBe(200);
    const malformed = await GET(authorizedRequest("http://localhost/api/backend/api/v1/runtime-validation/not-a-uuid"), {
      params: Promise.resolve({ path: ["api", "v1", "runtime-validation", "not-a-uuid"] }),
    });
    expect(malformed.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
