/**
 * One place for the legal documents' version and contact details. Bump LEGAL_VERSION when any
 * document changes materially: sign-in records which version each person accepted.
 */
export const LEGAL_VERSION = "2026-10-20";
export const LEGAL_EFFECTIVE = "20 October 2026";
export const LEGAL_CONTACT = "ashepic057@gmail.com";
export const LEGAL_OPERATOR = "the Fiona team (Asharib Khan, Abdullah, Daniyal and Yahya), Karachi, Pakistan";

export const LEGAL_DOCS = [
  { href: "/legal/terms", title: "Terms of Service", blurb: "The agreement for using Fiona: what it is, what it isn't, and who is responsible for what." },
  { href: "/legal/privacy", title: "Privacy Policy", blurb: "What personal data Fiona handles, why, who processes it, how long it is kept and your rights." },
  { href: "/legal/ai-notice", title: "AI & Financial Notice", blurb: "How the AI agents work, their limits, and why nothing here is financial, tax or legal advice." },
  { href: "/legal/acceptable-use", title: "Acceptable Use", blurb: "What you may and may not do with Fiona, including responsible security testing." },
  { href: "/legal/cookies", title: "Cookies & Storage", blurb: "The only cookies Fiona sets are the ones sign-in needs. No tracking, no ads." },
] as const;
