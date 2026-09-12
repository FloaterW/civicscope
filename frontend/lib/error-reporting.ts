export const errorCodes = ["uncaught", "unhandled_rejection", "render", "api_timeout", "api_network", "api_response"] as const;
export type ErrorCode = typeof errorCodes[number];

const reported = new Set<ErrorCode>();

/** Send only fixed error categories, never user queries, messages, or stack traces. */
export function reportClientError(code: ErrorCode) {
  if (typeof window === "undefined" || process.env.NODE_ENV !== "production" || reported.has(code)) return;
  reported.add(code);
  void fetch("/api/client-errors", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
    credentials: "omit",
    keepalive: true,
  }).catch(() => { /* Monitoring must never interrupt the dashboard. */ });
}
