"use client";

import { ErrorState } from "@fiona/ui";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="error-page"><span className="eyebrow">SOMETHING WENT WRONG</span><h1>This view hit a problem</h1>{error.digest ? <ErrorState requestId={error.digest} /> : <ErrorState />}<button className="button button-primary" onClick={() => reset()}>Try again</button></div>;
}
