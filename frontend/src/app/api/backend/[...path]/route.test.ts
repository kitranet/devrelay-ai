import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";

afterEach(() => {
  delete process.env.BACKEND_API_URL;
});

describe("local backend proxy", () => {
  it("forwards only the repository analysis endpoint to the configured loopback backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"summary":{"repository_id":"planning-fixture"}}', {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    process.env.BACKEND_API_URL = "http://127.0.0.1:8001";
    const request = new NextRequest("http://localhost/api/backend/api/v1/repositories/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repository_id: "planning-fixture" }),
    });
    const response = await POST(request, { params: Promise.resolve({ path: ["api", "v1", "repositories", "analyze"] }) });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ summary: { repository_id: "planning-fixture" } });
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://127.0.0.1:8001/api/v1/repositories/analyze");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("rejects unlisted backend routes and remote upstream addresses", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const health = new NextRequest("http://localhost/api/backend/health");
    const unknown = await GET(health, { params: Promise.resolve({ path: ["openapi.json"] }) });
    expect(unknown.status).toBe(404);

    process.env.BACKEND_API_URL = "https://example.com";
    const request = new NextRequest("http://localhost/api/backend/health");
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
    const create = new NextRequest("http://localhost/api/backend/api/v1/proposals/create", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repository_id: "planning-fixture", task_id: "plan-id" }),
    });
    const response = await POST(create, { params: Promise.resolve({ path: ["api", "v1", "proposals", "create"] }) });
    expect(response.status).toBe(201);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("http://127.0.0.1:8001/api/v1/proposals/create");
    const apply = new NextRequest("http://localhost/api/backend/api/v1/proposals/proposal-id/apply", { method: "POST", body: "{}" });
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
    const status = await GET(new NextRequest("http://localhost/api/backend/api/v1/reviews/status"), {
      params: Promise.resolve({ path: ["api", "v1", "reviews", "status"] }),
    });
    expect(status.status).toBe(200);
    const history = await GET(new NextRequest("http://localhost/api/backend/api/v1/reviews/2b7a47fb-5c38-481a-a35c-b4f4cc0d7047"), {
      params: Promise.resolve({ path: ["api", "v1", "reviews", "2b7a47fb-5c38-481a-a35c-b4f4cc0d7047"] }),
    });
    expect(history.status).toBe(200);
    const handoffId = "01e6d118-3477-45df-9a1a-0cfaf17d4ae8";
    const handoff = await GET(new NextRequest(`http://localhost/api/backend/api/v1/handoffs/${handoffId}`), {
      params: Promise.resolve({ path: ["api", "v1", "handoffs", handoffId] }),
    });
    expect(handoff.status).toBe(200);
    const malformed = await GET(new NextRequest("http://localhost/api/backend/api/v1/handoffs/not-a-uuid"), {
      params: Promise.resolve({ path: ["api", "v1", "handoffs", "not-a-uuid"] }),
    });
    expect(malformed.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("allows only runtime-validation readiness, request, and UUID evidence routes", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{"status":"disabled"}', {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    process.env.BACKEND_API_URL = "http://127.0.0.1:8001";
    const readiness = await GET(new NextRequest("http://localhost/api/backend/api/v1/runtime-validation/readiness"), {
      params: Promise.resolve({ path: ["api", "v1", "runtime-validation", "readiness"] }),
    });
    expect(readiness.status).toBe(200);
    const payload = JSON.stringify({ authorization: { authorizer_identifier: "local_authorizer", purpose: "Verify this reviewed test patch." } });
    const requested = await POST(new NextRequest("http://localhost/api/backend/api/v1/runtime-validation", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: payload,
    }), { params: Promise.resolve({ path: ["api", "v1", "runtime-validation"] }) });
    expect(requested.status).toBe(200);
    const evidenceId = "01e6d118-3477-45df-9a1a-0cfaf17d4ae8";
    const evidence = await GET(new NextRequest(`http://localhost/api/backend/api/v1/runtime-validation/${evidenceId}`), {
      params: Promise.resolve({ path: ["api", "v1", "runtime-validation", evidenceId] }),
    });
    expect(evidence.status).toBe(200);
    const malformed = await GET(new NextRequest("http://localhost/api/backend/api/v1/runtime-validation/not-a-uuid"), {
      params: Promise.resolve({ path: ["api", "v1", "runtime-validation", "not-a-uuid"] }),
    });
    expect(malformed.status).toBe(404);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
