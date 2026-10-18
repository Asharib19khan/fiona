"use client";

import { useState } from "react";
import { USERS, type UserSession } from "./auth-modal";

interface LoginPageProps {
  onLogin: (user: UserSession) => void;
  currentTheme: "light" | "dark";
  onToggleTheme: () => void;
}

export function LoginPage({ onLogin, currentTheme, onToggleTheme }: LoginPageProps) {
  const [selectedUser, setSelectedUser] = useState<UserSession>(USERS[0]!);
  const [activeTab, setActiveTab] = useState<"passkey" | "credentials">("passkey");
  const [authenticating, setAuthenticating] = useState(false);
  const [authStep, setAuthStep] = useState<string>("");
  const [email, setEmail] = useState("asharib@karachiapparel.com");
  const [password, setPassword] = useState("••••••••••••••••");
  const [tenantId, setTenantId] = useState("karachi-apparel-sovereign-01");
  const [rememberDevice, setRememberDevice] = useState(true);

  function handlePasskeyLogin(user: UserSession) {
    setSelectedUser(user);
    setAuthenticating(true);
    setAuthStep("Querying FIDO2 Hardware Enclave...");

    setTimeout(() => {
      setAuthStep("Verifying RFC 8785 Ed25519 Signature...");
    }, 450);

    setTimeout(() => {
      setAuthStep("Guardian Invariant Gauntlet: Cleared");
    }, 900);

    setTimeout(() => {
      setAuthenticating(false);
      onLogin(user);
    }, 1250);
  }

  function handleCredentialsSubmit(e: React.FormEvent) {
    e.preventDefault();
    setAuthenticating(true);
    setAuthStep("Authenticating Corporate SSO...");

    setTimeout(() => {
      setAuthStep("Validating Tenant Security Policies...");
    }, 500);

    setTimeout(() => {
      setAuthenticating(false);
      onLogin(selectedUser);
    }, 1100);
  }

  return (
    <div className="login-viewport" role="main" aria-label="Fiona Sovereign Login">
      {/* Ambient background depth */}
      <div className="login-backdrop" />
      <div className="login-ambient-glow" />

      {/* Top utility row with theme switcher */}
      <header className="login-topbar">
        <div className="login-telemetry-badge">
          <span className="telemetry-ping" />
          <span>Sovereign Node 01 · Invariant Gauntlet Armed</span>
        </div>
        <button
          type="button"
          className="login-theme-toggle"
          onClick={onToggleTheme}
          aria-label={`Switch to ${currentTheme === "dark" ? "light" : "dark"} mode`}
          title={`Switch to ${currentTheme === "dark" ? "light" : "dark"} mode`}
        >
          {currentTheme === "dark" ? (
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

      {/* Main Login Card */}
      <div className="login-card-container">
        <div className="login-card">
          {/* Brand Wordmark Header */}
          <div className="login-brand-header">
            <h1 className="login-wordmark">FIONA</h1>
            <p className="login-brand-sub">SOVEREIGN TREASURY OS</p>
            <div className="login-security-pill">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              <span>Hardware Enclave · Zero-Trust Verification</span>
            </div>
          </div>

          {/* Authentication Method Tabs */}
          <div className="login-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "passkey"}
              className={`login-tab ${activeTab === "passkey" ? "login-tab-active" : ""}`}
              onClick={() => setActiveTab("passkey")}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M12 2a10 10 0 0 0-7.07 17.07" />
                <path d="M12 22a10 10 0 0 0 7.07-2.93" />
                <path d="M22 12a10 10 0 0 0-2.93-7.07" />
                <path d="M2 12a10 10 0 0 0 2.93 7.07" />
              </svg>
              <span>Executive Passkey</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "credentials"}
              className={`login-tab ${activeTab === "credentials" ? "login-tab-active" : ""}`}
              onClick={() => setActiveTab("credentials")}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect width="20" height="16" x="2" y="4" rx="2" />
                <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
              </svg>
              <span>Corporate SSO</span>
            </button>
          </div>

          {/* Tab 1: Executive Passkey / Quick Sovereign Personas */}
          {activeTab === "passkey" ? (
            <div className="login-passkey-view">
              <div className="login-view-instruction">
                <span>Select executive identity to sign cryptographic challenge:</span>
              </div>

              <div className="login-persona-grid">
                {USERS.map((user) => {
                  const isSelected = selectedUser.id === user.id;
                  return (
                    <button
                      key={user.id}
                      type="button"
                      className={`login-persona-card ${isSelected ? "login-persona-selected" : ""}`}
                      onClick={() => setSelectedUser(user)}
                      disabled={authenticating}
                    >
                      <div className="persona-avatar-wrap" style={{ background: user.avatar }}>
                        <span>{user.initials}</span>
                      </div>
                      <div className="persona-info-wrap">
                        <div className="persona-name-row">
                          <strong className="persona-name">{user.name}</strong>
                          {user.role === "owner" && <span className="persona-badge owner-badge">Signer</span>}
                          {user.role === "risk_officer" && <span className="persona-badge risk-badge">Guardian</span>}
                          {user.role === "treasurer" && <span className="persona-badge treasurer-badge">Operator</span>}
                          {user.role === "auditor" && <span className="persona-badge auditor-badge">Auditor</span>}
                        </div>
                        <span className="persona-title">{user.title}</span>
                        <span className="persona-mandate">{user.mandateLimit}</span>
                      </div>
                      <div className="persona-radio-dot" />
                    </button>
                  );
                })}
              </div>

              {/* Passkey Biometric Action Button */}
              <button
                type="button"
                className="login-submit-btn"
                onClick={() => handlePasskeyLogin(selectedUser)}
                disabled={authenticating}
              >
                {authenticating ? (
                  <div className="login-scanning-feedback">
                    <span className="passkey-scan-spinner" />
                    <span>{authStep}</span>
                  </div>
                ) : (
                  <>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 11c0 2.21-1.79 4-4 4s-4-1.79-4-4 1.79-4 4-4 4 1.79 4 4Z" />
                      <path d="M16 11V7a5 5 0 0 0-10 0" />
                      <path d="M12 15v4" />
                      <path d="M10 19h4" />
                    </svg>
                    <span>Authenticate as {selectedUser.name}</span>
                  </>
                )}
              </button>
            </div>
          ) : (
            /* Tab 2: Corporate SSO & Enterprise Key */
            <form className="login-credentials-form" onSubmit={handleCredentialsSubmit}>
              <div className="login-field-group">
                <label htmlFor="login-email" className="login-field-label">Corporate Email</label>
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="login-input"
                  required
                  disabled={authenticating}
                />
              </div>

              <div className="login-field-group">
                <label htmlFor="login-password" className="login-field-label">Enterprise Access Key</label>
                <input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="login-input"
                  required
                  disabled={authenticating}
                />
              </div>

              <div className="login-field-group">
                <label htmlFor="login-tenant" className="login-field-label">Sovereign Tenant ID</label>
                <input
                  id="login-tenant"
                  type="text"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  className="login-input"
                  required
                  disabled={authenticating}
                />
              </div>

              <div className="login-checkbox-row">
                <label className="login-checkbox-label">
                  <input
                    type="checkbox"
                    checked={rememberDevice}
                    onChange={(e) => setRememberDevice(e.target.checked)}
                    disabled={authenticating}
                  />
                  <span>Persist Hardware Enclave credentials</span>
                </label>
              </div>

              <button
                type="submit"
                className="login-submit-btn"
                disabled={authenticating}
              >
                {authenticating ? (
                  <div className="login-scanning-feedback">
                    <span className="passkey-scan-spinner" />
                    <span>{authStep}</span>
                  </div>
                ) : (
                  <>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                      <polyline points="10 17 15 12 10 7" />
                      <line x1="15" x2="3" y1="12" y2="12" />
                    </svg>
                    <span>Authorize Sovereign Session</span>
                  </>
                )}
              </button>
            </form>
          )}

          {/* Security & Regulatory Telemetry Footer */}
          <footer className="login-card-footer">
            <div className="login-footer-meta">
              <span>RFC 8785 Canonical State</span>
              <span className="meta-sep">·</span>
              <span>Karachi Apparel Co.</span>
              <span className="meta-sep">·</span>
              <span>256-bit Enclave Verified</span>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
