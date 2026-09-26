import type { Metadata } from "next";

export const metadata: Metadata = {
  title: {
    default: "Legal — FIELDed",
    template: "%s — FIELDed",
  },
};

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <div className="mb-8">
        <a
          href="/"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
        >
          <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to FIELDed
        </a>
      </div>
      <article className="prose-fielded">{children}</article>
    </div>
  );
}
