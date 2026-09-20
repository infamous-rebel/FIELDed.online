"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { businesses, enquiries } from "@/lib/api-client";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/business/dashboard" },
  { label: "Enquiries", href: "/business/enquiries", badge: true },
  { label: "Quotes", href: "/business/quotes" },
  { label: "Bookings", href: "/business/bookings" },
  { label: "Operations", href: "/business/operations" },
  { label: "Services", href: "/business/services" },
  { label: "Business Brain", href: "/business/brain" },
  { label: "Communications", href: "/business/communications" },
  { label: "Payments", href: "/business/payments" },
  { label: "Settings", href: "/business/settings" },
];

export default function BusinessLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [enquiryCount, setEnquiryCount] = useState(0);

  useEffect(() => {
    async function fetchCount() {
      try {
        const bizList = await businesses.list();
        if (bizList.length > 0) {
          const enqList = await enquiries.listForBusiness(bizList[0].id);
          setEnquiryCount(enqList.length);
        }
      } catch {
        // Silently fail — badge stays at 0
      }
    }
    fetchCount();
  }, []);

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="hidden md:flex w-64 flex-shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="p-6">
          <a
            href="/"
            className="text-xl font-bold text-[var(--text-primary)]"
          >
            FIELDed
          </a>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Business Brain
          </p>
        </div>

        <nav className="flex-1 px-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/business/dashboard" &&
                pathname.startsWith(item.href));
            return (
              <a
                key={item.href}
                href={item.href}
                className={`flex items-center justify-between rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "border-l-2 border-[var(--accent)] bg-[var(--bg-elevated)] text-[var(--accent)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span>{item.label}</span>
                {item.badge && enquiryCount > 0 && (
                  <span className="inline-flex items-center justify-center rounded-full bg-[var(--accent)] px-2 py-0.5 text-xs font-medium text-white">
                    {enquiryCount}
                  </span>
                )}
              </a>
            );
          })}
        </nav>

        <div className="p-4 border-t border-[var(--border-subtle)]">
          <a
            href="/"
            className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
          >
            ← Back to FIELDed
          </a>
        </div>
      </aside>

      {/* Mobile header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-50 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="flex items-center justify-between px-4 py-3">
          <a
            href="/"
            className="text-lg font-bold text-[var(--text-primary)]"
          >
            FIELDed
          </a>
          <span className="text-xs text-[var(--text-muted)]">Business</span>
        </div>
        <nav className="flex overflow-x-auto px-3 pb-2 gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/business/dashboard" &&
                pathname.startsWith(item.href));
            return (
              <a
                key={item.href}
                href={item.href}
                className={`whitespace-nowrap rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-[var(--accent)] text-white"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
                }`}
              >
                {item.label}
              </a>
            );
          })}
        </nav>
      </div>

      {/* Main content */}
      <main className="flex-1 p-6 md:p-8 mt-[104px] md:mt-0 overflow-auto">
        {children}
      </main>
    </div>
  );
}
