import { NextRequest, NextResponse } from "next/server";
import { authorizeDemoRequest } from "@/lib/server/demo-auth";

export function proxy(request: NextRequest) {
  return authorizeDemoRequest(request) ?? NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|robots.txt).*)"],
};
