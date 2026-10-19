"use client";

import { Card } from "@fiona/ui";
import { TwoFactorSettings } from "@/components/two-factor-settings";

/**
 * Shown to the super admin instead of the account tools until two-step verification is on.
 * Turning it on upgrades this session (aal2), so the page reloads straight into the tools.
 */
export function AdminTwoStepGate() {
  return (
    <Card className="tier-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">REQUIRED</span>
          <h2>Turn on two-step verification first</h2>
        </div>
      </div>
      <p className="admin-muted">
        Account administration always needs a code from your authenticator app, on top of your password. Set it up once here and the account tools open.
      </p>
      <TwoFactorSettings onEnabled={() => window.setTimeout(() => window.location.reload(), 900)} />
    </Card>
  );
}
