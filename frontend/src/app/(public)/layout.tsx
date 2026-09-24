import type { Metadata } from "next";

export const metadata: Metadata = {
  title: {
    default: "FIELDed — Find Services, Connect with Businesses",
    template: "%s — FIELDed",
  },
  description:
    "Describe what you need in plain language. FIELDed matches you with qualified businesses instantly.",
};

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <nav className="mx-auto max-w-7xl px-4 py-4 flex items-center justify-between">
          <a href="/" className="text-xl font-bold text-[var(--text-primary)]">
            FIELDed
          </a>
          <div className="flex gap-4">
            <a
              href="/search"
              className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Search
            </a>
            <a
              href="/network"
              className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Network
            </a>
            <a
              href="/login"
              className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Sign In
            </a>
            <a
              href="/signup"
              className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-hover)] transition-colors"
            >
              Sign Up
            </a>
          </div>
        </nav>
      </header>
      {children}
    </div>
  );
}
