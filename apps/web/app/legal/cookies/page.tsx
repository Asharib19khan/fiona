import type { Metadata } from "next";
import { LegalDoc, type LegalSection } from "../legal-doc";

export const metadata: Metadata = { title: "Cookies & Storage · Fiona" };

const sections: LegalSection[] = [
  {
    id: "what",
    heading: "What Fiona stores in your browser",
    body: (
      <div className="legal-table-wrap">
        <table className="legal-table">
          <thead><tr><th>Name</th><th>Type</th><th>Purpose</th><th>Lasts</th></tr></thead>
          <tbody>
            <tr><td><code>sb-…-auth-token</code></td><td>Cookie, strictly necessary</td><td>Keeps you signed in securely (Supabase session)</td><td>Until you sign out or the session expires</td></tr>
            <tr><td>Display preferences</td><td>Local storage</td><td>Remembers layout choices, such as collapsed panels and the agent folder</td><td>Until you clear site data</td></tr>
            <tr><td><code>fiona:intro-seen</code></td><td>Session storage</td><td>Plays the opening animation only once per visit</td><td>Until you close the tab</td></tr>
          </tbody>
        </table>
      </div>
    ),
  },
  {
    id: "none",
    heading: "What Fiona does not use",
    body: <p>No analytics, advertising, social media or cross-site tracking cookies, and no third-party scripts. Fonts are served from Fiona itself, so your browser does not contact Google or any other font service.</p>,
  },
  {
    id: "consent",
    heading: "Why there is no cookie banner",
    body: <p>Cookies that are strictly necessary for a service you asked for do not need consent under the EU and UK ePrivacy rules. Fiona uses no other kind. If that ever changes, we will ask first.</p>,
  },
  {
    id: "control",
    heading: "Your control",
    body: <p>You can delete Fiona&rsquo;s cookies and storage in your browser settings at any time. Doing so signs you out.</p>,
  },
];

export default function CookiesPage() {
  return <LegalDoc title="Cookies & Storage" summary={<ul><li>Only the sign-in cookie and a few display preferences. No tracking, no ads, no third-party scripts.</li></ul>} sections={sections} />;
}
