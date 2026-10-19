"use client";

import { useEffect, useState } from "react";

export function greetingFor(hour: number): string {
  if (hour >= 5 && hour < 12) return "Good morning";
  if (hour >= 12 && hour < 17) return "Good afternoon";
  if (hour >= 17 && hour < 21) return "Good evening";
  return "Good night";
}

/** "Good morning, Sara." on the viewer's own clock, re-checked every minute. */
export function Greeting({ firstName }: { firstName: string }) {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    const tick = () => setText(greetingFor(new Date().getHours()));
    tick();
    const timer = window.setInterval(tick, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  // Before the browser clock is known, greet without a time of day rather than guess.
  return <h1>{text ?? "Hello"}, {firstName}.</h1>;
}
