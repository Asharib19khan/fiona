"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function LegalNav({ docs }: { docs: { href: string; title: string }[] }) {
  const pathname = usePathname();
  return (
    <nav className="legal-nav">
      {docs.map((doc) => (
        <Link key={doc.href} href={doc.href} className="legal-nav-item" aria-current={pathname === doc.href ? "page" : undefined}>
          {doc.title}
        </Link>
      ))}
    </nav>
  );
}
