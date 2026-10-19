import { workspaceInfo } from "@/lib/workspaces";
import type { Metadata, Viewport } from "next";
import { Cinzel, Playfair_Display } from "next/font/google";
import type { ReactNode } from "react";
import { WindowShell, type ShellStatus } from "./shell";
import { SmoothScrollProvider } from "@/components/smooth-scroll-provider";
import { apiMode } from "@/lib/env";
import { getSession } from "@/lib/session";
import "./globals.css";
import "@fiona/ui/styles.css";
import "./screens.css";

// Downloaded at build time and served from this site, so the browser never calls Google Fonts.
const cinzel = Cinzel({ subsets: ["latin"], weight: ["600", "700", "800"], variable: "--font-cinzel", display: "swap" });
const playfair = Playfair_Display({ subsets: ["latin"], weight: ["600", "700", "800"], style: ["normal", "italic"], variable: "--font-playfair", display: "swap" });

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
