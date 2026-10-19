"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { initials } from "./auth-modal";

export interface WorkspaceOption {
  id: string;
  name: string;
}

/**
 * The workspace menu in the top bar: which business you are in, the workspaces you can use,
 * and shortcuts to that workspace's setup. A person belongs to one workspace today (set by an
 * admin on their account); the list renders every workspace it is given, so more appear here
 * once accounts can join several.
 */
export function WorkspaceSwitcher({
  workspaces,
  currentId,
  sourceLabel,
  superAdmin,
}: {
  workspaces: WorkspaceOption[];
  currentId: string | null;
  /** Where the figures come from, e.g. "Live ledger" or "Demo data". */
  sourceLabel: string;
  superAdmin: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const current = workspaces.find((workspace) => workspace.id === currentId) ?? null;
  const currentName = current?.name ?? "No workspace";

  // Close on a click outside; move focus into the menu when it opens.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    menuRef.current?.querySelector<HTMLElement>("[role='menuitem'], [role='menuitemradio']")?.focus();
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function close(returnFocus: boolean) {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>("[role='menuitem'], [role='menuitemradio']") ?? []);
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      items[(index + step + items.length) % items.length]?.focus();
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      items[event.key === "Home" ? 0 : items.length - 1]?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div className="workspace-switcher" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="workspace-picker"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="workspace-menu"
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) { event.preventDefault(); setOpen(true); }
        }}
      >
        <span className="workspace-avatar">{initials(currentName)}</span>
        <span>
          <strong>{currentName}</strong>
          <small>{sourceLabel}</small>
        </span>
        <span className={`chevron ${open ? "chevron-open" : ""}`} aria-hidden="true">⌄</span>
      </button>

      {open && (
        <div className="workspace-menu" id="workspace-menu" role="menu" aria-label="Workspaces" ref={menuRef} onKeyDown={onMenuKeyDown}
          onClick={(event) => { if ((event.target as HTMLElement).closest("a")) setOpen(false); }}>
          <div className="workspace-menu-label">Your workspaces</div>
          {workspaces.length === 0 ? (
            <p className="workspace-menu-empty">You are not in a workspace yet. An admin adds you to one.</p>
          ) : (
            <div role="group" aria-label="Your workspaces">
              {workspaces.map((workspace) => {
                const active = workspace.id === currentId;
                return (
                  <button
                    key={workspace.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={active}
                    className={`workspace-menu-item ${active ? "workspace-menu-item-active" : ""}`}
                    onClick={() => close(true)}
                  >
                    <span className="workspace-avatar">{initials(workspace.name)}</span>
                    <span className="workspace-menu-text">
                      <strong>{workspace.name}</strong>
                      <small>{active ? sourceLabel : workspace.id}</small>
                    </span>
                    {active && <span className="workspace-menu-check" aria-hidden="true">✓</span>}
                  </button>
                );
              })}
            </div>
          )}

          <div className="workspace-menu-divider" role="separator" />
          <Link className="workspace-menu-link" role="menuitem" href="/settings/mandates">Mandates &amp; policies</Link>
          <Link className="workspace-menu-link" role="menuitem" href="/import">Import ledger data</Link>
          {superAdmin ? (
            <Link className="workspace-menu-link" role="menuitem" href="/admin">Manage people &amp; workspaces</Link>
          ) : (
            <p className="workspace-menu-note">Need access to another business? Ask your Fiona admin to add you.</p>
          )}
        </div>
      )}
    </div>
  );
}
