import { PageHeader, rise } from "@/components/screen-kit";
import { MandatesPanel } from "@/components/mandates-panel";
import { routes } from "@/lib/routes";
import { getWorkspaceSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function MandatesPage() {
  const session = await getWorkspaceSession();
  const owner = session?.role === "owner";
  return (
    <div className="section-page sk-page">
      <PageHeader title={routes.mandates.label} description={routes.mandates.description} chips={["Permission tiers", owner ? "Owner" : "Read only"]} />
      <div className="data-note sk-rise" style={rise(1)}>
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
