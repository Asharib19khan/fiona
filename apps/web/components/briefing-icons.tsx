import type { ReactNode, SVGProps } from "react";

/** Line icons for the briefing, drawn inline so the page needs no icon package. */
function Icon({ children, ...props }: SVGProps<SVGSVGElement> & { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      {children}
    </svg>
  );
}

export const TrendDownIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M22 17l-8.5-8.5-5 5L2 7" /><path d="M16 17h6v-6" /></Icon>
);
export const TrendUpIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M22 7l-8.5 8.5-5-5L2 17" /><path d="M16 7h6v6" /></Icon>
);
export const ShieldCheckIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="M9 12l2 2 4-4" /></Icon>
);
export const BoxIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M21 8l-9-5-9 5 9 5 9-5z" /><path d="M3 8v8l9 5 9-5V8" /><path d="M12 13v8" /></Icon>
);
export const ArrowRightIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon width="14" height="14" {...p}><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></Icon>
);
export const InfoIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon width="14" height="14" {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" /></Icon>
);
export const CompassIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M15.5 8.5l-2 5-5 2 2-5 5-2z" /></Icon>
);
export const ChatIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M21 12a8 8 0 0 1-11.8 7L4 20l1.1-4.6A8 8 0 1 1 21 12z" /></Icon>
);
export const LayersIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M12 3l9 5-9 5-9-5 9-5z" /><path d="M3 13l9 5 9-5" /></Icon>
);
export const ClockIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>
);
export const LinkIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></Icon>
);
export const DocIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" /><path d="M14 3v5h5" /><path d="M9 13h6" /><path d="M9 17h4" /></Icon>
);
export const ScaleIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M12 3v18" /><path d="M5 7h14" /><path d="M5 7l-3 7a3 3 0 0 0 6 0z" /><path d="M19 7l-3 7a3 3 0 0 0 6 0z" /><path d="M8 21h8" /></Icon>
);
export const GaugeIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M4 18a8 8 0 1 1 16 0" /><path d="M12 18l4-6" /></Icon>
);
export const AlertIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M12 3l9.5 17h-19z" /><path d="M12 10v4" /><path d="M12 17h.01" /></Icon>
);
export const WalletIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><rect x="3" y="6" width="18" height="14" rx="2" /><path d="M3 10h18" /><path d="M16 15h2" /><path d="M6 6l9-3 1 3" /></Icon>
);
export const CheckCircleIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M8 12l3 3 5-6" /></Icon>
);
export const CoinsIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><ellipse cx="9" cy="7" rx="6" ry="3" /><path d="M3 7v5c0 1.7 2.7 3 6 3s6-1.3 6-3V7" /><path d="M9 15v2c0 1.7 2.7 3 6 3s6-1.3 6-3v-5c0-1.7-2.7-3-6-3" /></Icon>
);
export const CalendarIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18" /><path d="M8 3v4" /><path d="M16 3v4" /></Icon>
);
export const HashIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M5 9h15" /><path d="M4 15h15" /><path d="M10 3L8 21" /><path d="M16 3l-2 18" /></Icon>
);
export const UploadIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M12 16V4" /><path d="M7 9l5-5 5 5" /><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></Icon>
);
export const SparkIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M12 3v4" /><path d="M12 17v4" /><path d="M3 12h4" /><path d="M17 12h4" /><path d="M6 6l2.5 2.5" /><path d="M15.5 15.5L18 18" /><path d="M18 6l-2.5 2.5" /><path d="M8.5 15.5L6 18" /></Icon>
);
export const UsersIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7" /><path d="M18 14a6.5 6.5 0 0 1 3.5 6" /></Icon>
);
export const KeyIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><circle cx="8" cy="15" r="4" /><path d="M11 12l9-9" /><path d="M17 6l3 3" /><path d="M15 8l2 2" /></Icon>
);
export const ChevronDownIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon width="14" height="14" {...p}><path d="M6 9l6 6 6-6" /></Icon>
);
export const XCircleIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M15 9l-6 6" /><path d="M9 9l6 6" /></Icon>
);
export const UndoIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M9 14L4 9l5-5" /><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" /></Icon>
);
export const InboxIcon = (p: SVGProps<SVGSVGElement>) => (
  <Icon {...p}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z" /></Icon>
);
