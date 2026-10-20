import type { Metadata } from "next";
import { LEGAL_CONTACT } from "@/lib/legal";
import { LegalDoc, type LegalSection } from "../legal-doc";

export const metadata: Metadata = { title: "Acceptable Use · Fiona" };

const sections: LegalSection[] = [
  {
    id: "do-not",
    heading: "Do not",
    body: (
      <ul>
        <li>Use Fiona for anything unlawful, including fraud, money laundering, terrorist financing or evading sanctions or tax.</li>
        <li>Upload data you have no right to share, or real bank, card or identity data of other people.</li>
        <li>Try to access another workspace, another person&rsquo;s account, or data you have not been given.</li>
        <li>Disrupt or overload Fiona, or bypass its security, the Guardian, mandates, spending caps or approval steps on a copy you do not control.</li>
        <li>Use Fiona&rsquo;s agents to create harmful, deceptive or infringing content, or break Anthropic&rsquo;s usage policies.</li>
        <li>Present Fiona&rsquo;s outputs to others as professional financial, tax or legal advice.</li>
        <li>Resell, rebrand or offer Fiona as a service without our written permission.</li>
      </ul>
    ),
  },
  {
    id: "testing",
    heading: "Security testing and evaluation",
    body: (
      <>
        <p>Judges, reviewers and researchers are welcome to inspect Fiona in depth, including its source code, and to test its defences (for example with the injection bills in the demo set) on a copy they run themselves.</p>
        <p>Please do not test against other people&rsquo;s accounts or our shared sign-in service beyond normal use, and do not access, change or delete data that isn&rsquo;t yours. If you find a vulnerability, report it privately to <a href={`mailto:${LEGAL_CONTACT}`}>{LEGAL_CONTACT}</a> and give us reasonable time to fix it before sharing it. We will not take action against good-faith research that follows these rules.</p>
      </>
    ),
  },
  {
    id: "enforcement",
    heading: "What happens if this policy is broken",
    body: <p>We may remove content, suspend or end access, and, where the law requires, report activity to the authorities.</p>,
  },
];

export default function AcceptableUsePage() {
  return (
    <LegalDoc
      title="Acceptable Use Policy"
      summary={<ul><li>Use Fiona lawfully, only with data you&rsquo;re allowed to share, and only on your own workspace.</li><li>Inspecting and testing Fiona on your own copy is welcome; report security problems privately.</li></ul>}
      sections={sections}
    />
  );
}
