import { readArchivedResale } from "@/lib/server/trreb-archive";
import { TRREB_MODE } from "@/lib/trreb-mode";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store" };

export async function GET(request: Request, context: { params: Promise<{ geoid: string }> }) {
  if (TRREB_MODE !== "archive" || process.env.TRREB_ARCHIVE_DISABLED === "1") {
    return Response.json({ detail: "Not found" }, { status: 404, headers });
  }
  const { geoid } = await context.params;
  const query = new URL(request.url).searchParams;
  const year = query.get("year") ?? "2025";
  const month = query.get("month");
  if (query.getAll("year").length > 1 || query.getAll("month").length > 1 ||
      !/^202[0-5]$/.test(year) || (month !== null && !/^(?:[1-9]|1[0-2])$/.test(month))) {
    return Response.json({ detail: "Choose a year from 2020–2025 and a month from 1–12." }, { status: 422, headers });
  }
  if (!/^\d{7}$/.test(geoid)) {
    return Response.json({ detail: "No municipal TRREB reporting area" }, { status: 404, headers });
  }
  try {
    const row = readArchivedResale(geoid, Number(year), month === null ? undefined : Number(month));
    return row ? Response.json(row, { headers }) : Response.json({ detail: "No municipal TRREB reporting area" }, { status: 404, headers });
  } catch {
    return Response.json({ detail: "TRREB archive is temporarily unavailable." }, { status: 503, headers });
  }
}
