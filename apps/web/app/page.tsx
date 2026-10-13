import { apiMode } from "@/lib/env";

const SERVICES = [
  { name: "Window", path: "/api/healthz", port: 3000 },
  { name: "Engine", path: "/healthz", port: 8000 },
  { name: "Agents", path: "/healthz", port: 8100 },
  { name: "Guardian", path: "/healthz", port: 8200 },
] as const;

export default function Home() {
  const mode = apiMode();

  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center px-4 py-16 sm:px-8">
      <p className="flex items-center gap-3 text-sm text-(--color-ink-muted)">
        <span className="font-semibold tracking-wide text-(--color-ink)">Fiona</span>
        <span
          className="rounded border border-(--color-rule) px-2 py-0.5 text-xs"
          aria-label={mode === "mock" ? "Showing mock data" : "Connected to live services"}
        >
          {mode === "mock" ? "Mock data" : "Live"}
        </span>
      </p>

      <h1 className="mt-6 text-3xl font-semibold tracking-tight sm:text-4xl">The Window</h1>
      <p className="mt-4 max-w-prose text-base leading-relaxed text-(--color-ink-muted)">
        Fiona&apos;s agents run as a service, whether or not this window is open. The console shell
        (agent rail, briefing, approvals and command bar) arrives with task A3.
      </p>

      <table className="mt-10 w-full border-t border-(--color-rule) text-sm">
        <caption className="sr-only">Local service health endpoints</caption>
        <tbody>
          {SERVICES.map((s) => (
            <tr key={s.name} className="border-b border-(--color-rule)">
              <th scope="row" className="py-3 text-left font-medium">
                {s.name}
              </th>
              <td className="py-3 text-right font-mono text-(--color-ink-muted) tabular-nums">
                :{s.port}
                {s.path}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
