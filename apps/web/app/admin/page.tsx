import { notFound, redirect } from "next/navigation";
import { PageHeader, rise } from "@/components/screen-kit";
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
    <div className="section-page sk-page">
      <PageHeader title="Accounts" description="Create sign-in accounts, give each a workspace and role, and disable or remove them." chips={["Super admin", "Two-step required"]} />
      <div className="data-note sk-rise" style={rise(1)}>
        <span aria-hidden="true">●</span>
        <span>
          <strong>Stored in Supabase Auth</strong> · Accounts live in the project&rsquo;s database (auth.users). Workspace and role sit in each account&rsquo;s app metadata, which only this server can write; people cannot change their own. The super admin account is set outside the app and cannot be edited here.
        </span>
      </div>
      <div className="sk-rise" style={rise(2)}>{needsTwoStep ? <AdminTwoStepGate /> : <AdminPortal />}</div>
    </div>
  );
}
