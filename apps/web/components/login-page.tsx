"use client";

import { useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/browser";

/**
 * Sign in with Supabase Auth (email and password). The workspace and role come from the
 * account itself (app_metadata, set by an admin), never from this form.
 */
export function LoginPage({ next }: { next: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    typeof document !== "undefined" && document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );

  function toggleTheme() {
    const value = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = value;
    setTheme(value);
    try { window.localStorage.setItem("fiona:theme", value); } catch { /* theme still applies for this visit */ }
  }

  async function signIn(event: { preventDefault(): void }) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const { error: failure } = await supabaseBrowser().auth.signInWithPassword({ email: email.trim(), password });
    if (failure) {
      setPending(false);
      setError(failure.message === "Invalid login credentials" ? "That email and password don't match an account." : failure.message);
      return;
    }
    // A full navigation, so the server renders the workspace with the new session cookie.
    window.location.assign(next.startsWith("/") && !next.startsWith("//") ? next : "/");
  }

  return (
    <div className="login-viewport" role="main" aria-label="Sign in to Fiona">
      <div className="login-backdrop" />
      <div className="login-ambient-glow" />

      <header className="login-topbar">
        <button
          type="button"
          className="login-theme-toggle"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
            </svg>
          )}
        </button>
      </header>

      <div className="login-card-container">
        <div className="login-card">
          <div className="login-brand-header">
            <h1 className="login-wordmark">FIONA</h1>
            <p className="login-brand-sub">YOUR AI FINANCE TEAM</p>
          </div>

          <form className="login-credentials-form" onSubmit={signIn} noValidate={false}>
            <div className="login-field-group">
              <label htmlFor="login-email" className="login-field-label">Email</label>
              <input
                id="login-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="login-input"
                required
                disabled={pending}
              />
            </div>
            <div className="login-field-group">
              <label htmlFor="login-password" className="login-field-label">Password</label>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="login-input"
                required
                disabled={pending}
              />
            </div>

            {error && <p className="login-error" role="alert">{error}</p>}

            <button type="submit" className="login-submit-btn" disabled={pending || !email || !password}>
              {pending ? (
                <div className="login-scanning-feedback">
                  <span className="passkey-scan-spinner" />
                  <span>Signing in…</span>
                </div>
              ) : (
                <>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                    <polyline points="10 17 15 12 10 7" />
                    <line x1="15" x2="3" y1="12" y2="12" />
                  </svg>
                  <span>Sign in</span>
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
