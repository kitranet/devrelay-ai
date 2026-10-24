import { createHash, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

const realm = 'Basic realm="DevRelay AI judge demo", charset="UTF-8"';

function denied(status: 401 | 403 | 503, message: string): NextResponse {
  const headers = new Headers({ "Cache-Control": "no-store", "Vary": "Authorization, Origin" });
  if (status === 401) headers.set("WWW-Authenticate", realm);
  return NextResponse.json({ error: { code: status === 503 ? "demo_auth_unconfigured" : status === 403 ? "demo_origin_rejected" : "authentication_required", message } }, { status, headers });
}

function equalSecret(actual: string, expected: string): boolean {
  const actualDigest = createHash("sha256").update(actual, "utf8").digest();
  const expectedDigest = createHash("sha256").update(expected, "utf8").digest();
  return timingSafeEqual(actualDigest, expectedDigest);
}

/** Fail-closed HTTP Basic auth and same-origin guard for browser mutations. */
export function authorizeDemoRequest(request: NextRequest): NextResponse | null {
  const username = process.env.DEMO_AUTH_USERNAME;
  const password = process.env.DEMO_AUTH_PASSWORD;
  const configuredOrigin = process.env.DEMO_AUTH_ORIGIN;
  if (
    !username || username.length > 256 || username.includes(":") || /[\u0000-\u001f\u007f]/.test(username) ||
    !password || password.length < 16 || password.length > 256 || /[\u0000-\u001f\u007f]/.test(password) ||
    !configuredOrigin
  ) {
    return denied(503, "The demo access gateway is not configured.");
  }

  let expectedOrigin: string;
  try {
    const parsed = new URL(configuredOrigin);
    if (!new Set(["https:", "http:"]).has(parsed.protocol) || parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash || (parsed.protocol === "http:" && !new Set(["localhost", "127.0.0.1", "[::1]"]).has(parsed.hostname))) {
      return denied(503, "The demo access gateway is not configured.");
    }
    expectedOrigin = parsed.origin;
  } catch {
    return denied(503, "The demo access gateway is not configured.");
  }

  if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) {
    const origin = request.headers.get("origin");
    if (!origin || origin !== expectedOrigin) return denied(403, "The request origin is not permitted.");
  }

  const authorization = request.headers.get("authorization") ?? "";
  if (authorization.length > 1024 || !authorization.startsWith("Basic ")) {
    return denied(401, "Valid demo credentials are required.");
  }
  try {
    const encoded = authorization.slice(6);
    const bytes = Buffer.from(encoded, "base64");
    if (!encoded || bytes.toString("base64") !== encoded) return denied(401, "Valid demo credentials are required.");
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const separator = decoded.indexOf(":");
    if (separator < 1 || decoded.length > 513) return denied(401, "Valid demo credentials are required.");
    const actualUser = decoded.slice(0, separator);
    const actualPassword = decoded.slice(separator + 1);
    const userMatches = equalSecret(actualUser, username);
    const passwordMatches = equalSecret(actualPassword, password);
    if (userMatches && passwordMatches) return null;
  } catch {
    // Malformed auth material is intentionally indistinguishable from bad credentials.
  }
  return denied(401, "Valid demo credentials are required.");
}
