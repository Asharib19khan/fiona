import { DegradedBanner } from "@fiona/ui";
import { PageHeader, rise } from "@/components/screen-kit";
import { AiConnectionPanel } from "@/components/ai-connection-panel";
import { getWorkspaceSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function AiConnectionPage() {
  const session = await getWorkspaceSession();
  return (
    <div className="section-page sk-page">
      <PageHeader title="AI connection" description="Choose which Claude account runs this workspace's agents and Guardian." chips={["Your own Claude account", "Sealed per workspace"]} />
      {session ? <div className="sk-rise" style={rise(1)}><AiConnectionPanel canEdit={session.role === "owner"} /></div> : <DegradedBanner>Sign in to a workspace to see its AI connection.</DegradedBanner>}
    </div>
  );
}
