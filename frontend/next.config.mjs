import withBundleAnalyzer from "@next/bundle-analyzer";

const analyze = withBundleAnalyzer({ enabled: process.env.ANALYZE === "true" });
const isDevelopment = process.env.NODE_ENV === "development";

const apiOrigin = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").origin;
  } catch {
    return "http://localhost:8000";
  }
})();

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  `script-src 'self' 'unsafe-inline'${isDevelopment ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://tiles.openfreemap.org",
  "font-src 'self' data: https://tiles.openfreemap.org",
  `connect-src 'self' ${apiOrigin} https://tiles.openfreemap.org${isDevelopment ? " ws:" : ""}`,
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  ...(!isDevelopment ? ["upgrade-insecure-requests"] : [])
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Next.js 16.3 does not emit the server trace file when Vercel injects its
  // build adapter, but standalone finalization still tries to read it. Vercel
  // does not use the standalone bundle; keep it enabled for Docker/self-hosting.
  output: process.env.VERCEL ? undefined : "standalone",
  reactStrictMode: true,
  headers: async () => [
    {
      source: "/(.*)",
      headers: [
        { key: "X-Frame-Options", value: "DENY" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=()" },
        { key: "Content-Security-Policy", value: contentSecurityPolicy },
        { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      ],
    },
  ],
};

export default analyze(nextConfig);
