// A closed vocabulary prevents URLs, search text, exception messages and IDs
// from entering telemetry, including through untrusted reporter requests.
const operations = ["map", "summary", "compare", "search", "transit", "status", "resale", "other"] as const;
const failures = ["network", "browser_abort", "timeout", "http", "decode", "unknown"] as const;
const durations = ["under_1s", "1_to_10s", "10_to_60s", "over_60s"] as const;
type Operation = typeof operations[number];
export type ErrorContext = {
  operation?: Operation;
  failure?: typeof failures[number];
  duration?: typeof durations[number];
  online?: boolean;
  visibility?: "visible" | "hidden";
  status?: number;
};

export function sanitizeErrorContext(value: unknown): ErrorContext {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const data = value as Record<string, unknown>;
  const result: ErrorContext = {};
  if (operations.some((item) => item === data.operation)) result.operation = data.operation as Operation;
  if (failures.some((item) => item === data.failure)) result.failure = data.failure as ErrorContext["failure"];
  if (durations.some((item) => item === data.duration)) result.duration = data.duration as ErrorContext["duration"];
  if (typeof data.online === "boolean") result.online = data.online;
  if (data.visibility === "visible" || data.visibility === "hidden") result.visibility = data.visibility;
  if (typeof data.status === "number" && Number.isInteger(data.status) && data.status >= 400 && data.status <= 599) result.status = data.status;
  return result;
}

export function apiErrorContext(path: string, startedAt: number, failure: ErrorContext["failure"], status?: number): ErrorContext {
  const routes: Record<string, Operation> = {
    "/api/map-data": "map", "/api/summary": "summary", "/api/compare": "compare",
    "/api/geographies": "search", "/api/transit-routes": "transit", "/api/data-status": "status",
  };
  const pathname = path.split("?")[0];
  const operation = routes[pathname] ?? (/^\/api\/(?:trreb\/resale|trreb-preview)\/[^/]+$/.test(pathname) ? "resale" : "other");
  const elapsed = Math.max(0, Date.now() - startedAt);
  return sanitizeErrorContext({
    operation, failure, status,
    duration: elapsed < 1000 ? "under_1s" : elapsed < 10_000 ? "1_to_10s" : elapsed < 60_000 ? "10_to_60s" : "over_60s",
    online: typeof navigator === "undefined" ? undefined : navigator.onLine,
    visibility: typeof document === "undefined" ? undefined : document.visibilityState,
  });
}
