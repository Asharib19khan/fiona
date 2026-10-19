"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { StateChip } from "@fiona/ui";
import { AgentFolder } from "../components/agent-folder";
import { WorkspaceSwitcher } from "../components/workspace-switcher";
import { workspaceLabel } from "../lib/workspaces";
import { CommandBar } from "../components/command-bar";
import { BootScreen } from "../components/boot-screen";
import { NavProgress } from "../components/nav-progress";
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
  /** The workspace is a generated demo company (synthetic ledger). */
  synthetic: boolean;
}

export function WindowShell({ children, user, status }: { children: ReactNode; user: ShellUser | null; status: ShellStatus }) {
  const pathname = usePathname();
  const [railOpen, setRailOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false); // phone: the full page list over the canvas
  const navRef = useRef<HTMLElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const [modKey, setModKey] = useState("Ctrl");

  // The top bar lifts off the page once you scroll, and shows the right shortcut key for this computer.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    const frame = window.requestAnimationFrame(() => {
      if (/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)) setModKey("⌘");
    });
    return () => { window.removeEventListener("scroll", onScroll); window.cancelAnimationFrame(frame); };
  }, []);

  const [indicator, setIndicator] = useState<{ top: number; height: number } | null>(null);

  // One highlight glides to the active page instead of each item lighting up on its own.
  useLayoutEffect(() => {
    const place = () => {
      const active = navRef.current?.querySelector<HTMLElement>(".nav-item-active");
      setIndicator(active ? { top: active.offsetTop, height: active.offsetHeight } : null);
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [pathname, railOpen]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setRailOpen(safePreference("fiona:rail", true));
      setInspectorOpen(safePreference("fiona:inspector", true));
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
        setMenuOpen(false);
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

  // Not signed in: the proxy has sent this visitor to /login, which renders on its own.
  if (!user) return <>{children}</>;

  const workspaceName = workspaceLabel(user.workspace ?? null);

  return (
    <>
      <BootScreen />
      <NavProgress />

      <div className={`window ${railOpen ? "window-with-rail" : "window-rail-closed"} ${inspectorOpen ? "window-with-inspector" : "window-inspector-closed"}`}>
        {/* Luxury Top Navigation Bar */}
        <header className={`topbar topbar-pro ${scrolled ? "is-scrolled" : ""}`}>
          {/* Fiona Brand Serif Wordmark */}
          <Link
            href="/"
            className="brand-lockup-luxury"
            aria-label="Fiona Home"
            onClick={(e) => {
              if (e.shiftKey) {
                e.preventDefault();
                window.dispatchEvent(new CustomEvent("fiona:replay-intro"));
              }
            }}
            title="Shift+Click to replay boot intro"
          >
            <img
              src="/fiona-logo.png"
              alt="Fiona"
              className="brand-logo-img brand-logo-light"
              width={75}
              height={32}
            />
            <img
              src="/fiona-logo-dark.png"
              alt="Fiona"
              className="brand-logo-img brand-logo-dark"
              width={75}
              height={32}
            />
          </Link>

          <button
            className="icon-button rail-toggle"
            type="button"
            onClick={() => { setRailOpen((open) => { savePreference("fiona:rail", !open); return !open; }); }}
            aria-label={railOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={railOpen}
            title={railOpen ? "Hide navigation ( [ )" : "Show navigation ( [ )"}
          >
            <svg className={`rail-icon ${railOpen ? "is-open" : ""}`} viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="4" width="18" height="16" rx="3" />
              <path className="rail-icon-divider" d="M9 4v16" />
              <path className="rail-icon-arrow" d="M15 10l-2 2 2 2" />
            </svg>
          </button>

          <span className="topbar-divider" aria-hidden="true" />

          {/* Active Enterprise Workspace Identifier */}
          <WorkspaceSwitcher
            workspaces={user.workspace ? [{ id: user.workspace, name: workspaceName }] : []}
            currentId={user.workspace ?? null}
            sourceLabel={`${status.ledger === "live" ? "Live ledger" : "Demo data"}${status.synthetic ? " · synthetic" : ""}`}
            superAdmin={Boolean(user.superAdmin)}
          />

          <div className="topbar-spacer" />

          <button className="topbar-search" type="button" onClick={() => setPaletteOpen(true)} aria-label="Search or jump to a page" aria-keyshortcuts="Control+K Meta+K">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
            <span className="topbar-search-label">Search or jump to…</span>
            <span className="topbar-kbd" aria-hidden="true"><kbd>{modKey}</kbd><kbd>K</kbd></span>
          </button>

          {/* System status: where figures come from, how the Guardian reviews, and that money is simulated */}
          <div className="topbar-status" role="group" aria-label="System status">
            <span className={`topbar-status-item ${status.ledger === "live" ? "is-live" : "is-demo"}`} tabIndex={0} data-tip={`${status.ledger === "live" ? "Figures are computed from the posted ledger." : "Figures come from labelled demo files."}${status.synthetic ? " This workspace is a generated demo company: its data is synthetic, not a real customer's." : ""}`}>
              <i aria-hidden="true" />{status.ledger === "live" ? "Live ledger" : "Demo data"}
            </span>
            <span className={`topbar-status-item ${status.guardian === "live" ? "is-live-blue" : "is-muted"}`} tabIndex={0} data-tip={status.guardian === "live" ? "The Guardian reviews every proposal with its own model, right now." : "The Guardian shows recorded reviews only."}>
              <i aria-hidden="true" />{status.guardian === "live" ? "Guardian reviewing live" : "Guardian: recorded reviews"}
            </span>
            <span className="topbar-status-item is-muted" tabIndex={0} data-tip="Payments run in a sandbox wallet. No real money moves.">
              <i aria-hidden="true" />Sandbox wallet
            </span>
          </div>

          <button className="icon-button topbar-help" type="button" onClick={() => setHelpOpen(true)} aria-label="Keyboard shortcuts" title="Keyboard shortcuts ( ? )">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.4" /><path d="M12 17h.01" /></svg>
          </button>

          {/* User Profile / Auth Switcher Button */}
          <button
            className="profile-button-luxury"
            type="button"
            onClick={() => setAuthOpen(true)}
            title="Account and sign out"
            aria-haspopup="dialog"
          >
            <div className="profile-badge-inner">{initials(user.name)}</div>
            <div className="profile-text-compact">
              <strong>{user.name}</strong>
              <small>{roleLabel(user.role).split(" · ")[0]}</small>
            </div>
            <svg className="profile-chevron" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
          </button>
        </header>

        {/* Primary Sidebar Rail */}
        <aside
          id="main-navigation"
          className={`sidebar ${railOpen ? "" : "sidebar-hidden"} ${menuOpen ? "sidebar-mobile-open" : ""}`}
          aria-label="Main navigation"
          onClick={(event) => { if ((event.target as HTMLElement).closest("a")) setMenuOpen(false); }}
        >
          <div className="side-section-label">TREASURY WORKSPACE</div>
          <nav className={`primary-nav ${indicator ? "has-indicator" : ""}`} ref={navRef}>
            <span className="nav-indicator" aria-hidden="true" style={indicator ? ({ "--y": `${indicator.top}px`, "--h": `${indicator.height}px` } as CSSProperties) : { opacity: 0 }} />
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
            <Link className={`nav-item ${pathname.startsWith("/settings/mandates") ? "nav-item-active" : ""}`} href="/settings/mandates">
              <span className="nav-icon">⚙</span>
              <span>Mandates & Policies</span>
            </Link>
            <Link className={`nav-item ${pathname.startsWith("/settings/ai") ? "nav-item-active" : ""}`} href="/settings/ai">
              <span className="nav-icon">✦</span>
              <span>AI connection</span>
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
            {status.synthetic && <span>Synthetic demo company · not real customer data</span>}
            <span>Hash-chained audit log</span>
            <span>{status.currency} · {status.timezone}</span>
          </footer>
        </main>

        {/* Phone: the four pages used most, plus the full list */}
        <nav className="mobile-nav" aria-label="Quick navigation">
          {navigation.filter((item) => ["/", "/approvals", "/bills", "/forecast"].includes(item.href)).map((item) => {
            const active = !menuOpen && (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href));
            return (
              <Link key={item.href} href={item.href} className={active ? "mobile-nav-active" : ""} aria-current={active ? "page" : undefined} onClick={() => setMenuOpen(false)}>
                <span><NavIcon name={item.iconKey} /></span>
                <small>{item.label === "Cash forecast" ? "Forecast" : item.label === "Bills & AP" ? "Bills" : item.label}</small>
              </Link>
            );
          })}
          <button type="button" className={menuOpen ? "mobile-nav-active" : ""} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen((open) => !open)}>
            <span aria-hidden="true">{menuOpen ? "✕" : "☰"}</span>
            <small>{menuOpen ? "Close" : "Menu"}</small>
          </button>
        </nav>

        {/* Right Inspector: The 5 Autonomous Agents */}
        <aside className={`inspector ${inspectorOpen ? "" : "inspector-hidden"}`} aria-label="Agent activity">
          <div className="inspector-heading">
            <button className="icon-button" type="button" style={{ marginLeft: "auto" }} aria-label="Close agent panel" onClick={() => { setInspectorOpen(false); savePreference("fiona:inspector", false); }}>
              ×
            </button>
          </div>

          {/* Agent roster: one page per agent in an interactive folder */}
          <AgentFolder agents={agents} />

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
