import { cp, mkdir } from "node:fs/promises";

// Vercel builds use the platform adapter rather than Next.js standalone output.
if (process.env.VERCEL) process.exit(0);

async function copyDirectory(source, destination) {
  try {
    await cp(source, destination, { recursive: true, force: true });
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

await mkdir(".next/standalone/.next", { recursive: true });
await Promise.all([
  copyDirectory("public", ".next/standalone/public"),
  copyDirectory(".next/static", ".next/standalone/.next/static")
]);
