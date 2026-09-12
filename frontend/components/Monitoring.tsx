"use client";

import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";

function withoutQuery(url: string): string {
  return url.split(/[?#]/, 1)[0];
}

export function Monitoring() {
  return <>
    <Analytics beforeSend={(event) => ({ ...event, url: withoutQuery(event.url) })} />
    <SpeedInsights beforeSend={(event) => ({ ...event, url: withoutQuery(event.url) })} />
  </>;
}
