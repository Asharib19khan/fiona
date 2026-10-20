import type { Metadata } from "next";
import Link from "next/link";
import { LEGAL_CONTACT, LEGAL_OPERATOR } from "@/lib/legal";
import { LegalDoc, type LegalSection } from "../legal-doc";

export const metadata: Metadata = { title: "Terms of Service · Fiona" };

const sections: LegalSection[] = [
  {
    id: "agreement",
    heading: "The agreement",
    body: (
      <>
        <p>These Terms of Service (the &ldquo;Terms&rdquo;) are an agreement between you and {LEGAL_OPERATOR} (&ldquo;we&rdquo;, &ldquo;us&rdquo;). They apply to the Fiona web console, its companion app, its services and its documentation (together, &ldquo;Fiona&rdquo;).</p>
        <p>You accept these Terms by ticking the box on the sign-in page, or by using Fiona. If you use Fiona for a business, you confirm you are authorised to accept them for that business, and &ldquo;you&rdquo; includes it. If you do not agree, do not use Fiona.</p>
        <p>These Terms include the <Link href="/legal/privacy">Privacy Policy</Link>, the <Link href="/legal/ai-notice">AI &amp; Financial Notice</Link>, the <Link href="/legal/acceptable-use">Acceptable Use Policy</Link> and the <Link href="/legal/cookies">Cookies &amp; Storage notice</Link>.</p>
      </>
    ),
  },
  {
    id: "prototype",
    heading: "What Fiona is, and its current status",
    body: (
      <>
        <p>Fiona is a <strong>prototype</strong> built for the FinTechathon 2026 competition. It gives a small business a team of AI agents that read bills, plan payments, forecast cash and compare financing over one ledger, with an independent check (the Guardian) and the owner&rsquo;s approval before anything is paid.</p>
        <ul>
          <li>The demonstration business and its records are <strong>synthetic</strong>. They describe no real company or person.</li>
          <li>The wallet is a <strong>sandbox</strong>. It is not connected to any bank or payment network, and <strong>no real money moves</strong>.</li>
          <li>Fiona is offered for evaluation and demonstration. It is not offered for sale and is not a production service.</li>
        </ul>
      </>
    ),
  },
  {
    id: "not-advice",
    heading: "Not a bank, and not advice",
    body: (
      <>
        <p>We are not a bank, payment service provider, investment adviser, accountant, auditor, tax adviser or law firm, and we hold no licence from the State Bank of Pakistan, the Securities and Exchange Commission of Pakistan or any other regulator. Nothing in Fiona is financial, investment, accounting, tax or legal advice.</p>
        <p>Fiona&rsquo;s outputs, including forecasts, rankings, proposals and agent opinions, are information to support your own decisions. You are responsible for every decision you make and every approval you give. Read the <Link href="/legal/ai-notice">AI &amp; Financial Notice</Link> before relying on any output.</p>
      </>
    ),
  },
  {
    id: "accounts",
    heading: "Accounts and security",
    body: (
      <>
        <p>Accounts are created by a workspace administrator; there is no public sign-up. You must be at least 18 years old.</p>
        <ul>
          <li>Keep your password and authenticator private, and do not share your account. Administrator accounts must use two-step verification.</li>
          <li>You are responsible for activity under your account. Tell us straight away at <a href={`mailto:${LEGAL_CONTACT}`}>{LEGAL_CONTACT}</a> if you suspect someone else has used it.</li>
          <li>Workspace owners decide who may access their workspace and with what role, and are responsible for those choices.</li>
        </ul>
      </>
    ),
  },
  {
    id: "your-data",
    heading: "Your data",
    body: (
      <>
        <p>You keep all rights in the documents and data you put into Fiona (&ldquo;Your Data&rdquo;). You give us permission to store and process Your Data only to run Fiona for you, keep it secure, and meet legal obligations. We do not sell Your Data and do not use it to train AI models.</p>
        <p>You confirm you have the right to upload Your Data. If it contains personal data about other people (for example suppliers&rsquo; or staff names on bills), you are responsible for having a lawful basis to share it, and we process it on your behalf as described in the <Link href="/legal/privacy">Privacy Policy</Link>.</p>
        <p>Please do not upload real customer, bank or card data to this prototype. Use synthetic or test data.</p>
      </>
    ),
  },
  {
    id: "ai-connection",
    heading: "AI connection and third-party services",
    body: (
      <>
        <p>Fiona&rsquo;s agents run on Anthropic&rsquo;s Claude models. A workspace owner chooses on the AI connection page whether Fiona uses the server&rsquo;s own Claude sign-in or the owner&rsquo;s Anthropic API key or Claude subscription token. When you connect your own credential, your use of it is also governed by Anthropic&rsquo;s terms, and any usage charges are between you and Anthropic.</p>
        <p>Sign-in is provided by Supabase. Third-party services are governed by their own terms, and we are not responsible for their availability or conduct.</p>
      </>
    ),
  },
  {
    id: "acceptable-use",
    heading: "Acceptable use",
    body: <p>You must follow the <Link href="/legal/acceptable-use">Acceptable Use Policy</Link>. We may suspend access that breaks it or puts Fiona, other users or third parties at risk.</p>,
  },
  {
    id: "ip",
    heading: "Intellectual property",
    body: (
      <>
        <p>Fiona&rsquo;s software, design, names and documentation belong to us. The source code is published for review and evaluation; publication does not grant a licence to use it commercially, copy it into another product, or offer it as a service. No rights are granted except those stated in these Terms.</p>
        <p>If you send us feedback, we may use it freely without obligation to you.</p>
      </>
    ),
  },
  {
    id: "availability",
    heading: "Availability and changes",
    body: <p>As a prototype, Fiona may change, be unavailable, lose data or stop at any time without notice. Keep your own copies of anything important. We may change features, and we may update these Terms; when a change is material we will update the version shown above and ask you to accept again at sign-in.</p>,
  },
  {
    id: "warranty",
    heading: "No warranty",
    body: <p>To the extent the law allows, Fiona is provided <strong>&ldquo;as is&rdquo; and &ldquo;as available&rdquo;</strong>, without warranties of any kind, express or implied, including fitness for a particular purpose, accuracy, non-infringement and uninterrupted or error-free operation.</p>,
  },
  {
    id: "liability",
    heading: "Limitation of liability",
    body: (
      <>
        <p>To the extent the law allows, we are not liable for indirect, incidental, special or consequential losses, or for lost profits, revenue, data or goodwill, arising from Fiona or its outputs. Our total liability for any claim relating to Fiona is limited to the amount you paid us for it in the twelve months before the claim, which for this free prototype is zero.</p>
        <p>Nothing in these Terms limits liability that cannot be limited by law, such as liability for fraud, or for death or personal injury caused by negligence, or your rights under consumer protection law that cannot be waived.</p>
      </>
    ),
  },
  {
    id: "termination",
    heading: "Suspension and ending",
    body: <p>You may stop using Fiona at any time and ask us to delete your account. We may suspend or end access if you break these Terms, if required by law, or when the prototype is retired. Sections on your data, intellectual property, no warranty, limitation of liability and governing law continue after access ends.</p>,
  },
  {
    id: "law",
    heading: "Governing law and disputes",
    body: <p>These Terms are governed by the laws of Pakistan. We will first try to settle any dispute informally; please contact us. Otherwise, the courts at Karachi have jurisdiction, except where mandatory consumer law gives you the right to bring a claim where you live.</p>,
  },
  {
    id: "general",
    heading: "General",
    body: <p>If any part of these Terms is unenforceable, the rest still applies. Our not enforcing a right is not a waiver of it. You may not transfer your rights under these Terms without our consent. These Terms are the whole agreement between you and us about Fiona.</p>,
  },
];

export default function TermsPage() {
  return (
    <LegalDoc
      title="Terms of Service"
      summary={
        <ul>
          <li>Fiona is a competition prototype. Its data is synthetic and its wallet is a sandbox: no real money moves.</li>
          <li>It is not a bank and gives no financial, tax or legal advice. You make and own every decision.</li>
          <li>Your data stays yours. We don&rsquo;t sell it or train AI on it.</li>
          <li>Provided as is, with liability limited as far as the law allows. Pakistani law applies.</li>
        </ul>
      }
      sections={sections}
    />
  );
}
