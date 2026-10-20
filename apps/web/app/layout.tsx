import { workspaceInfo } from "@/lib/workspaces";
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import { WindowShell, type ShellStatus } from "./shell";
import { SmoothScrollProvider } from "@/components/smooth-scroll-provider";
import { apiMode } from "@/lib/env";
import { getSession } from "@/lib/session";
import "./globals.css";
import "@fiona/ui/styles.css";
import "./screens.css";

// Bundled with the app (from @fontsource), so nothing is fetched from Google at build or run time.
const cinzel = localFont({
  src: [
    { path: "../node_modules/@fontsource/cinzel/files/cinzel-latin-600-normal.woff2", weight: "600", style: "normal" },
    { path: "../node_modules/@fontsource/cinzel/files/cinzel-latin-700-normal.woff2", weight: "700", style: "normal" },
    { path: "../node_modules/@fontsource/cinzel/files/cinzel-latin-800-normal.woff2", weight: "800", style: "normal" },
  ],
  variable: "--font-cinzel",
  display: "swap",
});
const playfair = localFont({
  src: [
    { path: "../node_modules/@fontsource/playfair-display/files/playfair-display-latin-600-normal.woff2", weight: "600", style: "normal" },
    { path: "../node_modules/@fontsource/playfair-display/files/playfair-display-latin-600-italic.woff2", weight: "600", style: "italic" },
    { path: "../node_modules/@fontsource/playfair-display/files/playfair-display-latin-700-normal.woff2", weight: "700", style: "normal" },
    { path: "../node_modules/@fontsource/playfair-display/files/playfair-display-latin-700-italic.woff2", weight: "700", style: "italic" },
    { path: "../node_modules/@fontsource/playfair-display/files/playfair-display-latin-800-normal.woff2", weight: "800", style: "normal" },
    { path: "../node_modules/@fontsource/playfair-display/files/playfair-display-latin-800-italic.woff2", weight: "800", style: "italic" },
  ],
  variable: "--font-playfair",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Fiona",
  description: "A window onto Fiona, the AI finance team that is checked before it acts.",
  applicationName: "Fiona",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  colorScheme: "light",
  themeColor: "#f6f7f5",
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const live = apiMode() === "live" || (process.env.FIONA_MODE ?? "mock") === "live";
  const session = await getSession();
  const workspace = workspaceInfo(session?.tenantId ?? null);
  const status: ShellStatus = {
    ledger: live ? "live" : "demo",
    guardian: (process.env.FIONA_LLM_PROVIDER ?? "replay") === "claude_cli" ? "live" : "replay",
    currency: workspace?.currency ?? "—",
    timezone: workspace?.timezone ?? "UTC",
    // An unregistered workspace is not known to be real, so it is labelled synthetic too.
    synthetic: workspace?.synthetic ?? true,
  };
  const user = session
    ? { name: session.name, email: session.email, role: session.role, workspace: session.tenantId, demo: session.demo, superAdmin: session.superAdmin }
    : null;
  return (
    <html lang="en" data-theme="light" data-scroll-behavior="smooth" className={`${cinzel.variable} ${playfair.variable}`} suppressHydrationWarning>
      <body>
        <SmoothScrollProvider>
          <WindowShell user={user} status={status}>{children}</WindowShell>
        </SmoothScrollProvider>
      </body>
    </html>
  );
}
