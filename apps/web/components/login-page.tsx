"use client";

import { useEffect, useState, useSyncExternalStore, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { supabaseBrowser } from "@/lib/supabase/browser";

/** How a payment travels through Fiona: the same order the product enforces. */
const FLOW = [
  { role: "Treasurer", text: "Prepares the payment from your ledger.", status: "Prepared" },
  { role: "Guardian", text: "Checks it independently against your rules.", status: "Checked" },
  { role: "You", text: "Approve it. Only then does money move.", status: "Approved" },
];

type Phase = "idle" | "pending" | "success";
export type LoginMode = "signin" | "forgot" | "sent" | "mfa";

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
const delay = (ms: number) => ({ "--d": `${ms}ms` }) as CSSProperties;

function subscribeReducedMotion(onChange: () => void) {
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Cycles through the flow steps; holds on the last step when the visitor prefers less motion. */
function useFlowStep(): number {
  const reduced = useSyncExternalStore(subscribeReducedMotion, () => window.matchMedia(REDUCED_MOTION).matches, () => false);
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const timer = window.setInterval(() => setStep((current) => (current + 1) % (FLOW.length + 1)), 1900);
    return () => window.clearInterval(timer);
  }, [reduced]);
  // One extra beat on the full flow before it starts again.
  return reduced ? FLOW.length - 1 : Math.min(step, FLOW.length - 1);
}

/* ---------- Shared pieces (also used by the reset-password page) ---------- */

function Icon({ name }: { name: "mail" | "lock" | "shield" | "arrow" | "check" | "back" }) {
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  switch (name) {
    case "mail":
      return <svg {...common} strokeWidth={2} className="signin-icon"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></svg>;
    case "lock":
      return <svg {...common} strokeWidth={2} className="signin-icon"><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>;
    case "shield":
      return <svg {...common} strokeWidth={2} className="signin-icon"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" /></svg>;
    case "arrow":
      return <svg {...common} strokeWidth={2.4} className="signin-arrow"><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
    case "check":
      return <svg {...common} strokeWidth={3}><path className="signin-check" d="M20 6 9 17l-5-5" /></svg>;
    case "back":
      return <svg {...common} strokeWidth={2.2}><path d="M19 12H5M11 18l-6-6 6-6" /></svg>;
  }
}

/** The page frame: the brand panel on the left, the card on the right. */
export function SigninShell({ label, children }: { label: string; children: ReactNode }) {
  const step = useFlowStep();
  return (
    <div className="signin" role="main" aria-label={label}>
      <section className="signin-brand" aria-label="About Fiona">
        <span className="signin-aurora" aria-hidden="true" />

        <div className="signin-brand-top signin-rise" style={delay(60)}>
          <span className="signin-wordmark">FIONA</span>
          <span className="signin-tagline">Your AI finance team</span>
        </div>

        <div className="signin-brand-body">
          <p className="signin-kicker signin-rise" style={delay(120)}>Treasury, with a human in charge</p>
          <h1 className="signin-headline signin-rise" style={delay(180)}>
            A council of agents over one ledger. <span>You make the final call.</span>
          </h1>

          <ol
            className="signin-flow signin-rise"
            style={{ ...delay(260), "--progress": step / (FLOW.length - 1) } as CSSProperties}
            aria-label="How a payment moves through Fiona"
          >
            {FLOW.map((item, index) => {
              const state = index < step ? "done" : index === step ? "active" : "waiting";
              return (
                <li key={item.role} className={`signin-flow-step signin-flow-${state}`}>
                  <span className="signin-flow-node" aria-hidden="true">
                    {state === "done" ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                    ) : (
                      index + 1
                    )}
                  </span>
                  <div className="signin-flow-copy">
                    <div className="signin-flow-head">
                      <strong>{item.role}</strong>
                      <span className="signin-flow-status">{item.status}</span>
                    </div>
                    <p>{item.text}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </section>

      <section className="signin-panel">{children}</section>
    </div>
  );
}

/** The card, which shakes once when `shaking` turns on. */
export function SigninCard({ shaking, onShakeEnd, children }: { shaking: boolean; onShakeEnd: () => void; children: ReactNode }) {
  return (
    <div className={`signin-card${shaking ? " signin-shake" : ""}`} onAnimationEnd={(e) => { if (e.animationName === "signinShake") onShakeEnd(); }}>
      <span className="signin-wordmark signin-wordmark-compact" aria-hidden="true">FIONA</span>
      {children}
    </div>
  );
}

/** A row that slides open when it has something to say (errors, hints). */
export function RevealRow({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <div className={`signin-reveal-row${open ? " signin-reveal-row-open" : ""}`} aria-live="polite">
      <div>{children}</div>
    </div>
  );
}

export function PasswordField(props: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  placeholder: string;
  disabled: boolean;
  invalid: boolean;
  style?: CSSProperties;
  autoFocus?: boolean;
}) {
  const [shown, setShown] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const track = (event: KeyboardEvent<HTMLInputElement>) => setCapsLock(event.getModifierState?.("CapsLock") ?? false);
  return (
    <div className="signin-field signin-rise" style={props.style}>
      <label htmlFor={props.id}>{props.label}</label>
      <div className="signin-control">
        <Icon name="lock" />
        <input
          id={props.id}
          type={shown ? "text" : "password"}
          autoComplete={props.autoComplete}
          autoFocus={props.autoFocus}
          placeholder={props.placeholder}
          value={props.value}
          onChange={(e) => props.onChange(e.target.value)}
          onKeyDown={track}
          onKeyUp={track}
          onBlur={() => setCapsLock(false)}
          className="signin-input signin-input-reveal"
          aria-invalid={props.invalid || undefined}
          aria-describedby={capsLock ? `${props.id}-caps` : undefined}
          required
          disabled={props.disabled}
        />
        <button
          type="button"
          className="signin-reveal"
          onClick={() => setShown((value) => !value)}
          aria-label={shown ? "Hide password" : "Show password"}
          aria-pressed={shown}
          disabled={props.disabled}
        >
          {shown ? "Hide" : "Show"}
        </button>
      </div>
      <RevealRow open={capsLock}>
        <p id={`${props.id}-caps`} className="signin-hint">Caps Lock is on.</p>
      </RevealRow>
    </div>
  );
}

export function SubmitButton({ phase, disabled, idle, pending, success, style }: { phase: Phase; disabled: boolean; idle: string; pending: string; success: string; style?: CSSProperties }) {
  return (
    <button type="submit" className={`signin-submit signin-rise signin-submit-${phase}`} style={style} disabled={phase !== "idle" || disabled}>
      <span className="signin-submit-face" key={phase}>
        {phase === "pending" ? (
          <><span className="signin-spinner" aria-hidden="true" /><span>{pending}</span></>
        ) : phase === "success" ? (
          <><Icon name="check" /><span>{success}</span></>
        ) : (
          <><span>{idle}</span><Icon name="arrow" /></>
        )}
      </span>
    </button>
  );
}

/* ---------- The sign-in page ---------- */

/**
 * Sign in with Supabase Auth: email and password, then the authenticator code when the person
 * has two-step verification on. Also asks for a password-reset email. The workspace and role
 * come from the account itself (app_metadata, set by an admin), never from this form; the server
 * (proxy and session) enforces the code step, so skipping it here gains nothing.
 */
export function LoginPage({ next, initialMode = "signin", notice = null }: { next: string; initialMode?: LoginMode; notice?: string | null }) {
  const [mode, setMode] = useState<LoginMode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [shaking, setShaking] = useState(false);
  const busy = phase !== "idle";

  function go(nextMode: LoginMode) {
    setError(null);
    setPhase("idle");
    setMode(nextMode);
  }

  function fail(message: string) {
    setPhase("idle");
    setError(message);
    setShaking(true);
  }

  function enterWorkspace() {
    setPhase("success");
    // A full navigation, so the server renders the workspace with the new session cookie.
    window.location.assign(next);
  }

  async function signIn(event: { preventDefault(): void }) {
    event.preventDefault();
    setPhase("pending");
    setError(null);
    const supabase = supabaseBrowser();
    const { error: failure } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (failure) {
      fail(failure.message === "Invalid login credentials" ? "That email and password don't match an account." : failure.message);
      return;
    }
    setPassword("");
    const { data: level } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    if (level && level.nextLevel === "aal2" && level.currentLevel !== "aal2") {
      go("mfa");
      return;
    }
    enterWorkspace();
  }

  async function verifyCode(value: string) {
    if (busy || value.length !== 6) return;
    setPhase("pending");
    setError(null);
    const supabase = supabaseBrowser();
    const { data: factors, error: listError } = await supabase.auth.mfa.listFactors();
    const factor = factors?.totp.find((item) => item.status === "verified");
    if (listError || !factor) {
      fail("We couldn't find your authenticator. Sign in again, or ask your workspace owner for help.");
      return;
    }
    const { error: failure } = await supabase.auth.mfa.challengeAndVerify({ factorId: factor.id, code: value });
    if (failure) {
      setCode("");
      fail(failure.status === 429 ? "Too many attempts. Wait a minute, then try again." : "That code didn't work. Codes change every 30 seconds, so enter the newest one.");
      return;
    }
    enterWorkspace();
  }

  async function sendReset(event: { preventDefault(): void }) {
    event.preventDefault();
    setPhase("pending");
    setError(null);
    const { error: failure } = await supabaseBrowser().auth.resetPasswordForEmail(email.trim(), {
      redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
    });
    if (failure) {
      fail(failure.status === 429 ? "Too many requests. Wait a minute, then try again." : failure.message);
      return;
    }
    go("sent");
  }

  async function switchAccount() {
    setPhase("pending");
    await supabaseBrowser().auth.signOut();
    setCode("");
    go("signin");
  }

  return (
    <SigninShell label="Sign in to Fiona">
      <SigninCard shaking={shaking} onShakeEnd={() => setShaking(false)}>
        <div className="signin-step" key={mode}>
          {mode === "signin" && (
            <>
              <h2 className="signin-title signin-rise" style={delay(140)}>Welcome back</h2>
              <p className="signin-sub signin-rise" style={delay(190)}>Sign in with the account your workspace admin set up for you.</p>
              {notice && <p className="signin-notice signin-rise" style={delay(200)} role="status">{notice}</p>}

              <form className="signin-form" onSubmit={signIn}>
                <div className="signin-field signin-rise" style={delay(240)}>
                  <label htmlFor="login-email">Work email</label>
                  <div className="signin-control">
                    <Icon name="mail" />
                    <input
                      id="login-email"
                      type="email"
                      inputMode="email"
                      autoComplete="email"
                      autoFocus
                      placeholder="you@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="signin-input"
                      aria-invalid={error ? true : undefined}
                      required
                      disabled={busy}
                    />
                  </div>
                </div>

                <div className="signin-password-block">
                  <PasswordField
                    id="login-password"
                    label="Password"
                    value={password}
                    onChange={setPassword}
                    autoComplete="current-password"
                    placeholder="Your password"
                    disabled={busy}
                    invalid={Boolean(error)}
                    style={delay(290)}
                  />
                  <button type="button" className="signin-link signin-forgot signin-rise" style={delay(300)} onClick={() => go("forgot")} disabled={busy}>
                    Forgot password?
                  </button>
                </div>

                <RevealRow open={Boolean(error)}>
                  <p className="login-error signin-error" role={error ? "alert" : undefined}>{error ?? " "}</p>
                </RevealRow>

                <SubmitButton phase={phase} disabled={!email || !password} idle="Sign in" pending="Signing in…" success="Signed in. Opening your workspace…" style={delay(340)} />
              </form>

              <p className="signin-note signin-rise" style={delay(400)}>No account yet? Ask your workspace owner to invite you.</p>
            </>
          )}

          {mode === "mfa" && (
            <>
              <span className="signin-badge signin-rise" style={delay(60)} aria-hidden="true"><Icon name="shield" /></span>
              <h2 className="signin-title signin-rise" style={delay(100)}>Two-step verification</h2>
              <p className="signin-sub signin-rise" style={delay(150)}>Open your authenticator app and enter the 6-digit code for Fiona.</p>

              <form className="signin-form" onSubmit={(e) => { e.preventDefault(); void verifyCode(code); }}>
                <div className="signin-field signin-rise" style={delay(200)}>
                  <label htmlFor="login-code">Authentication code</label>
                  <input
                    id="login-code"
                    className="signin-input signin-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    autoFocus
                    pattern="[0-9]{6}"
                    maxLength={6}
                    placeholder="000000"
                    value={code}
                    onChange={(e) => {
                      const digits = e.target.value.replace(/\D/g, "").slice(0, 6);
                      setCode(digits);
                      if (digits.length === 6) void verifyCode(digits);
                    }}
                    aria-invalid={error ? true : undefined}
                    disabled={busy}
                  />
                </div>

                <RevealRow open={Boolean(error)}>
                  <p className="login-error signin-error" role={error ? "alert" : undefined}>{error ?? " "}</p>
                </RevealRow>

                <SubmitButton phase={phase} disabled={code.length !== 6} idle="Verify" pending="Checking code…" success="Verified. Opening your workspace…" style={delay(250)} />
              </form>

              <p className="signin-note signin-rise" style={delay(320)}>
                Lost your phone? Ask your workspace owner to reset two-step verification.{" "}
                <button type="button" className="signin-link" onClick={switchAccount} disabled={busy}>Use another account</button>
              </p>
            </>
          )}

          {mode === "forgot" && (
            <>
              <button type="button" className="signin-link signin-back signin-rise" style={delay(40)} onClick={() => go("signin")} disabled={busy}>
                <Icon name="back" /> Back to sign in
              </button>
              <h2 className="signin-title signin-rise" style={delay(100)}>Reset your password</h2>
              <p className="signin-sub signin-rise" style={delay(150)}>Enter your work email and we&apos;ll send you a link to choose a new password.</p>

              <form className="signin-form" onSubmit={sendReset}>
                <div className="signin-field signin-rise" style={delay(200)}>
                  <label htmlFor="reset-email">Work email</label>
                  <div className="signin-control">
                    <Icon name="mail" />
                    <input
                      id="reset-email"
                      type="email"
                      inputMode="email"
                      autoComplete="email"
                      autoFocus
                      placeholder="you@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="signin-input"
                      aria-invalid={error ? true : undefined}
                      required
                      disabled={busy}
                    />
                  </div>
                </div>

                <RevealRow open={Boolean(error)}>
                  <p className="login-error signin-error" role={error ? "alert" : undefined}>{error ?? " "}</p>
                </RevealRow>

                <SubmitButton phase={phase} disabled={!email.includes("@")} idle="Send reset link" pending="Sending…" success="Sent" style={delay(250)} />
              </form>
            </>
          )}

          {mode === "sent" && (
            <>
              <span className="signin-badge signin-badge-success signin-rise" style={delay(60)} aria-hidden="true"><Icon name="mail" /></span>
              <h2 className="signin-title signin-rise" style={delay(100)}>Check your email</h2>
              <p className="signin-sub signin-rise" style={delay(150)}>
                If an account exists for <strong>{email.trim()}</strong>, we&apos;ve sent a link to reset your password. Open it in this browser; it works once.
              </p>
              <button type="button" className="signin-submit signin-rise" style={delay(220)} onClick={() => go("signin")}>
                <span className="signin-submit-face"><span>Back to sign in</span></span>
              </button>
              <p className="signin-note signin-rise" style={delay(280)}>
                Nothing after a few minutes? Check spam, or{" "}
                <button type="button" className="signin-link" onClick={() => go("forgot")}>send it again</button>.
              </p>
            </>
          )}
        </div>
      </SigninCard>
    </SigninShell>
  );
}
