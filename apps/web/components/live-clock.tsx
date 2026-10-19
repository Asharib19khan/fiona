"use client";

import { useEffect, useState } from "react";
import { StateChip } from "@fiona/ui";

const FORMAT = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/** Today's date and time on the viewer's clock, updated every few seconds. */
export function LiveClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    // Set on the client only, so the server render never shows a stale time.
    const tick = () => setNow(new Date());
    tick();
    const timer = window.setInterval(tick, 5_000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <StateChip>
      <time dateTime={now?.toISOString()} suppressHydrationWarning>
        {now ? FORMAT.format(now).replace(" at ", ", ") : " "}
      </time>
    </StateChip>
  );
}
