import { NextRequest, NextResponse } from "next/server";

const ROUTES = new Map<string, { method: "GET" | "POST"; upstream: string }>([
  ["health", { method: "GET", upstream: "/health" }],
  ["api/v1/repositories/analyze", { method: "POST", upstream: "/api/v1/repositories/analyze" }],
  ["api/v1/tasks/plan", { method: "POST", upstream: "/api/v1/tasks/plan" }],
  ["api/v1/proposals/create", { method: "POST", upstream: "/api/v1/proposals/create" }],
  ["api/v1/reviews/status", { method: "GET", upstream: "/api/v1/reviews/status" }],
  ["api/v1/reviews", { method: "POST", upstream: "/api/v1/reviews" }],
  ["api/v1/handoffs", { method: "POST", upstream: "/api/v1/handoffs" }],
]);

type RouteContext = { params: Promise<{ path: string[] }> };

function errorResponse(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message } }, { status });
}

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const pathKey = path.join("/");
  const route = ROUTES.get(pathKey) ?? (
    request.method === "GET" && path.length === 4 && path[0] === "api" && path[1] === "v1" &&
    ["reviews", "handoffs"].includes(path[2]) && /^[0-9a-f-]{36}$/i.test(path[3])
      ? { method: "GET" as const, upstream: `/${pathKey}` }
      : undefined
  );
  if (!route) return errorResponse(404, "proxy_route_not_found", "This backend route is not available through the dashboard.");
  if (request.method !== route.method) return errorResponse(405, "method_not_allowed", "This method is not available for this route.");

  let body: string | undefined;
  if (route.method === "POST") {
    const contentLength = Number(request.headers.get("content-length") ?? "0");
    if (contentLength > 8_192) return errorResponse(413, "request_too_large", "The request is larger than the dashboard allows.");
    body = await request.text();
    if (body.length > 8_192) return errorResponse(413, "request_too_large", "The request is larger than the dashboard allows.");
    try {
      JSON.parse(body);
    } catch {
      return errorResponse(400, "invalid_json", "The request body must be valid JSON.");
    }
  }

  const configuredBase = process.env.BACKEND_API_URL?.trim() || "http://127.0.0.1:8001";
  let base: URL;
  try {
    base = new URL(configuredBase);
  } catch {
    return errorResponse(500, "backend_configuration_error", "BACKEND_API_URL is invalid.");
  }
  const localHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);
  if (!new Set(["http:", "https:"]).has(base.protocol) || !localHosts.has(base.hostname) || base.username || base.password || base.search || base.hash) {
    return errorResponse(500, "backend_configuration_error", "BACKEND_API_URL must point to a local HTTP service.");
  }

  try {
    const response = await fetch(new URL(route.upstream, `${base.toString().replace(/\/$/, "")}/`), {
      method: route.method,
      ...(body === undefined ? {} : { body }),
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(65_000),
    });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      return errorResponse(504, "backend_timeout", "The backend did not respond before the dashboard timeout.");
    }
    return errorResponse(502, "backend_unavailable", "Cannot connect to the local backend. Check its address and status.");
  }
}

export const GET = proxy;
export const POST = proxy;
