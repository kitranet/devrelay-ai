import { NextRequest } from "next/server";
import { afterEach, describe, expect, it } from "vitest";
import { proxy } from "@/proxy";
import { authorizeDemoRequest } from "./demo-auth";

const original = {
  username: process.env.DEMO_AUTH_USERNAME,
  password: process.env.DEMO_AUTH_PASSWORD,
  origin: process.env.DEMO_AUTH_ORIGIN,
};

afterEach(() => {
  for (const [key, value] of Object.entries({
    DEMO_AUTH_USERNAME: original.username,
    DEMO_AUTH_PASSWORD: original.password,
    DEMO_AUTH_ORIGIN: original.origin,
  })) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

function configure() {
  process.env.DEMO_AUTH_USERNAME = "judge";
  process.env.DEMO_AUTH_PASSWORD = "local-test-password";
  process.env.DEMO_AUTH_ORIGIN = "https://demo.example.test";
}

function request(path = "/", authorization?: string, method = "GET", origin?: string) {
  return new NextRequest(`https://demo.example.test${path}`, {
    method,
    ...(authorization ? { headers: { authorization, ...(origin ? { origin } : {}) } } : origin ? { headers: { origin } } : {}),
  });
}

describe("judge demo authentication", () => {
  it("fails closed when credentials or trusted origin are not configured", () => {
    delete process.env.DEMO_AUTH_USERNAME;
    const response = authorizeDemoRequest(request());
    expect(response?.status).toBe(503);
    expect(response?.headers.get("cache-control")).toBe("no-store");
  });

  it("fails closed for a password below the minimum length", () => {
    configure();
    process.env.DEMO_AUTH_PASSWORD = "short";
    expect(authorizeDemoRequest(request())?.status).toBe(503);
  });

  it("challenges unauthenticated application and API requests", async () => {
    configure();
    const page = await proxy(request("/"));
    const api = await proxy(request("/api/backend/api/v1/tasks/plan", undefined, "POST", "https://demo.example.test"));
    expect(page.status).toBe(401);
    expect(api.status).toBe(401);
    expect(page.headers.get("www-authenticate")).toContain("Basic");
  });

  it("authenticates using server-only credentials and rejects foreign mutation origins", () => {
    configure();
    const credentials = `Basic ${Buffer.from("judge:local-test-password").toString("base64")}`;
    expect(authorizeDemoRequest(request("/", credentials))).toBeNull();
    expect(authorizeDemoRequest(request("/api/backend/api/v1/tasks/plan", credentials, "POST", "https://attacker.example"))?.status).toBe(403);
    expect(authorizeDemoRequest(request("/api/backend/api/v1/tasks/plan", undefined, "POST", "https://demo.example.test"))?.status).toBe(401);
  });
});
