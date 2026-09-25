type TrrebEnvironment = { runtime?: string; publicEnabled?: string; previewEnabled?: string };

export function getTrrebMode({ runtime, publicEnabled, previewEnabled }: TrrebEnvironment): "archive" | "public" | "preview" | "disabled" {
  if (publicEnabled === "1") return "public";
  if (runtime === "development" && previewEnabled === "1") return "preview";
  // Owner-approved, versioned Vercel archive is the default. Explicit 0 (or
  // any unrecognized value) disables display; 1 retains the legacy DB mode.
  if (publicEnabled === undefined || publicEnabled === "archive") return "archive";
  return "disabled";
}

// Keep these static accesses so Next.js replaces public flags at build time.
export const TRREB_MODE = getTrrebMode({
  runtime: process.env.NODE_ENV,
  publicEnabled: process.env.NEXT_PUBLIC_TRREB_ENABLED,
  previewEnabled: process.env.NEXT_PUBLIC_TRREB_PREVIEW_ENABLED,
});
