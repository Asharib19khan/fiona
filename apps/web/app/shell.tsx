"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { AutonomyBadge, StateChip } from "@fiona/ui";
import { CommandBar } from "../components/command-bar";
import { BootScreen } from "../components/boot-screen";
import { AgentActivity } from "../components/agent-activity";
import { AuthModal, initials, roleLabel, type ShellUser } from "../components/auth-modal";

// Luxury SVG Icon set for navigation
function NavIcon({ name }: { name: string }) {
  switch (name) {
    case "briefing":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="7" height="9" x="3" y="3" rx="1.5" />
          <rect width="7" height="5" x="14" y="3" rx="1.5" />
          <rect width="7" height="9" x="14" y="12" rx="1.5" />
          <rect width="7" height="5" x="3" y="16" rx="1.5" />
        </svg>
      );
    case "approvals":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      );
    case "forecast":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
          <polyline points="16 7 22 7 22 13" />
        </svg>
      );
    case "financing":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="8" cy="8" r="6" />
          <path d="M18.09 10.37A6 6 0 1 1 10.34 18" />
          <path d="M7 6h2v4H7z" />
          <path d="m14 14 3 3" />
        </svg>
      );
    case "analysis":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 3v18h18" />
          <path d="m19 9-5 5-4-4-3 3" />
        </svg>
      );
    case "bills":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z" />
          <path d="M16 8h-6" />
          <path d="M16 12h-6" />
          <path d="M10 16h-4" />
        </svg>
      );
    case "reconcile":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m16 3 4 4-4 4" />
          <path d="M20 7H4" />
          <path d="m8 21-4-4 4-4" />
          <path d="M4 17h16" />
        </svg>
      );
    case "wallet":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="20" height="14" x="2" y="5" rx="3" />
          <path d="M2 10h20" />
          <circle cx="16" cy="14" r="1.5" />
        </svg>
      );
    case "inventory":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
          <path d="m3.3 7 8.7 5 8.7-5" />
          <path d="M12 22V12" />
        </svg>
      );
    case "import":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" x2="12" y1="3" y2="15" />
        </svg>
      );
    case "launch-lab":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2v8" />
          <path d="m4.93 10.93 5.66 5.66" />
          <path d="M2 12h8" />
          <path d="M20 12h2" />
          <path d="m19.07 4.93-1.41 1.41" />
          <path d="M15.5 15.5 22 22" />
        </svg>
      );
    case "council":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case "audit":
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2" />
          <path d="M9 12h6" />
          <path d="M9 16h6" />
          <path d="M9 8h6" />
        </svg>
      );
    default:
      return <span>◈</span>;
  }
}

const navigation = [
  { label: "Briefing", href: "/", iconKey: "briefing" },
  { label: "Approvals", href: "/approvals", iconKey: "approvals" },
  { label: "Cash forecast", href: "/forecast", iconKey: "forecast" },
  { label: "Financing", href: "/financing", iconKey: "financing" },
  { label: "Financial analysis", href: "/analysis", iconKey: "analysis" },
  { label: "Bills & AP", href: "/bills", iconKey: "bills" },
  { label: "Reconciliation", href: "/reconcile", iconKey: "reconcile" },
  { label: "Autonomous Vault", href: "/wallet", iconKey: "wallet" },
  { label: "Inventory", href: "/inventory", iconKey: "inventory" },
  { label: "Ledger Import", href: "/import", iconKey: "import" },
  { label: "Launch Lab", href: "/launch-lab", iconKey: "launch-lab" },
  { label: "Council", href: "/council", iconKey: "council" },
  { label: "Audit Chain", href: "/audit", iconKey: "audit" },
];

const agents = [
  { name: "Controller", role: "Reconciliation & bill checks", level: "Reports", code: "CT", color: "agent-ct" },
  { name: "Treasurer", role: "Payment planning", level: "Prepares · you approve", code: "TR", color: "agent-tr" },
  { name: "CFO Strategist", role: "Capital decisions", level: "Advises", code: "CF", color: "agent-cf" },
  { name: "Growth Analyst", role: "Stock & growth", level: "Advises", code: "GA", color: "agent-ga" },
  { name: "Guardian", role: "Independent checks", level: "Reviews every proposal", code: "G", color: "agent-g" },
];

function safePreference(key: string, fallback: boolean) {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "true";
  } catch {
    return fallback;
  }
}

function savePreference(key: string, value: boolean) {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Storage is optional
  }
}

export interface ShellStatus {
  /** live: the engine reads the posted ledger; demo: labelled synthetic fixtures. */
  ledger: "live" | "demo";
  /** live: the Guardian reviews with its own model; replay: recorded reviews only. */
  guardian: "live" | "replay";
  currency: string;
  timezone: string;
}

export function WindowShell({ children, user, status }: { children: ReactNode; user: ShellUser | null; status: ShellStatus }) {
  const pathname = usePathname();
  const [railOpen, setRailOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setRailOpen(safePreference("fiona:rail", true));
      setInspectorOpen(safePreference("fiona:inspector", true));
      const stored = document.documentElement.dataset.theme;
      setTheme(stored === "dark" ? "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      } else if (event.key === "Escape") {
        setPaletteOpen(false);
        setHelpOpen(false);
        setAuthOpen(false);
      } else if (!typing && event.key === "?" && !event.metaKey && !event.ctrlKey) {
        setHelpOpen((open) => !open);
      } else if (!typing && event.key === "[") {
        setRailOpen((open) => { savePreference("fiona:rail", !open); return !open; });
      } else if (!typing && event.key === "]") {
        setInspectorOpen((open) => { savePreference("fiona:inspector", !open); return !open; });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    setTheme(next);
    try { window.localStorage.setItem("fiona:theme", next); } catch { /* noop */ }
  }

  // Not signed in: the proxy has sent this visitor to /login, which renders on its own.
  if (!user) return <>{children}</>;

  const workspaceName = user.workspace === "ten_karachi_apparel" ? "Karachi Apparel" : (user.workspace ?? "No workspace");

  return (
    <>
      <BootScreen />

      <div className={`window ${railOpen ? "window-with-rail" : "window-rail-closed"} ${inspectorOpen ? "window-with-inspector" : "window-inspector-closed"}`}>
        {/* Luxury Top Navigation Bar */}
        <header className="topbar">
          {/* Bespoke Geometric Fiona Monogram Brand */}
          <Link href="/" className="brand-lockup-luxury" aria-label="Fiona Home">
            <svg className="brand-emblem-svg" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="32" height="32" rx="9" fill="url(#brand-grad-bg)" />
              <circle cx="16" cy="16" r="11" stroke="url(#brand-grad-ring)" strokeWidth="1.5" />
              <path d="M16 7V25M11 13H21M11 19H21" stroke="#FFFFFF" strokeWidth="1.7" strokeLinecap="round" />
              <circle cx="16" cy="16" r="2.5" fill="#38BDF8" />
              <defs>
                <linearGradient id="brand-grad-bg" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#0F172A" />
                  <stop offset="1" stopColor="#1E293B" />
                </linearGradient>
                <linearGradient id="brand-grad-ring" x1="5" y1="5" x2="27" y2="27" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#38BDF8" />
                  <stop offset="1" stopColor="#6366F1" />
                </linearGradient>
              </defs>
            </svg>
            <div
              className="brand-text-block"
              onClick={(e) => {
                if (e.shiftKey) {
                  e.preventDefault();
                  window.dispatchEvent(new CustomEvent("fiona:replay-intro"));
                }
              }}
              title="Shift+Click to replay boot intro"
            >
              <span className="brand-name-luxury">FIONA</span>
              <span className="brand-sub-luxury">TREASURY OS</span>
            </div>
          </Link>

          <button
            className="icon-button rail-toggle"
            type="button"
            onClick={() => { setRailOpen((open) => { savePreference("fiona:rail", !open); return !open; }); }}
            aria-label={railOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={railOpen}
          >
            ☰
          </button>

          {/* Active Enterprise Workspace Identifier */}
          <div className="workspace-picker">
            <span className="workspace-avatar">{initials(workspaceName)}</span>
            <span>
              <strong>{workspaceName}</strong>
              <small>{status.ledger === "live" ? "Live ledger" : "Demo data"}</small>
            </span>
            <span className="chevron">⌄</span>
          </div>

          <div className="topbar-spacer" />

          {/* Live Node Badges */}
          <div className="topbar-live-status" title={status.ledger === "live" ? "Figures are computed from your posted ledger." : "Figures come from labelled synthetic demo files."}>
            <span className="status-halo-dot" />
            <span className="status-label-top">{status.ledger === "live" ? "Live ledger" : "Demo data"}</span>
          </div>
          <StateChip>{status.guardian === "live" ? "Guardian reviewing live" : "Guardian: recorded reviews"}</StateChip>
          <StateChip>Sandbox wallet</StateChip>

          <button
            className="icon-button theme-toggle"
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? "☼" : "☾"}
          </button>

          {/* User Profile / Auth Switcher Button */}
          <button
            className="profile-button-luxury"
            type="button"
            onClick={() => setAuthOpen(true)}
            title="Account and sign out"
          >
            <div className="profile-badge-inner">{initials(user.name)}</div>
            <div className="profile-text-compact">
              <strong>{user.name}</strong>
              <small>{roleLabel(user.role).split(" · ")[0]}</small>
            </div>
          </button>
        </header>

        {/* Primary Sidebar Rail */}
        <aside className={`sidebar ${railOpen ? "" : "sidebar-hidden"}`} aria-label="Main navigation">
          <div className="side-section-label">TREASURY WORKSPACE</div>
          <nav className="primary-nav">
            {navigation.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link className={`nav-item ${active ? "nav-item-active" : ""}`} href={item.href} key={item.href} aria-current={active ? "page" : undefined}>
                  <span className="nav-icon"><NavIcon name={item.iconKey} /></span>
                  <span className="nav-label">{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="sidebar-bottom">
            <div className="side-section-label">ENTERPRISE GOVERNANCE</div>
            <Link className={`nav-item ${pathname.startsWith("/settings") ? "nav-item-active" : ""}`} href="/settings/mandates">
              <span className="nav-icon">⚙</span>
              <span>Mandates & Policies</span>
            </Link>
            {user.superAdmin && (
              <Link className={`nav-item ${pathname.startsWith("/admin") ? "nav-item-active" : ""}`} href="/admin">
                <span className="nav-icon">◎</span>
                <span>Accounts</span>
              </Link>
            )}
            <div className="business-card">
              <span className="business-avatar">{initials(workspaceName)}</span>
              <div>
                <strong>{workspaceName}</strong>
                <small>{status.currency} · {status.timezone}</small>
              </div>
            </div>
          </div>
        </aside>

        {/* Central Canvas Viewport */}
        <main className="canvas">
          <div className="mobile-context">
            <span className="brand-symbol">F</span>
            <span>{workspaceName}</span>
            <StateChip>{status.ledger === "live" ? "Live ledger" : "Demo data"}</StateChip>
          </div>
          <div className="canvas-content">{children}</div>
          <footer className="statusbar">
            <span><i className="status-led" />{status.ledger === "live" ? "Engine reading the posted ledger" : "Demo data"}</span>
            <span>Hash-chained audit log</span>
            <span>{status.currency} · {status.timezone}</span>
          </footer>
        </main>

        {/* Right Inspector: The 5 Autonomous Agents */}
        <aside className={`inspector ${inspectorOpen ? "" : "inspector-hidden"}`} aria-label="Agent activity">
          <div className="inspector-heading">
            <div>
              <span className="eyebrow">YOUR FINANCE TEAM</span>
              <h2>Agents</h2>
            </div>
            <button className="icon-button" type="button" aria-label="Close agent panel" onClick={() => { setInspectorOpen(false); savePreference("fiona:inspector", false); }}>
              ×
            </button>
          </div>

          {/* Revamped Luminous Agent Roster */}
          <div className="agent-list-luxury">
            {agents.map((agent) => (
              <div className="agent-card-luxury" key={agent.name}>
                <div className={`agent-avatar-luxury ${agent.color}`}>
                  <span>{agent.code}</span>
                  <span className="agent-live-pulse" />
                </div>
                <div className="agent-meta-luxury">
                  <div className="agent-name-row">
                    <strong>{agent.name}</strong>
                    <AutonomyBadge>{agent.level}</AutonomyBadge>
                  </div>
                  <span className="agent-role-sub">{agent.role}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="inspector-divider" />

          <AgentActivity />

          <div className="inspector-bottom-luxury">
            <div className="guardian-shield-badge">
              <span className="shield-icon">🛡</span>
              <div>
                <strong>Nothing pays without you</strong>
                <p>The Guardian checks every proposal against 15 rules, including an independent model review. Then you approve or reject it.</p>
              </div>
            </div>
          </div>
        </aside>

        {!inspectorOpen && (
          <button className="reopen-inspector" type="button" onClick={() => { setInspectorOpen(true); savePreference("fiona:inspector", true); }} aria-label="Open agent panel">
            ◉
          </button>
        )}

        <CommandBar
          isOpen={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onToggleTheme={toggleTheme}
          currentTheme={theme}
        />

        <AuthModal isOpen={authOpen} onClose={() => setAuthOpen(false)} user={user} />

        {helpOpen && (
          <div className="overlay-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setHelpOpen(false); }}>
            <section className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="shortcuts-title">
              <div className="dialog-heading">
                <div>
                  <span className="eyebrow">QUICK REFERENCE</span>
                  <h2 id="shortcuts-title">Executive Shortcuts</h2>
                </div>
                <button className="icon-button" onClick={() => setHelpOpen(false)} aria-label="Close shortcuts">×</button>
              </div>
              <dl className="shortcut-list">
                <div><dt>Open command palette</dt><dd><kbd>⌘</kbd><kbd>K</kbd></dd></div>
                <div><dt>Show keyboard shortcuts</dt><dd><kbd>?</kbd></dd></div>
                <div><dt>Toggle navigation rail</dt><dd><kbd>[</kbd></dd></div>
                <div><dt>Toggle agent council panel</dt><dd><kbd>]</kbd></dd></div>
                <div><dt>Close dialog</dt><dd><kbd>Esc</kbd></dd></div>
              </dl>
            </section>
          </div>
        )}
      </div>
    </>
  );
}
