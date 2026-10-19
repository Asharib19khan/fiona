import { notFound, redirect } from "next/navigation";
import { StateChip } from "@fiona/ui";
import { AdminPortal } from "@/components/admin-portal";
import { AdminTwoStepGate } from "@/components/admin-two-step-gate";
import { AdminError, requireSuperAdmin } from "@/lib/admin";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  let needsTwoStep = false;
  try {
    await requireSuperAdmin();
  } catch (err) {
    // These two are raised only after the caller is confirmed as the super admin.
    if (err instanceof AdminError && err.code === "mfa_required") redirect("/login?next=/admin");
    if (err instanceof AdminError && err.code === "mfa_setup_required") needsTwoStep = true;
    else if (err instanceof AdminError) notFound(); // nobody else learns the page exists
    else throw err;
  }
  return (
    <div className="section-page">
      <div className="page-kicker"><span className="eyebrow">SUPER ADMIN</span><StateChip>Accounts</StateChip></div>
      <header className="page-heading">
        <div>
          <h1>Accounts</h1>
          <p>Create sign-in accounts, give each a workspace and role, and disable or remove them.</p>
        </div>
      </header>
      <div className="data-note">
        <span aria-hidden="true">●</span>
        <span>
          <strong>Stored in Supabase Auth</strong> · Accounts live in the project&rsquo;s database (auth.users). Workspace and role sit in each account&rsquo;s app metadata, which only this server can write; people cannot change their own. The super admin account is set outside the app and cannot be edited here.
        </span>
      </div>
      {needsTwoStep ? <AdminTwoStepGate /> : <AdminPortal />}
    </div>
  );
}
