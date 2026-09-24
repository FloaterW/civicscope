import { errorCodes } from "@/lib/error-reporting";
import { sanitizeErrorContext } from "@/lib/error-context";

// Best-effort per-instance log deduplication; platform limits remain necessary
// for hostile traffic. No persistent identifiers or user payloads are retained.
const lastLogged = new Map<string, number>();

export async function POST(request: Request) {
  const headers = { "Cache-Control": "no-store" };
  if (request.headers.get("origin") !== new URL(request.url).origin) {
    return new Response(null, { status: 403, headers });
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return new Response(null, { status: 415, headers });
  }
  const reader = request.body?.getReader();
  if (!reader) return new Response(null, { status: 400, headers });
  let size = 0;
  let body = "";
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 256) {
        await reader.cancel();
        return new Response(null, { status: 413, headers });
      }
      body += decoder.decode(value, { stream: true });
    }
    body += decoder.decode();
    const payload: unknown = JSON.parse(body);
    if (!payload || typeof payload !== "object" || !("code" in payload) ||
        typeof payload.code !== "string" || !errorCodes.some((code) => code === payload.code)) {
      return new Response(null, { status: 400, headers });
    }
    const now = Date.now();
    if (now - (lastLogged.get(payload.code) ?? 0) >= 60_000) {
      lastLogged.set(payload.code, now);
      const context = sanitizeErrorContext("context" in payload ? payload.context : undefined);
      console.error(JSON.stringify({ event: "client_error", code: payload.code, release: process.env.VERCEL_GIT_COMMIT_SHA ?? "local", ...(Object.keys(context).length ? { context } : {}) }));
    }
    return new Response(null, { status: 204, headers });
  } catch {
    return new Response(null, { status: 400, headers });
  } finally {
    reader.releaseLock();
  }
}
