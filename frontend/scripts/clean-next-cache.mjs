import { existsSync, rmSync } from "node:fs";

if (existsSync(".next")) {
  try {
    rmSync(".next", { recursive: true, force: true });
    console.log("Removed .next cache.");
  } catch (error) {
    console.error("Could not remove .next. Stop the Next dev server and retry clean:next.");
    throw error;
  }
} else {
  console.log("No .next cache to remove.");
}
