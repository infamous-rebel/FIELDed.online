export default function PublicFooter() {
  return (
    <footer className="border-t border-[var(--border-subtle)] glass-subtle">
      <div className="mx-auto max-w-[1400px] px-6 py-8">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 mb-6">
          {/* Product */}
          <div>
            <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Product
            </h4>
            <ul className="space-y-2">
              {[
                { href: "/search", label: "Search" },
                { href: "/network", label: "Network" },
                { href: "/#how", label: "How It Works" },
                { href: "/#brain", label: "Business Brain" },
              ].map((link) => (
                <li key={link.label}>
                  <a
                    href={link.href}
                    className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          {/* Platform */}
          <div>
            <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Platform
            </h4>
            <ul className="space-y-2">
              {[
                { href: "/industries", label: "Industries" },
                { href: "/#network", label: "Two-Sided Network" },
                { href: "/#industries", label: "Trust & Security" },
              ].map((link) => (
                <li key={link.label}>
                  <a
                    href={link.href}
                    className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          {/* Company */}
          <div>
            <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Company
            </h4>
            <ul className="space-y-2">
              <li>
                <a
                  href="mailto:hello@fielded.online"
                  className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  Contact
                </a>
              </li>
            </ul>
          </div>
          {/* Account */}
          <div>
            <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
              Account
            </h4>
            <ul className="space-y-2">
              {[
                { href: "/login", label: "Sign In" },
                { href: "/signup", label: "Sign Up" },
              ].map((link) => (
                <li key={link.label}>
                  <a
                    href={link.href}
                    className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
        {/* Bottom bar */}
        <div className="border-t border-[var(--border-subtle)] pt-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center rounded bg-[var(--accent)] text-[8px] font-bold text-white">
              F
            </div>
            <span className="text-[11px] text-[var(--text-muted)]">
              &copy; 2026 FIELDed Platform
            </span>
          </div>
          <div className="flex items-center gap-4">
            <a
              href="/legal/privacy"
              className="text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              Privacy
            </a>
            <a
              href="/legal/terms"
              className="text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              Terms
            </a>
            <a
              href="/legal/business-terms"
              className="text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              Business Terms
            </a>
            <a
              href="/legal/ai-disclosure"
              className="text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              AI Disclosure
            </a>
            <a
              href="mailto:hello@fielded.online"
              className="text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              hello@fielded.online
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
