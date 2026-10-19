import { StateChip } from "@fiona/ui";
import { MandatesPanel } from "@/components/mandates-panel";
import { routes } from "@/lib/routes";
import { getWorkspaceSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function MandatesPage() {
  const session = await getWorkspaceSession();
  const owner = session?.role === "owner";
  return (
    <div className="section-page">
      <div className="page-kicker"><StateChip>Permission tiers</StateChip></div>
      <header className="page-heading"><div><h1>{routes.mandates.label}</h1><p>{routes.mandates.description}</p></div></header>
      <div className="data-note">
        <span aria-hidden="true">●</span>
        <span>
          <strong>Enforced, not just shown</strong> · The Guardian checks every proposal against these mandates and the wallet re-checks them before paying. A level can never go above its ceiling, no agent can raise its own, and every change is a new version in the audit trail.
        </span>
      </div>
      <MandatesPanel canEdit={owner} />
      <p className="footnote">{owner ? "Only the owner can change a level." : "Only the owner can change a level; you are signed in with a different role."}</p>
    </div>
  );
}
