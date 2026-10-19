import { redirect } from "next/navigation";
import { ResetPasswordPage } from "@/components/reset-password-page";
import { getAuthStage } from "@/lib/session";
import { authConfigured } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/** Reached from the reset email: the link signed the person in, so they can set a new password. */
export default async function ResetPassword() {
  if (!authConfigured()) redirect("/");
  const stage = await getAuthStage();
  if (stage === "signed_out") redirect("/login");
  if (stage === "mfa_required") redirect("/login?next=/reset-password");
  return <ResetPasswordPage />;
}
