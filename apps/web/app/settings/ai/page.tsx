import { DegradedBanner, StateChip } from "@fiona/ui";
import { AiConnectionPanel } from "@/components/ai-connection-panel";
import { routes } from "@/lib/routes";
import { getWorkspaceSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function AiConnectionPage() {
  const session = await getWorkspaceSession();
  const page = routes["ai-connection"];
  return (
    <div className="section-page">
      <div className="page-kicker"><StateChip>Your own Claude account</StateChip></div>
      <header className="page-heading"><div><h1>{page.label}</h1><p>{page.description}</p></div></header>
      {session ? <AiConnectionPanel canEdit={session.role === "owner"} /> : <DegradedBanner>Sign in to a workspace to see its AI connection.</DegradedBanner>}
    </div>
  );
}
