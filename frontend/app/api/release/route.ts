export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  // Prefer provider identity so a forgotten local override cannot mask a deploy.
  const raw = process.env.VERCEL_GIT_COMMIT_SHA ?? process.env.CIVICSCOPE_BUILD_SHA ?? "";
  const commit = /^[0-9a-fA-F]{40}$/.test(raw) && raw.length === 40 ? raw.toLowerCase() : null;
  return Response.json(
    { service: "civicscope-frontend", commit },
    { headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } }
  );
}
