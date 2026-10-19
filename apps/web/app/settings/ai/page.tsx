import { DegradedBanner, StateChip } from "@fiona/ui";
import { AiConnectionPanel } from "@/components/ai-connection-panel";
import { getWorkspaceSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function AiConnectionPage() {
  const session = await getWorkspaceSession();
  return (
    <div className="section-page">
      <div className="page-kicker"><StateChip>Your own Claude account</StateChip></div>
      <header className="page-heading"><div><h1>AI connection</h1><p>Choose which Claude account runs this workspace&apos;s agents and Guardian.</p></div></header>
      {session ? <AiConnectionPanel canEdit={session.role === "owner"} /> : <DegradedBanner>Sign in to a workspace to see its AI connection.</DegradedBanner>}
    </div>
  );
}
