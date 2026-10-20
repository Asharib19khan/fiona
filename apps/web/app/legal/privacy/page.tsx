import type { Metadata } from "next";
import Link from "next/link";
import { LEGAL_CONTACT, LEGAL_OPERATOR } from "@/lib/legal";
import { LegalDoc, type LegalSection } from "../legal-doc";

export const metadata: Metadata = { title: "Privacy Policy · Fiona" };

const mail = <a href={`mailto:${LEGAL_CONTACT}`}>{LEGAL_CONTACT}</a>;

const sections: LegalSection[] = [
  {
    id: "who",
    heading: "Who we are",
    body: (
      <>
        <p>Fiona is operated by {LEGAL_OPERATOR}. For account and security data we decide how it is used (we are the &ldquo;controller&rdquo;). For the business documents and records a workspace puts into Fiona, the workspace owner decides, and we process that data on their behalf (we are a &ldquo;processor&rdquo;).</p>
        <p>Contact for anything in this policy, including requests about your data: {mail}.</p>
      </>
    ),
  },
  {
    id: "collect",
    heading: "What we collect",
    body: (
      <div className="legal-table-wrap">
        <table className="legal-table">
          <thead><tr><th>Data</th><th>Examples</th><th>Where it comes from</th></tr></thead>
          <tbody>
            <tr><td>Account</td><td>Name, work email, workspace, role, password (stored only as a hash by Supabase)</td><td>Your workspace administrator</td></tr>
            <tr><td>Security</td><td>Two-step verification factor, sign-in times, IP address, browser type, session tokens</td><td>Generated when you sign in</td></tr>
            <tr><td>Consent record</td><td>Which version of these documents you accepted, and when</td><td>The sign-in checkbox</td></tr>
            <tr><td>Business data</td><td>Bills, ledger entries, bank lines, inventory, forecasts, decisions and the names on them</td><td>Uploaded or imported by your workspace</td></tr>
            <tr><td>Activity and audit</td><td>Who proposed, checked, approved or rejected what, and when</td><td>Your use of Fiona</td></tr>
            <tr><td>AI connection</td><td>An Anthropic API key or Claude subscription token, if the owner adds one</td><td>The workspace owner</td></tr>
          </tbody>
        </table>
      </div>
    ),
  },
  {
    id: "use",
    heading: "Why we use it, and our legal basis",
    body: (
      <ul>
        <li><strong>To provide Fiona</strong> (sign-in, running the agents, the Guardian, approvals and the ledger): necessary to perform our agreement with you.</li>
        <li><strong>To keep Fiona secure</strong> (two-step verification, abuse prevention, the tamper-evident audit log): our legitimate interest in protecting users and data.</li>
        <li><strong>To record your acceptance</strong> of our terms: our legitimate interest in showing what was agreed, and legal obligations.</li>
        <li><strong>To meet legal obligations</strong>, such as lawful requests from authorities.</li>
      </ul>
    ),
  },
  {
    id: "ai",
    heading: "How the AI uses your data",
    body: (
      <>
        <p>When an agent or the Guardian works on a task, the relevant business data (for example a bill&rsquo;s text and the ledger figures it needs) is sent to Anthropic&rsquo;s Claude models to produce a result. Calculations are done by Fiona&rsquo;s own engine, not by the AI.</p>
        <ul>
          <li>We do not use your data to train AI models. Anthropic&rsquo;s commercial terms state that it does not train its models on inputs and outputs from its commercial services by default; see Anthropic&rsquo;s own privacy documentation for its handling and retention.</li>
          <li>Documents are treated as data, never as instructions: hidden instructions inside a document are reported, not followed.</li>
          <li>Fiona&rsquo;s AI does not make legally binding or similarly significant decisions about you on its own. A person approves every payment.</li>
        </ul>
      </>
    ),
  },
  {
    id: "sharing",
    heading: "Who we share it with",
    body: (
      <>
        <p>We do not sell personal data or share it for advertising. We share it only with these service providers, under their data processing terms, and only as needed to run Fiona:</p>
        <div className="legal-table-wrap">
          <table className="legal-table">
            <thead><tr><th>Provider</th><th>Purpose</th><th>Location</th></tr></thead>
            <tbody>
              <tr><td>Supabase, Inc.</td><td>Sign-in, accounts and two-step verification</td><td>Singapore (AWS ap-southeast-1)</td></tr>
              <tr><td>Anthropic, PBC</td><td>The Claude models behind the agents and the Guardian</td><td>United States</td></tr>
            </tbody>
          </table>
        </div>
        <p>The ledger, documents, audit log and sealed AI credentials are stored in a database on the server that runs Fiona. We may also disclose data where the law requires it, or to protect the rights and safety of users and others.</p>
      </>
    ),
  },
  {
    id: "transfers",
    heading: "International transfers",
    body: <p>Because our providers are in Singapore and the United States, your data may be processed outside your country, including outside Pakistan, the European Economic Area and mainland China. We rely on our providers&rsquo; contractual safeguards (such as standard contractual clauses where they apply) and send only the data a task needs. If you are in a country whose law requires separate consent for such transfers, please contact us before uploading personal data, and use synthetic data in the meantime.</p>,
  },
  {
    id: "retention",
    heading: "How long we keep it",
    body: (
      <ul>
        <li><strong>Account and security data:</strong> while the account exists, then deleted within 30 days of a deletion request, except where we must keep it by law.</li>
        <li><strong>Business data:</strong> for as long as the workspace exists, or until the owner deletes it.</li>
        <li><strong>Audit log:</strong> kept for the life of the workspace. Each entry is chained to the one before it so that tampering can be detected, which means entries are not edited or removed individually. When a workspace is deleted, its audit log is deleted with it.</li>
        <li><strong>Consent records:</strong> while the account exists, so we can show what was agreed.</li>
        <li>When the competition prototype is retired, we will delete the data it holds.</li>
      </ul>
    ),
  },
  {
    id: "security",
    heading: "How we protect it",
    body: (
      <ul>
        <li>Each workspace is isolated in the database by row-level security, so one workspace cannot read another&rsquo;s records.</li>
        <li>Administrator accounts must use two-step verification. Passwords are stored only as hashes.</li>
        <li>AI credentials are sealed with AES-256-GCM encryption and are never shown back in full.</li>
        <li>Internal services authenticate each other with short-lived signed tokens, and every action is written to a hash-chained audit log.</li>
      </ul>
    ),
  },
  {
    id: "rights",
    heading: "Your rights",
    body: (
      <>
        <p>Depending on where you live, you may have the right to: access your data; correct it; delete it; receive a copy in a portable format; object to or restrict processing; withdraw consent at any time (without affecting earlier processing); and not be subject to decisions made solely by automated means. Email {mail} to use any of these rights. We will answer within 30 days and may need to confirm your identity first.</p>
        <p>For business data, we will pass your request to the workspace owner who controls it and help them respond.</p>
        <p>You may also complain to your local data protection authority (for example, your national supervisory authority in the EU or UK, or the Cyberspace Administration of China). Pakistan has no data protection authority yet; we follow the principles of the draft Personal Data Protection Bill and the Prevention of Electronic Crimes Act, 2016.</p>
      </>
    ),
  },
  {
    id: "cookies",
    heading: "Cookies",
    body: <p>Fiona uses only the cookies and browser storage needed to keep you signed in and remember display preferences. No analytics, advertising or tracking cookies. See <Link href="/legal/cookies">Cookies &amp; Storage</Link>.</p>,
  },
  {
    id: "children",
    heading: "Children",
    body: <p>Fiona is a business tool for people aged 18 and over. We do not knowingly collect data about children. If you believe a child has an account, contact us and we will delete it.</p>,
  },
  {
    id: "changes",
    heading: "Changes to this policy",
    body: <p>When we change this policy materially, we will update the version and date at the top and ask you to accept it again at sign-in.</p>,
  },
];

export default function PrivacyPage() {
  return (
    <LegalDoc
      title="Privacy Policy"
      summary={
        <ul>
          <li>We collect what sign-in, security and your workspace&rsquo;s work need, and nothing for advertising.</li>
          <li>Your business data is sent to Anthropic&rsquo;s Claude only to do the task you asked for. It is never sold or used to train AI.</li>
          <li>Sign-in runs on Supabase (Singapore); the AI runs on Anthropic (United States).</li>
          <li>You can ask to see, correct, export or delete your data at any time.</li>
        </ul>
      }
      sections={sections}
    />
  );
}
