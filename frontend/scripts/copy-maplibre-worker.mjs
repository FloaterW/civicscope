import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Next.js does not emit the worker's sibling module automatically. Keep both
// versioned assets together and self-hosted under the existing CSP.
const manifest = createRequire(import.meta.url).resolve("maplibre-gl/package.json");
const { version } = JSON.parse(readFileSync(manifest, "utf8"));
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const destination = path.join(root, "public", "maplibre", version);
mkdirSync(destination, { recursive: true });
for (const name of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(path.join(path.dirname(manifest), "dist", name), path.join(destination, name));
}
