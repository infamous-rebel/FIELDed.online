"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";

export default function LandingPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const handleEnquirySubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    sessionStorage.setItem("fielded_query", query.trim());
    router.push("/search");
  };

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="mx-auto max-w-7xl px-4 py-24 sm:py-32 lg:py-40">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="text-4xl font-bold tracking-tight text-[var(--text-primary)] sm:text-5xl lg:text-6xl">
              Tell us what you need.{" "}
              <span className="text-[var(--accent)]">
                FIELDed finds where it can be done.
              </span>
            </h1>
            <p className="mt-6 text-lg text-[var(--text-secondary)] leading-relaxed">
              Describe your service need in plain language. FIELDed matches your
              intent to qualified businesses, governed by rules you control.
            </p>
            <form
              onSubmit={handleEnquirySubmit}
              className="mt-10 flex flex-col sm:flex-row gap-3 max-w-2xl mx-auto"
            >
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g., I need a licensed electrician for a home wiring upgrade in Melbourne..."
                rows={2}
                className="flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3 text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                aria-label="Describe your service need"
              />
              <button
                type="submit"
                className="rounded-lg bg-[var(--accent)] px-6 py-3 font-medium text-white hover:bg-[var(--accent-hover)] transition-colors self-end sm:self-auto whitespace-nowrap"
              >
                Start Enquiry
              </button>
            </form>
          </div>
        </div>
        {/* Background gradient */}
        <div
          className="absolute inset-0 -z-10 opacity-30"
          style={{
            background:
              "radial-gradient(ellipse at 50% 0%, var(--accent) 0%, transparent 60%)",
          }}
          aria-hidden="true"
        />
      </section>

      {/* What is FIELDed? */}
      <section className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="mx-auto max-w-7xl px-4 py-20">
          <h2 className="text-center text-3xl font-bold text-[var(--text-primary)]">
            What is FIELDed?
          </h2>
          <p className="mt-4 text-center text-[var(--text-secondary)] max-w-2xl mx-auto">
            A customer-to-business service network where intent meets capability
            through governed execution.
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                title: "Intelligent Matching",
                description:
                  "Describe what you need. FIELDed interprets your intent and matches it to businesses with verified capabilities.",
                icon: "◎",
              },
              {
                title: "Governed Execution",
                description:
                  "Every business operates through its Business Brain — governed rules for pricing, availability, policies, and qualification.",
                icon: "⬡",
              },
              {
                title: "Transparent Communication",
                description:
                  "Dedicated conversations per enquiry. Every message, quote, and decision is tracked and auditable.",
                icon: "◈",
              },
              {
                title: "Service Lifecycle",
                description:
                  "From enquiry to completion — quotes, bookings, scheduling, execution, and reviews in one platform.",
                icon: "◇",
              },
              {
                title: "Two-Sided Network",
                description:
                  "Customers discover and enquire. Businesses configure, qualify, and respond. Both sides equally important.",
                icon: "⬢",
              },
              {
                title: "Provider Agnostic",
                description:
                  "No hardcoded dependencies. AI, email, storage, payments — all behind replaceable adapter interfaces.",
                icon: "◉",
              },
            ].map((item) => (
              <div
                key={item.title}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6"
              >
                <div className="text-2xl text-[var(--accent)] mb-3" aria-hidden="true">
                  {item.icon}
                </div>
                <h3 className="text-lg font-semibold text-[var(--text-primary)]">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm text-[var(--text-secondary)] leading-relaxed">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section className="border-t border-[var(--border-subtle)]">
        <div className="mx-auto max-w-7xl px-4 py-20">
          <h2 className="text-center text-3xl font-bold text-[var(--text-primary)]">
            How it Works
          </h2>
          <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                step: "01",
                title: "Describe",
                description:
                  "Tell FIELDed what you need in plain language. No forms, no categories — just describe your service need.",
              },
              {
                step: "02",
                title: "Discover",
                description:
                  "FIELDed interprets your intent and matches it to businesses with the right capabilities and availability.",
              },
              {
                step: "03",
                title: "Enquire",
                description:
                  "Start a dedicated conversation with a business. Ask questions, share details, receive quotes.",
              },
              {
                step: "04",
                title: "Complete",
                description:
                  "Book the service, track progress, and leave a review. Every step governed by business rules.",
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[var(--accent)]/15 text-[var(--accent)] font-bold text-lg">
                  {item.step}
                </div>
                <h3 className="mt-4 text-lg font-semibold text-[var(--text-primary)]">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm text-[var(--text-secondary)] leading-relaxed">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* One Platform, Two Sides */}
      <section className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="mx-auto max-w-7xl px-4 py-20">
          <h2 className="text-center text-3xl font-bold text-[var(--text-primary)]">
            One Platform, Two Sides
          </h2>
          <div className="mt-12 grid gap-6 lg:grid-cols-2">
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
              <h3 className="text-xl font-semibold text-[var(--accent)]">
                For Customers
              </h3>
              <ul className="mt-6 space-y-4">
                {[
                  "Search and discover qualified businesses",
                  "Describe your need in plain language",
                  "Start dedicated conversations with businesses",
                  "Receive quotes and proposals",
                  "Book services and track progress",
                  "Leave reviews after completion",
                ].map((item) => (
                  <li
                    key={item}
                    className="flex items-start gap-3 text-[var(--text-secondary)]"
                  >
                    <span
                      className="mt-1.5 h-1.5 w-1.5 rounded-full bg-[var(--accent)] flex-shrink-0"
                      aria-hidden="true"
                    />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
              <h3 className="text-xl font-semibold text-[var(--accent)]">
                For Businesses
              </h3>
              <ul className="mt-6 space-y-4">
                {[
                  "Configure your Business Brain — pricing, policies, availability",
                  "Receive qualified enquiries from matching customers",
                  "Operate through governed rules, not ad-hoc decisions",
                  "Manage conversations, quotes, and bookings",
                  "Track performance and service execution",
                  "Build reputation through verified reviews",
                ].map((item) => (
                  <li
                    key={item}
                    className="flex items-start gap-3 text-[var(--text-secondary)]"
                  >
                    <span
                      className="mt-1.5 h-1.5 w-1.5 rounded-full bg-[var(--accent)] flex-shrink-0"
                      aria-hidden="true"
                    />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Powered by AI and the Business Brain */}
      <section className="border-t border-[var(--border-subtle)]">
        <div className="mx-auto max-w-7xl px-4 py-20">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-bold text-[var(--text-primary)]">
              Powered by AI and the Business Brain
            </h2>
            <p className="mt-4 text-[var(--text-secondary)] leading-relaxed">
              AI interprets customer intent, classifies service needs, and
              assists businesses in drafting responses. The Business Brain
              provides governed operational rules — pricing, qualification,
              availability, and escalation policies.
            </p>
            <p className="mt-4 text-[var(--text-secondary)] leading-relaxed">
              But AI never decides authoritatively. Deterministic backend logic
              remains the final authority on pricing, availability,
              authorization, and transaction state.
            </p>
          </div>
        </div>
      </section>

      {/* Built for Trust */}
      <section className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="mx-auto max-w-7xl px-4 py-20">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-bold text-[var(--text-primary)]">
              Built for Trust
            </h2>
            <p className="mt-4 text-[var(--text-secondary)] leading-relaxed">
              Tenant isolation ensures businesses never access another
              business&apos;s data. Customers only access their own information.
              Authorization is resolved server-side from authenticated identity.
              Every state transition is validated, recorded, and auditable.
            </p>
            <div className="mt-8 grid gap-4 sm:grid-cols-3">
              {[
                { label: "Tenant Isolation", detail: "Database-level enforcement" },
                { label: "Server-Side Auth", detail: "JWT with token rotation" },
                { label: "Audit Trail", detail: "Every action recorded" },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4 text-center"
                >
                  <p className="font-semibold text-[var(--text-primary)]">
                    {item.label}
                  </p>
                  <p className="mt-1 text-sm text-[var(--text-muted)]">
                    {item.detail}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Start with an enquiry */}
      <section className="border-t border-[var(--border-subtle)]">
        <div className="mx-auto max-w-7xl px-4 py-20 text-center">
          <h2 className="text-3xl font-bold text-[var(--text-primary)]">
            Start with an enquiry
          </h2>
          <p className="mt-4 text-[var(--text-secondary)]">
            Describe what you need. FIELDed handles the rest.
          </p>
          <a
            href="/signup"
            className="mt-8 inline-block rounded-lg bg-[var(--accent)] px-8 py-3 font-medium text-white hover:bg-[var(--accent-hover)] transition-colors"
          >
            Get Started
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-sm text-[var(--text-muted)]">
              &copy; 2026 FIELDed Platform
            </p>
            <div className="flex gap-6">
              <a
                href="/search"
                className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
              >
                Search
              </a>
              <a
                href="/login"
                className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
              >
                Sign In
              </a>
              <a
                href="/signup"
                className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
              >
                Sign Up
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
