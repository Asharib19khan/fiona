"use client";

import { useState } from "react";

export interface UserSession {
  id: string;
  name: string;
  title: string;
  role: "owner" | "risk_officer" | "treasurer" | "auditor";
  avatar: string;
  initials: string;
  mandateLimit: string;
}

export const USERS: UserSession[] = [
  {
    id: "usr_asharib",
    name: "Asharib Khan",
    title: "Founder & Chief Executive",
    role: "owner",
    avatar: "linear-gradient(135deg, #2563EB, #1D4ED8)",
    initials: "AK",
    mandateLimit: "PKR 100,000,000",
  },
  {
    id: "usr_daniyal",
    name: "Daniyal",
    title: "Chief Risk Officer & Guardian Lead",
    role: "risk_officer",
    avatar: "linear-gradient(135deg, #059669, #047857)",
    initials: "DN",
    mandateLimit: "Invariant Enforcement G-01..G-15",
  },
  {
    id: "usr_yahya",
    name: "Yahya",
    title: "Head of Treasury & Liquidity",
    role: "treasurer",
    avatar: "linear-gradient(135deg, #D97706, #B45309)",
    initials: "YH",
    mandateLimit: "PKR 150,000 Autonomous",
  },
  {
    id: "usr_auditor",
    name: "Tsinghua / WeBank Delegation",
    title: "Competition Evaluation Auditor",
    role: "auditor",
    avatar: "linear-gradient(135deg, #7C3AED, #6D2842)",
    initials: "TH",
    mandateLimit: "Read-Only Cryptographic Audit",
  },
];

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: UserSession;
  onSelectUser: (user: UserSession) => void;
  onSignOut?: () => void;
}

export function AuthModal({ isOpen, onClose, currentUser, onSelectUser, onSignOut }: AuthModalProps) {
  const [authenticating, setAuthenticating] = useState(false);
  const [authSuccess, setAuthSuccess] = useState(false);

  if (!isOpen) return null;

  function handlePasskey(user: UserSession) {
    setAuthenticating(true);
    setTimeout(() => {
      setAuthenticating(false);
      setAuthSuccess(true);
      setTimeout(() => {
        setAuthSuccess(false);
        onSelectUser(user);
        onClose();
      }, 400);
    }, 700);
  }

  return (
    <div className="overlay-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">ENTERPRISE ACCESS CONTROL</span>
            <h2 id="auth-title">Sign In & Identity Delegation</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close sign in dialog">×</button>
        </div>

        <p className="auth-intro">
          Select an authenticated operator session or switch security privileges. Every transaction is signed and hash-chained to the active identity.
        </p>

        <div className="auth-user-list">
          {USERS.map((user) => {
            const isSelected = user.id === currentUser.id;
            return (
              <div
                key={user.id}
                className={`auth-user-card ${isSelected ? "auth-user-active" : ""}`}
                onClick={() => handlePasskey(user)}
              >
                <div className="auth-user-avatar" style={{ background: user.avatar }}>
                  {user.initials}
                </div>
                <div className="auth-user-info">
                  <div className="auth-user-top">
                    <strong>{user.name}</strong>
                    {isSelected && <span className="auth-active-chip">Active Session</span>}
                  </div>
                  <small className="auth-user-title">{user.title}</small>
                  <span className="auth-user-mandate">Mandate: {user.mandateLimit}</span>
                </div>
                <button className="button button-quiet auth-switch-btn" type="button">
                  {isSelected ? "Current" : "Switch →"}
                </button>
              </div>
            );
          })}
        </div>

        <div className="auth-telemetry-box">
          <div className="auth-telemetry-row">
            <span>Passkey / WebAuthn Hardware Enclave:</span>
            <strong className="status-positive">Active · Tier-1 Hardware Verified</strong>
          </div>
          <div className="auth-telemetry-row">
            <span>Active Tenant:</span>
            <strong>Karachi Apparel Co. (ten_karachi_apparel)</strong>
          </div>
          <div className="auth-telemetry-row">
            <span>Audit Standard:</span>
            <strong>RFC 8785 SHA-256 Canonical Chain</strong>
          </div>
        </div>

        {onSignOut && (
          <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end" }}>
            <button
              type="button"
              className="button button-quiet"
              style={{ color: "var(--danger, #ef4444)", borderColor: "rgba(239, 68, 68, 0.2)" }}
              onClick={() => {
                onClose();
                onSignOut();
              }}
            >
              Sign Out & Lock Workspace ⇥
            </button>
          </div>
        )}

        {authenticating && (
          <div className="auth-biometric-toast">
            <span className="auth-spinner" />
            <span>Verifying WebAuthn Biometric Passkey...</span>
          </div>
        )}
        {authSuccess && (
          <div className="auth-biometric-toast auth-toast-success">
            <span>✓ Identity Attested · Ephemeral JWT Minted</span>
          </div>
        )}
      </section>
    </div>
  );
}
