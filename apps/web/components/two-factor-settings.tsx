"use client";

import { useEffect, useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/browser";

type View =
  | { kind: "loading" }
  | { kind: "off" }
  | { kind: "on"; factorId: string }
  | { kind: "setup"; factorId: string; qr: string; secret: string }
  | { kind: "confirm-off"; factorId: string }
  | { kind: "error"; message: string };

/**
 * Turn two-step verification on (scan a QR code with an authenticator app, confirm one code) or
 * off. Once on, the server refuses this account's sessions until the code is entered at sign-in.
 */
export function TwoFactorSettings({ onEnabled }: { onEnabled?: () => void } = {}) {
  const [view, setView] = useState<View>({ kind: "loading" });
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void supabaseBrowser().auth.mfa.listFactors().then(({ data, error }) => {
      if (!live) return;
      if (error) return setView({ kind: "error", message: "Couldn't load your two-step settings." });
      const factor = data.totp.find((item) => item.status === "verified");
      setView(factor ? { kind: "on", factorId: factor.id } : { kind: "off" });
    });
    return () => { live = false; };
  }, []);

  async function startSetup() {
    setBusy(true);
    setNote(null);
    const mfa = supabaseBrowser().auth.mfa;
    // Clear any half-finished setup first, so a fresh QR code can be made.
    const { data: existing } = await mfa.listFactors();
    for (const factor of existing?.all ?? []) {
      if (factor.factor_type === "totp" && factor.status === "unverified") await mfa.unenroll({ factorId: factor.id });
    }
    const { data, error } = await mfa.enroll({ factorType: "totp", friendlyName: `Authenticator ${new Date().toISOString().slice(0, 16)}`, issuer: "Fiona" });
    setBusy(false);
    if (error || !data) return setNote(error?.message ?? "Couldn't start setup. Try again.");
    setCode("");
    setView({ kind: "setup", factorId: data.id, qr: data.totp.qr_code, secret: data.totp.secret });
  }

  async function confirmSetup(factorId: string) {
    if (code.length !== 6) return;
    setBusy(true);
    setNote(null);
    const { error } = await supabaseBrowser().auth.mfa.challengeAndVerify({ factorId, code });
    setBusy(false);
    if (error) {
      setCode("");
      return setNote(error.status === 429 ? "Too many attempts. Wait a minute, then try again." : "That code didn't match. Enter the newest code from the app.");
    }
    setView({ kind: "on", factorId });
    setNote("Two-step verification is on. You'll enter a code each time you sign in.");
    onEnabled?.();
  }

  async function cancelSetup(factorId: string) {
    setBusy(true);
    await supabaseBrowser().auth.mfa.unenroll({ factorId });
    setBusy(false);
    setNote(null);
    setView({ kind: "off" });
  }

  async function turnOff(factorId: string) {
    setBusy(true);
    setNote(null);
    const { error } = await supabaseBrowser().auth.mfa.unenroll({ factorId });
    setBusy(false);
    if (error) return setNote(error.message);
    setView({ kind: "off" });
    setNote("Two-step verification is off.");
  }

  return (
    <section className="twofa" aria-labelledby="twofa-title">
      <div className="twofa-head">
        <div>
          <h3 id="twofa-title">Two-step verification</h3>
          <p>A code from an authenticator app (Google Authenticator, 1Password, Microsoft Authenticator) at every sign-in.</p>
        </div>
        {(view.kind === "on" || view.kind === "confirm-off") && <span className="twofa-status twofa-status-on">On</span>}
        {view.kind === "off" && <span className="twofa-status">Off</span>}
      </div>

      {view.kind === "loading" && <p className="twofa-muted">Checking…</p>}
      {view.kind === "error" && <p className="twofa-muted" role="alert">{view.message}</p>}

      {view.kind === "off" && (
        <button className="button button-primary" type="button" onClick={startSetup} disabled={busy}>
          {busy ? "Preparing…" : "Turn on two-step verification"}
        </button>
      )}

      {view.kind === "setup" && (
        <div className="twofa-setup">
          <ol className="twofa-steps">
            <li>Scan this QR code with your authenticator app.</li>
            <li>Enter the 6-digit code it shows to finish.</li>
          </ol>
          <div className="twofa-qr-row">
            {/* eslint-disable-next-line @next/next/no-img-element -- a data: URI from Supabase, not an asset to optimise */}
            <img className="twofa-qr" src={view.qr} alt="QR code for your authenticator app" width={156} height={156} />
            <div className="twofa-secret">
              <span>Can&apos;t scan? Enter this key instead:</span>
              <code>{view.secret.replace(/(.{4})/g, "$1 ").trim()}</code>
            </div>
          </div>
          <form className="twofa-verify" onSubmit={(e) => { e.preventDefault(); void confirmSetup(view.factorId); }}>
            <label className="spec-label" htmlFor="twofa-code">6-digit code</label>
            <div className="twofa-verify-row">
              <input
                id="twofa-code"
                className="twofa-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="000000"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                disabled={busy}
                autoFocus
              />
              <button className="button button-primary" type="submit" disabled={busy || code.length !== 6}>{busy ? "Checking…" : "Verify and turn on"}</button>
            </div>
          </form>
          <button className="button button-quiet" type="button" onClick={() => cancelSetup(view.factorId)} disabled={busy}>Cancel</button>
        </div>
      )}

      {view.kind === "on" && (
        <button className="button button-quiet" type="button" onClick={() => { setNote(null); setView({ kind: "confirm-off", factorId: view.factorId }); }} disabled={busy}>
          Turn off
        </button>
      )}

      {view.kind === "confirm-off" && (
        <div className="twofa-confirm" role="alertdialog" aria-label="Turn off two-step verification?">
          <p>Turn off two-step verification? Anyone with your password could then sign in and approve payments.</p>
          <div className="twofa-confirm-actions">
            <button className="button button-secondary" type="button" onClick={() => setView({ kind: "on", factorId: view.factorId })} disabled={busy}>Keep it on</button>
            <button className="button button-danger" type="button" onClick={() => turnOff(view.factorId)} disabled={busy}>{busy ? "Turning off…" : "Turn off"}</button>
          </div>
        </div>
      )}

      {note && <p className="twofa-note" role="status">{note}</p>}
    </section>
  );
}
