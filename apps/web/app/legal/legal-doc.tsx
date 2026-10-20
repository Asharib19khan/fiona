import type { ReactNode } from "react";
import { LEGAL_CONTACT, LEGAL_EFFECTIVE, LEGAL_VERSION } from "@/lib/legal";

export interface LegalSection {
  id: string;
  heading: string;
  body: ReactNode;
}

/** A legal document: title, plain-language summary, contents list and numbered sections. */
export function LegalDoc({ title, summary, sections }: { title: string; summary: ReactNode; sections: LegalSection[] }) {
  return (
    <article className="legal-doc">
      <p className="legal-kicker">Version {LEGAL_VERSION} · Effective {LEGAL_EFFECTIVE}</p>
      <h1 className="legal-title">{title}</h1>
      <div className="legal-summary">
        <strong>In short</strong>
        {summary}
      </div>

      <nav className="legal-toc" aria-label="Contents">
        <p className="legal-toc-label">Contents</p>
        <ol>
          {sections.map((section) => (
            <li key={section.id}><a href={`#${section.id}`}>{section.heading}</a></li>
          ))}
        </ol>
      </nav>

      {sections.map((section, index) => (
        <section key={section.id} id={section.id} className="legal-section" aria-labelledby={`${section.id}-h`}>
          <h2 id={`${section.id}-h`}><span className="legal-num">{index + 1}.</span> {section.heading}</h2>
          {section.body}
        </section>
      ))}

      <footer className="legal-foot">
        Questions about this document? Email <a href={`mailto:${LEGAL_CONTACT}`}>{LEGAL_CONTACT}</a>.
      </footer>
    </article>
  );
}
