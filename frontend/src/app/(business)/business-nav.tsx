"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { businesses, enquiries, auth, type UserResponse } from "@/lib/api-client";
import { isAuthenticated, logout } from "@/lib/auth";
import FloatingCoBrain from "@/components/business/floating-cobrainer";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/business/dashboard", icon: HomeIcon, badge: false },
  { label: "Enquiries", href: "/business/enquiries", icon: InboxIcon, badge: true },
  { label: "Bookings", href: "/business/bookings", icon: CalendarIcon, badge: false },
  { label: "Quotes", href: "/business/quotes", icon: DocumentIcon, badge: false },
  { label: "Services", href: "/business/services", icon: BriefcaseIcon, badge: false },
  { label: "Schedule", href: "/business/schedule", icon: CalendarDaysIcon, badge: false },
  { label: "Finance", href: "/business/finance", icon: FinanceIcon, badge: false },
  { label: "Payments", href: "/business/payments", icon: CreditCardIcon, badge: false },
  { label: "Business Brain", href: "/business/brain", icon: BrainIcon, badge: false },
  { label: "Communications", href: "/business/communications", icon: MessageIcon, badge: false },
  { label: "Call Agent", href: "/business/call-agent", icon: PhoneIcon, badge: false },
  { label: "Operations", href: "/business/operations", icon: OperationsIcon, badge: false },
  { label: "Profile", href: "/business/profile", icon: UserIcon, badge: false },
  { label: "Settings", href: "/business/settings", icon: SettingsIcon, badge: false },
];

export default function BusinessNav({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [enquiryCount, setEnquiryCount] = useState(0);
  const [user, setUser] = useState<UserResponse | null>(null);
  const [businessId, setBusinessId] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) return;

    async function fetchData() {
      try {
        const [userData, bizList] = await Promise.all([
          auth.me(),
          businesses.list(),
        ]);
        setUser(userData);
        if (bizList.length > 0) {
          setBusinessId(bizList[0].id);
          const enqList = await enquiries.listForBusiness(bizList[0].id);
          const activeCount = enqList.filter(
            (e) => !["cancelled", "expired", "declined", "completed"].includes(e.status)
          ).length;
          setEnquiryCount(activeCount);
        }
      } catch {
        // Stay at 0
      }
    }
    fetchData();
  }, []);

  async function handleLogout() {
    await logout();
    window.location.href = "/";
  }

  const displayName = user?.customer_profile?.first_name || user?.email || "Operator";
  const initials = displayName
    .split(/[\s@]+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() || "")
    .join("");

  return (
    <div className="min-h-screen flex">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-64 flex-shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        {/* Logo */}
        <div className="p-5 pb-4">
          <a href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent)] text-sm font-bold text-white">
              F
            </div>
            <div>
              <span className="text-base font-semibold text-[var(--text-primary)]">FIELDed</span>
              <span className="block text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Business</span>
            </div>
          </a>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/business/dashboard" &&
                pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <a
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
                }`}
              >
                <Icon active={isActive} />
                <span className="flex-1">{item.label}</span>
                {item.badge && enquiryCount > 0 && (
                  <span className="inline-flex items-center justify-center rounded-full bg-[var(--accent)] px-1.5 py-0.5 text-[10px] font-semibold text-white min-w-[20px]">
                    {enquiryCount}
                  </span>
                )}
              </a>
            );
          })}
        </nav>

        {/* User section */}
        <div className="p-3 border-t border-[var(--border-subtle)]">
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-[var(--bg-elevated)]"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--accent)]/15 text-xs font-semibold text-[var(--accent)]">
                {initials || "?"}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[var(--text-primary)] truncate">{displayName}</p>
                <p className="text-[10px] text-[var(--text-muted)]">Business Owner</p>
              </div>
              <svg className="h-4 w-4 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l4-4 4 4m0 6l-4 4-4-4" />
              </svg>
            </button>

            {userMenuOpen && (
              <div className="absolute bottom-full left-0 right-0 mb-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] py-1 shadow-lg z-50">
                <a
                  href="/customer/dashboard"
                  className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)]"
                  onClick={() => setUserMenuOpen(false)}
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                  </svg>
                  Switch to Customer
                </a>
                <a
                  href="/"
                  className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)]"
                  onClick={() => setUserMenuOpen(false)}
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                  </svg>
                  Back to FIELDed
                </a>
                <div className="my-1 border-t border-[var(--border-subtle)]" />
                <button
                  onClick={() => { setUserMenuOpen(false); handleLogout(); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[var(--danger)] hover:bg-[var(--bg-surface)]"
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                  Sign Out
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-50 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--accent)] text-xs font-bold text-white">
              F
            </div>
            <span className="text-sm font-semibold text-[var(--text-primary)]">FIELDed</span>
          </div>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="rounded-lg p-1.5 text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile menu dropdown */}
        {mobileMenuOpen && (
          <div className="border-t border-[var(--border-subtle)] px-3 py-2 max-h-[80vh] overflow-y-auto">
            {NAV_ITEMS.map((item) => {
              const isActive =
                pathname === item.href ||
                (item.href !== "/business/dashboard" &&
                  pathname.startsWith(item.href));
              const Icon = item.icon;
              return (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
                  }`}
                >
                  <Icon active={isActive} />
                  <span className="flex-1">{item.label}</span>
                  {item.badge && enquiryCount > 0 && (
                    <span className="inline-flex items-center justify-center rounded-full bg-[var(--accent)] px-1.5 py-0.5 text-[10px] font-semibold text-white">
                      {enquiryCount}
                    </span>
                  )}
                </a>
              );
            })}
            <div className="my-2 border-t border-[var(--border-subtle)]" />
            <a
              href="/customer/dashboard"
              onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
              Switch to Customer
            </a>
            <button
              onClick={() => { setMobileMenuOpen(false); handleLogout(); }}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--danger)] hover:bg-[var(--bg-elevated)]"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              Sign Out
            </button>
          </div>
        )}
      </div>

      {/* Main content */}
      <main className="flex-1 p-6 md:p-8 mt-[52px] md:mt-0 overflow-auto min-h-screen">
        {children}
      </main>

      {/* Floating Co-Brain */}
      {businessId && (
        <FloatingCoBrain
          businessId={businessId}
          context={{
            page: pathname.replace("/business/", "").replace("/", " ") || "dashboard",
          }}
        />
      )}
    </div>
  );
}

/* ── Nav Icons ─ */

function HomeIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
    </svg>
  );
}

function InboxIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
    </svg>
  );
}

function CalendarIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

function CalendarDaysIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 10h18M3 14h18" />
    </svg>
  );
}

function DocumentIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function BriefcaseIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function FinanceIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
    </svg>
  );
}

function CreditCardIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
    </svg>
  );
}

function BrainIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 2a8 8 0 0 0-8 8c0 3.4 2.1 6.3 5 7.5V20a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-2.5c2.9-1.2 5-4.1 5-7.5a8 8 0 0 0-8-8z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M10 22h4" />
    </svg>
  );
}

function MessageIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
    </svg>
  );
}

function PhoneIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
    </svg>
  );
}

function OperationsIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function UserIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  );
}

function SettingsIcon({ active }: { active: boolean }) {
  return (
    <svg className={`h-[18px] w-[18px] ${active ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}
