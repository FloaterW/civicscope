import { sanitizeErrorContext, type ErrorContext } from "@/lib/error-context";

export const errorCodes = ["uncaught", "unhandled_rejection", "render", "api_timeout", "api_network", "api_response", "api_decode"] as const;
export type ErrorCode = typeof errorCodes[number];

const reported = new Set<ErrorCode>();

/** Send only fixed error categories, never user queries, messages, or stack traces. */
export function reportClientError(code: ErrorCode, context?: ErrorContext) {
  if (typeof window === "undefined" || process.env.NODE_ENV !== "production" || reported.has(code)) return;
  reported.add(code);
  void fetch("/api/client-errors", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, ...(context ? { context: sanitizeErrorContext(context) } : {}) }),
    credentials: "omit",
    keepalive: true,
  }).catch(() => { /* Monitoring must never interrupt the dashboard. */ });
}
