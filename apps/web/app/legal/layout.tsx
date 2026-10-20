import Link from "next/link";
import type { ReactNode } from "react";
import { LEGAL_DOCS, LEGAL_EFFECTIVE } from "@/lib/legal";
import { LegalNav } from "./legal-nav";
import "./legal.css";

export default function LegalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="legal">
      <header className="legal-top">
        <Link href="/legal" className="legal-brand">
          <span className="legal-wordmark">FIONA</span>
          <span className="legal-brand-sub">Legal</span>
        </Link>
        <Link href="/" className="legal-back">Back to Fiona</Link>
      </header>
      <div className="legal-body">
        <aside className="legal-side" aria-label="Legal documents">
          <LegalNav docs={LEGAL_DOCS.map(({ href, title }) => ({ href, title }))} />
          <p className="legal-side-note">Effective {LEGAL_EFFECTIVE}</p>
        </aside>
        <main className="legal-main">{children}</main>
      </div>
    </div>
  );
}
