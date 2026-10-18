"use client";

import { useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/browser";

/** The signed-in person as the shell shows them (from the server session, never the browser). */
export interface ShellUser {
  name: string;
  email: string | null;
  role: "owner" | "finance" | null;
  workspace: string | null;
  demo: boolean;
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]!.toUpperCase()).join("") || "?";
}

export function roleLabel(role: ShellUser["role"]): string {
  return role === "owner" ? "Owner · approves payments" : role === "finance" ? "Finance · approves payments" : "No workspace role";
}

/** Who is signed in, their workspace and role, and signing out. */
export function AuthModal({ isOpen, onClose, user }: { isOpen: boolean; onClose: () => void; user: ShellUser }) {
  const [signingOut, setSigningOut] = useState(false);
  if (!isOpen) return null;

  async function signOut() {
    setSigningOut(true);
    await supabaseBrowser().auth.signOut();
    window.location.assign("/login");
  }

  return (
    <div className="overlay-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="account-title">
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">SIGNED IN</span>
            <h2 id="account-title">{user.name}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close account details">×</button>
        </div>
        <dl className="shortcut-list">
          <div><dt>Email</dt><dd>{user.email ?? "Local development (no sign-in configured)"}</dd></div>
          <div><dt>Workspace</dt><dd>{user.workspace ?? "Not assigned"}</dd></div>
          <div><dt>Role</dt><dd>{roleLabel(user.role)}</dd></div>
        </dl>
        {!user.demo && (
          <button className="button button-secondary" type="button" onClick={signOut} disabled={signingOut} style={{ marginTop: 16 }}>
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        )}
      </section>
    </div>
  );
}
