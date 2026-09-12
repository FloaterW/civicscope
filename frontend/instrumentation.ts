import type { Instrumentation } from "next";

export const onRequestError: Instrumentation.onRequestError = (_error, _request, context) => {
  console.error(JSON.stringify({
    event: "server_error",
    route: context.routePath,
    type: context.routeType,
    release: process.env.VERCEL_GIT_COMMIT_SHA ?? "local",
  }));
};
