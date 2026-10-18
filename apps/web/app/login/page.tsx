import { redirect } from "next/navigation";
import { LoginPage } from "@/components/login-page";
import { getSession } from "@/lib/session";
import { authConfigured } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function Login({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  if (!authConfigured() || (await getSession())) redirect("/");
  const params = await searchParams;
  const next = Array.isArray(params.next) ? params.next[0] : params.next;
  return <LoginPage next={next ?? "/"} />;
}
