import Link from "next/link";
import { Card, EmptyState } from "@fiona/ui";

export default function NotFound() {
  return <div className="section-page"><span className="eyebrow">PAGE NOT FOUND</span><h1 className="not-found-title">This page isn’t in your workspace</h1><Card className="route-placeholder"><EmptyState title="No matching page">Check the address, or return to your business briefing.</EmptyState></Card><Link className="button button-primary" href="/">Back to briefing</Link></div>;
}
