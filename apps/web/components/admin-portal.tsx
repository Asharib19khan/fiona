"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, EmptyState } from "@fiona/ui";
import { WORKSPACES } from "@/lib/workspaces";

interface AdminUser {
  id: string;
  email: string;
  name: string;
  tenantId: string | null;
  role: "owner" | "finance" | null;
  superAdmin: boolean;
  disabled: boolean;
  createdAt: string;
  lastSignInAt: string | null;
}


function when(iso: string | null): string {
  if (!iso) return "never";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Karachi" }).format(new Date(iso));
}

async function call(url: string, init?: RequestInit): Promise<Record<string, unknown>> {
  const res = await fetch(url, { cache: "no-store", ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) } });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) throw new Error(String((data.error as Record<string, unknown> | undefined)?.message ?? "The request failed."));
  return data;
}

/** The super admin's account list and the form to set up a new account. */
export function AdminPortal() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ email: string; password: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", name: "", tenantId: WORKSPACES[0]!.id, role: "owner" });

  const load = useCallback(async () => {
    try {
      setUsers(((await call("/api/admin/users")).users as AdminUser[]) ?? []);
      setProblem(null);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "Accounts could not be loaded.");
    }
  }, []);

  useEffect(() => {
    const first = window.setTimeout(load, 0);
    return () => window.clearTimeout(first);
  }, [load]);

  async function create(event: { preventDefault(): void }) {
    event.preventDefault();
    setBusy("create");
    setNotice(null);
    setSecret(null);
    try {
      const data = await call("/api/admin/users", { method: "POST", body: JSON.stringify(form) });
      const user = data.user as AdminUser;
      setSecret({ email: user.email, password: String(data.temporaryPassword) });
      setForm({ email: "", name: "", tenantId: form.tenantId, role: "owner" });
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "The account could not be created.");
    } finally {
      setBusy(null);
    }
  }

  async function change(user: AdminUser, body: Record<string, unknown>, done: string) {
    setBusy(user.id);
    setNotice(null);
    setSecret(null);
    try {
      const data = await call(`/api/admin/users/${user.id}`, { method: "PATCH", body: JSON.stringify(body) });
      if (data.temporaryPassword) setSecret({ email: user.email, password: String(data.temporaryPassword) });
      else setNotice(done);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "The change failed.");
    } finally {
      setBusy(null);
    }
  }

  async function remove(user: AdminUser) {
    if (!window.confirm(`Delete ${user.email}? This cannot be undone.`)) return;
    setBusy(user.id);
    try {
      await call(`/api/admin/users/${user.id}`, { method: "DELETE" });
      setNotice(`${user.email} was deleted.`);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "The account could not be deleted.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="admin-portal">
      <Card className="tier-panel">
        <div className="panel-heading"><div><span className="eyebrow">NEW ACCOUNT</span><h2>Set up a user</h2></div></div>
        <form className="admin-form" onSubmit={create}>
          <label><span className="spec-label">Email</span><input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label><span className="spec-label">Full name</span><input required minLength={2} maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>
            <span className="spec-label">Workspace</span>
            <select value={form.tenantId} onChange={(e) => setForm({ ...form, tenantId: e.target.value })}>
              {WORKSPACES.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
            </select>
          </label>
          <label>
            <span className="spec-label">Role</span>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="owner">Owner: approves payments, changes mandates</option>
              <option value="finance">Finance: approves payments</option>
            </select>
          </label>
          <button className="button button-primary" type="submit" disabled={busy !== null}>{busy === "create" ? "Creating…" : "Create account"}</button>
        </form>
      </Card>

      {secret && (
        <div className="admin-secret" role="status">
          <strong>Temporary password for {secret.email}</strong>
          <code>{secret.password}</code>
          <span>Shown once. Hand it over privately; they can change it from their account menu after signing in.</span>
        </div>
      )}
      {notice && <p className="mandate-notice" role="status">{notice}</p>}

      <Card className="tier-panel">
        <div className="panel-heading"><div><span className="eyebrow">ALL ACCOUNTS</span><h2>{users ? `${users.length} account${users.length === 1 ? "" : "s"}` : "Loading…"}</h2></div></div>
        {problem && <EmptyState title="Accounts could not be loaded">{problem}</EmptyState>}
        {users && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Person</th><th>Workspace</th><th>Role</th><th>Last sign-in</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td><strong>{u.name}</strong><br /><span className="admin-muted">{u.email}</span></td>
                    <td>{u.tenantId ?? "—"}</td>
                    <td>
                      {u.superAdmin ? "Super admin · owner" : (
                        <select value={u.role ?? ""} disabled={busy !== null} onChange={(e) => change(u, { role: e.target.value }, `${u.email} is now ${e.target.value}.`)} aria-label={`Role for ${u.email}`}>
                          <option value="owner">Owner</option>
                          <option value="finance">Finance</option>
                        </select>
                      )}
                    </td>
                    <td>{when(u.lastSignInAt)}</td>
                    <td>{u.disabled ? "Disabled" : "Active"}</td>
                    <td className="admin-actions">
                      {u.superAdmin ? <span className="admin-muted">Protected</span> : (
                        <>
                          <button className="button button-quiet" type="button" disabled={busy !== null} onClick={() => change(u, { resetPassword: true }, "")}>Reset password</button>
                          <button className="button button-secondary" type="button" disabled={busy !== null} onClick={() => change(u, { disabled: !u.disabled }, `${u.email} is ${u.disabled ? "enabled" : "disabled"}.`)}>{u.disabled ? "Enable" : "Disable"}</button>
                          <button className="button button-danger" type="button" disabled={busy !== null} onClick={() => remove(u)}>Delete</button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
