"use client";

import { useState, type CSSProperties } from "react";
import { PasswordField, RevealRow, SigninCard, SigninShell, SubmitButton } from "@/components/login-page";
import { supabaseBrowser } from "@/lib/supabase/browser";

const MIN_LENGTH = 10;
const delay = (ms: number) => ({ "--d": `${ms}ms` }) as CSSProperties;

/** Choose a new password after following the reset email (the link already signed the person in). */
export function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [phase, setPhase] = useState<"idle" | "pending" | "success">("idle");
  const [error, setError] = useState<string | null>(null);
  const [shaking, setShaking] = useState(false);
  const longEnough = password.length >= MIN_LENGTH;
  const matches = password.length > 0 && password === confirm;

  async function save(event: { preventDefault(): void }) {
    event.preventDefault();
    if (!longEnough || !matches) return;
    setPhase("pending");
    setError(null);
    const { error: failure } = await supabaseBrowser().auth.updateUser({ password });
    if (failure) {
      setPhase("idle");
      setShaking(true);
      setError(
        failure.code === "same_password"
          ? "Choose a password you haven't used here before."
          : failure.code === "weak_password"
            ? "That password is too easy to guess. Try a longer one."
            : failure.message,
      );
      return;
    }
    setPhase("success");
    window.location.assign("/");
  }

  return (
    <SigninShell label="Choose a new password">
      <SigninCard shaking={shaking} onShakeEnd={() => setShaking(false)}>
        <h2 className="signin-title signin-rise" style={delay(140)}>Choose a new password</h2>
        <p className="signin-sub signin-rise" style={delay(190)}>You&apos;ll use it the next time you sign in to Fiona.</p>

        <form className="signin-form" onSubmit={save}>
          <PasswordField id="new-password" label="New password" value={password} onChange={setPassword} autoComplete="new-password" placeholder={`At least ${MIN_LENGTH} characters`} disabled={phase !== "idle"} invalid={Boolean(error)} style={delay(240)} autoFocus />
          <PasswordField id="confirm-password" label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" placeholder="Type it again" disabled={phase !== "idle"} invalid={confirm.length > 0 && !matches} style={delay(290)} />

          <ul className="signin-rules signin-rise" style={delay(320)} aria-label="Password requirements">
            <li className={longEnough ? "signin-rule-met" : undefined}>At least {MIN_LENGTH} characters</li>
            <li className={matches ? "signin-rule-met" : undefined}>Both passwords match</li>
          </ul>

          <RevealRow open={Boolean(error)}>
            <p className="login-error signin-error" role={error ? "alert" : undefined}>{error ?? " "}</p>
          </RevealRow>

          <SubmitButton phase={phase} disabled={!longEnough || !matches} idle="Save new password" pending="Saving…" success="Password saved. Opening your workspace…" style={delay(360)} />
        </form>
      </SigninCard>
    </SigninShell>
  );
}
