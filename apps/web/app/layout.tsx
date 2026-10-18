import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { WindowShell, type ShellStatus } from "./shell";
import { SmoothScrollProvider } from "@/components/smooth-scroll-provider";
import { apiMode } from "@/lib/env";
import { getSession } from "@/lib/session";
import "./globals.css";
import "@fiona/ui/styles.css";

export const metadata: Metadata = {
  title: "Fiona",
  description: "A window onto Fiona, the AI finance team that is checked before it acts.",
  applicationName: "Fiona",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f7f5" },
    { media: "(prefers-color-scheme: dark)", color: "#111713" },
  ],
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const live = apiMode() === "live" || (process.env.FIONA_MODE ?? "mock") === "live";
  const status: ShellStatus = {
    ledger: live ? "live" : "demo",
    guardian: (process.env.FIONA_LLM_PROVIDER ?? "replay") === "claude_cli" ? "live" : "replay",
    currency: "PKR",
    timezone: "Asia/Karachi",
  };
  const session = await getSession();
  const user = session
    ? { name: session.name, email: session.email, role: session.role, workspace: session.tenantId, demo: session.demo, superAdmin: session.superAdmin }
    : null;
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Playfair+Display:ital,wght@0,600;0,700;0,800;1,600&display=swap"
          rel="stylesheet"
        />
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("fiona:theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`,
          }}
        />
      </head>
      <body>
        <SmoothScrollProvider>
          <WindowShell user={user} status={status}>{children}</WindowShell>
        </SmoothScrollProvider>
      </body>
    </html>
  );
}
