import { reportClientError } from "@/lib/error-reporting";

window.addEventListener("error", () => reportClientError("uncaught"));
window.addEventListener("unhandledrejection", (event) => {
  if (event.reason instanceof Error && event.reason.name === "AbortError") return;
  reportClientError("unhandled_rejection");
});
