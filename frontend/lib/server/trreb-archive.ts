// Server route only: never import this module from a client component.
import { createHash } from "node:crypto";
import archive from "@/data/trreb-resale-2020-2025.json";

export const ARCHIVE_SHA256 = "10645ab2c4e2507a79afa3f26ebd0a9eabfaa715f92b52a21b4ad8609a3b7d73";
export const SOURCE_RELEASE = "253fbe7ac0c9668b08d60cc9034aaa9cf81cbc992273fe736e056c5f6148329d";
type Observation = typeof archive.observations[number];
let index: Map<string, Observation> | undefined;

function archiveIndex() {
  if (index) return index;
  // Fail closed if the pinned public artifact changes without release review.
  if (archive.schema_version !== 1 || archive.source_release !== SOURCE_RELEASE ||
      createHash("sha256").update(JSON.stringify(archive)).digest("hex") !== ARCHIVE_SHA256) {
    throw new Error("TRREB archive integrity check failed");
  }
  const candidate = new Map(archive.observations.map(row => [`${row.geoid}:${row.period}`, row]));
  if (candidate.size !== 1950) throw new Error("TRREB archive coverage check failed");
  index = candidate;
  return index;
}

export function readArchivedResale(geoid: string, year: number, month?: number) {
  const period = month === undefined ? String(year) : `${year}-${String(month).padStart(2, "0")}`;
  const row = archiveIndex().get(`${geoid}:${period}`);
  return row ? { ...row, release_id: SOURCE_RELEASE, archive_sha256: ARCHIVE_SHA256, preview_only: false } : undefined;
}
