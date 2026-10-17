"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { AgentChip, AutonomyBadge, StateChip } from "@fiona/ui";
import { CommandBar } from "../components/command-bar";

const navigation = [
  { label: "Briefing", href: "/", icon: "⌂" },
  { label: "Approvals", href: "/approvals", icon: "▣" },
  { label: "Cash forecast", href: "/forecast", icon: "↗" },
  { label: "Financing", href: "/financing", icon: "◇" },
  { label: "Analysis", href: "/analysis", icon: "⌁" },
  { label: "Bills", href: "/bills", icon: "▤" },
  { label: "Reconcile", href: "/reconcile", icon: "⇄" },
  { label: "Sandbox wallet", href: "/wallet", icon: "◈" },
  { label: "Inventory", href: "/inventory", icon: "▤" },
  { label: "Import", href: "/import", icon: "⇧" },
  { label: "Launch Lab", href: "/launch-lab", icon: "✳" },
  { label: "Council", href: "/council", icon: "◉" },
  { label: "Audit trail", href: "/audit", icon: "⌁" },
];

const agents = [
  { name: "Controller", role: "Bookkeeping", level: "Prepare only" },
  { name: "Treasurer", role: "Payments", level: "Up to PKR 150k" },
  { name: "CFO Strategist", role: "Decisions", level: "Recommend" },
  { name: "Growth Analyst", role: "Planning", level: "Recommend" },
  { name: "Guardian", role: "Independent review", level: "Always checks" },
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
    // Storage is optional: private browsing and embedded previews can disable it.
  }
}

export function WindowShell({ children, mockMode }: { children: ReactNode; mockMode: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const [railOpen, setRailOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [devPanelOpen, setDevPanelOpen] = useState(false);
  const [scenario, setScenario] = useState("default");
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
      } else if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "d") {
        event.preventDefault();
        const current = new URL(window.location.href).searchParams.get("scenario");
        setScenario(current ?? "default");
        setDevPanelOpen((open) => !open);
      } else if (event.key === "Escape") {
        setPaletteOpen(false);
        setHelpOpen(false);
        setDevPanelOpen(false);
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
    try { window.localStorage.setItem("fiona:theme", next); } catch { /* Theme still works for this session. */ }
  }

  return (
    <div className={`window ${railOpen ? "window-with-rail" : "window-rail-closed"} ${inspectorOpen ? "window-with-inspector" : "window-inspector-closed"}`}>
      <header className="topbar">
        <div className="brand-lockup"><span className="brand-symbol" aria-hidden="true">f</span><span>fiona<span className="brand-period">.</span></span></div>
        <button className="icon-button rail-toggle" type="button" onClick={() => { setRailOpen((open) => { savePreference("fiona:rail", !open); return !open; }); }} aria-label={railOpen ? "Close navigation" : "Open navigation"} aria-expanded={railOpen}>☰</button>
        <div className="workspace-picker">
          <span className="workspace-avatar">KA</span><span><strong>Karachi Apparel</strong><small>Owner workspace</small></span><span className="chevron">⌄</span>
        </div>
        <div className="topbar-spacer" />
        <StateChip>{mockMode ? "Mock data" : "Live reads disabled"}</StateChip>
        <StateChip>{mockMode ? "Simulated wallet" : "Wallet locked"}</StateChip>
        <button className="icon-button theme-toggle" type="button" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>{theme === "dark" ? "☼" : "☾"}</button>
        <div className="profile-button" title="Demo owner">AK</div>
      </header>

      <aside className={`sidebar ${railOpen ? "" : "sidebar-hidden"}`} aria-label="Main navigation">
        <div className="side-section-label">WORKSPACE</div>
        <nav className="primary-nav">
          {navigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return <Link className={`nav-item ${active ? "nav-item-active" : ""}`} href={item.href} key={item.href} aria-current={active ? "page" : undefined}>
              <span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>
            </Link>;
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="side-section-label">YOUR BUSINESS</div>
          <Link className={`nav-item ${pathname.startsWith("/settings") ? "nav-item-active" : ""}`} href="/settings/mandates"><span className="nav-icon" aria-hidden="true">⚙</span><span>Mandates & limits</span></Link>
          <div className="business-card"><span className="business-avatar">KA</span><div><strong>Karachi Apparel</strong><small>PKR · Asia/Karachi</small></div></div>
        </div>
      </aside>

      <main className="canvas">
        <div className="mobile-context"><span className="brand-symbol">f</span><span>Karachi Apparel</span><StateChip>Mock data</StateChip></div>
        <div className="canvas-content">{children}</div>
        <footer className="statusbar"><span><i className="status-led" />Mock preview ready</span><span>Snapshot · 22 Oct 2026</span><span>PKR · Asia/Karachi</span></footer>
      </main>

      <aside className={`inspector ${inspectorOpen ? "" : "inspector-hidden"}`} aria-label="Agent activity">
        <div className="inspector-heading"><div><span className="eyebrow">YOUR FINANCE TEAM</span><h2>Agents</h2></div><button className="icon-button" type="button" aria-label="Close agent panel" onClick={() => { setInspectorOpen(false); savePreference("fiona:inspector", false); }}>×</button></div>
        <div className="agent-list">{agents.map((agent, index) => <div className="agent-row" key={agent.name}><AgentChip name={agent.name} role={agent.role} /><AutonomyBadge>{agent.level}</AutonomyBadge><span className={`agent-presence ${index === 4 ? "presence-review" : ""}`} role="img" aria-label="Illustrative demo marker" /></div>)}</div>
        <div className="inspector-divider" />
        <div className="inspector-heading activity-heading"><div><span className="eyebrow">SAMPLE ACTIVITY</span><h2>Demo timeline</h2></div><Link className="text-button" href="/audit">View all</Link></div>
        <ol className="activity-list">
          <li><span className="activity-mark activity-green">✓</span><div><strong>Cash forecast refreshed</strong><p>Treasurer · 4 min ago</p></div></li>
          <li><span className="activity-mark activity-amber">!</span><div><strong>3 bills need your review</strong><p>Controller · 18 min ago</p></div></li>
          <li><span className="activity-mark activity-muted">↻</span><div><strong>Inventory analysis ready</strong><p>Growth Analyst · 1 hr ago</p></div></li>
        </ol>
        <div className="inspector-bottom"><span className="shield-mark">◈</span><p><strong>Guardian review is part of the design</strong><br />Service integration is not connected in this preview.</p></div>
      </aside>

      <nav className="mobile-nav" aria-label="Mobile navigation">{navigation.slice(0, 5).map((item) => <Link href={item.href} key={item.href} className={item.href === "/" ? pathname === "/" ? "mobile-nav-active" : "" : pathname.startsWith(item.href) ? "mobile-nav-active" : ""}><span aria-hidden="true">{item.icon}</span><small>{item.label === "Cash forecast" ? "Cash" : item.label}</small></Link>)}</nav>

      {!inspectorOpen && <button className="reopen-inspector" type="button" onClick={() => { setInspectorOpen(true); savePreference("fiona:inspector", true); }} aria-label="Open agent panel">◉</button>}

      <CommandBar
        isOpen={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onToggleTheme={toggleTheme}
        currentTheme={theme}
      />
      {helpOpen && <div className="overlay-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setHelpOpen(false); }}><section className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="shortcuts-title"><div className="dialog-heading"><div><span className="eyebrow">QUICK REFERENCE</span><h2 id="shortcuts-title">Keyboard shortcuts</h2></div><button className="icon-button" onClick={() => setHelpOpen(false)} aria-label="Close shortcuts">×</button></div><dl className="shortcut-list"><div><dt>Open command palette</dt><dd><kbd>⌘</kbd><kbd>K</kbd></dd></div><div><dt>Show keyboard shortcuts</dt><dd><kbd>?</kbd></dd></div><div><dt>Toggle navigation</dt><dd><kbd>[</kbd></dd></div><div><dt>Toggle agent panel</dt><dd><kbd>]</kbd></dd></div><div><dt>Close dialog</dt><dd><kbd>Esc</kbd></dd></div><div><dt>Developer scenarios</dt><dd><kbd>Ctrl</kbd><kbd>Shift</kbd><kbd>D</kbd></dd></div></dl></section></div>}
      {devPanelOpen && <div className="overlay-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setDevPanelOpen(false); }}><section className="help-dialog scenario-dialog" role="dialog" aria-modal="true" aria-labelledby="scenario-title"><div className="dialog-heading"><div><span className="eyebrow">MOCK PREVIEW</span><h2 id="scenario-title">Switch briefing scenario</h2></div><button className="icon-button" onClick={() => setDevPanelOpen(false)} aria-label="Close scenario switcher">×</button></div><p>Scenarios change the visible sample only. They never submit or execute a proposal.</p><label className="scenario-select-label" htmlFor="scenario-select">Briefing scenario</label><select id="scenario-select" value={scenario} onChange={(event) => { const next = new URL(window.location.href); if (event.target.value === "default") next.searchParams.delete("scenario"); else next.searchParams.set("scenario", event.target.value); router.replace(`${next.pathname}${next.search}${next.hash}`); setScenario(event.target.value); setDevPanelOpen(false); }}><option value="default">Standard seeded briefing</option><option value="planted-bill">Planted bill · blocked</option><option value="clean">Clean · no open findings</option><option value="escalate-over-cap">Over cap · escalation</option><option value="degraded">Degraded · partial sources</option><option value="empty">Empty state</option><option value="error">Error state</option><option value="replayed">Replayed response</option></select></section></div>}
    </div>
  );
}
