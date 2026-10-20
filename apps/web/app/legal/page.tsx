import type { Metadata } from "next";
import Link from "next/link";
import { LEGAL_CONTACT, LEGAL_DOCS, LEGAL_EFFECTIVE } from "@/lib/legal";

export const metadata: Metadata = { title: "Legal · Fiona" };

export default function LegalIndex() {
  return (
    <article className="legal-doc">
      <p className="legal-kicker">Effective {LEGAL_EFFECTIVE}</p>
      <h1 className="legal-title">Legal and privacy</h1>
      <p className="legal-lead">Fiona is a competition prototype running on synthetic data with a sandbox wallet. These documents explain the rules, how your data is handled and what the AI can and cannot do.</p>
      <ul className="legal-index">
        {LEGAL_DOCS.map((doc) => (
          <li key={doc.href}>
            <Link href={doc.href}>
              <strong>{doc.title}</strong>
              <span>{doc.blurb}</span>
            </Link>
          </li>
        ))}
      </ul>
      <footer className="legal-foot">Contact: <a href={`mailto:${LEGAL_CONTACT}`}>{LEGAL_CONTACT}</a></footer>
    </article>
  );
}
