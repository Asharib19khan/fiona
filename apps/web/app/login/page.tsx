import { redirect } from "next/navigation";
import { LoginPage } from "@/components/login-page";
import { safeNext } from "@/lib/safe-next";
import { getAuthStage } from "@/lib/session";
import { authConfigured } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

type Params = { next?: string | string[]; error?: string | string[] };

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

export default async function Login({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const next = safeNext(first(params.next));
  const stage = await getAuthStage();
  if (!authConfigured() || stage === "signed_in") redirect(next);
  const notice = first(params.error) === "link" ? "That link has expired or was already used. Ask for a new one below." : null;
  return <LoginPage next={next} initialMode={stage === "mfa_required" ? "mfa" : "signin"} notice={notice} />;
}
