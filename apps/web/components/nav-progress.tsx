"use client";

import { useEffect, useState } from "react";

/**
 * A slim bar at the top of the window that starts the moment an in-app link is clicked and
 * completes when the new page's content has arrived (not just its loading skeleton). Pages
 * render on the server, so without it a click can look ignored for a second.
 */
export function NavProgress() {
  const [phase, setPhase] = useState<"idle" | "loading" | "done">("idle");

  useEffect(() => {
    let timer = 0;
    let observer: MutationObserver | null = null;

    const finish = () => {
      observer?.disconnect();
      observer = null;
      window.clearTimeout(timer);
      setPhase("done");
    };

    function onClick(e: MouseEvent) {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[href]");
      if (!(a instanceof HTMLAnchorElement) || a.target === "_blank" || a.hasAttribute("download")) return;
      const url = new URL(a.href, location.href);
      const from = location.pathname;
      if (url.origin !== location.origin || url.pathname === from) return;

      setPhase("loading");
      observer?.disconnect();
      // Done once the address has changed and the loading skeleton is gone.
      observer = new MutationObserver(() => {
        if (location.pathname !== from && !document.querySelector(".loading-page")) finish();
      });
      observer.observe(document.body, { childList: true, subtree: true });
      window.clearTimeout(timer);
      // Never leave the bar hanging if a navigation is cancelled.
      timer = window.setTimeout(finish, 12_000);
    }

    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("click", onClick);
      observer?.disconnect();
      window.clearTimeout(timer);
    };
  }, []);

  return <div className={`nav-progress ${phase === "loading" ? "is-loading" : phase === "done" ? "is-done" : ""}`} aria-hidden="true" />;
}
