"use client";

import { useState, useEffect, useRef, useCallback, type FormEvent } from "react";
import { useRouter } from "next/navigation";

/* ── Data ──────────────────────────────────────────────── */

const PLACEHOLDER_EXAMPLES = [
  "I need a consultant for my startup...",
  "I need a photographer for an event...",
  "I need a developer for a website...",
  "I need a tutor for mathematics...",
  "I need a designer for a logo...",
  "I need a cleaner for my office...",
  "I need a repair service for appliances...",
  "I need a planner for a corporate event...",
];

const FLOW_STEPS = [
  {
    id: "01",
    label: "Describe",
    desc: "Plain-language intent — no forms, no categories",
    tags: ["Natural language", "Intent parsing"],
    accent: "var(--accent)",
  },
  {
    id: "02",
    label: "Discover",
    desc: "Deterministic matching against business capabilities",
    tags: ["Service matching", "Capability check"],
    accent: "var(--info)",
  },
  {
    id: "03",
    label: "Enquire",
    desc: "Dedicated conversation with governed communication",
    tags: ["Messaging", "Quote exchange"],
    accent: "var(--warning)",
  },
  {
    id: "04",
    label: "Complete",
    desc: "Booked, executed, and reviewed — fully auditable",
    tags: ["Booking", "Review"],
    accent: "var(--accent)",
  },
];

const BRAIN_STAGES = [
  { label: "Evidence", desc: "Customer intent, service context, history", color: "var(--info)" },
  { label: "Understanding", desc: "Classified needs, capability matching", color: "var(--warning)" },
  { label: "Governed Action", desc: "Pricing rules, policies, availability", color: "var(--accent)" },
];

const INDUSTRIES = [
  { name: "Consulting", desc: "Advisory, strategy, analysis", icon: "◆" },
  { name: "Creative", desc: "Design, photography, video", icon: "◇" },
  { name: "Technology", desc: "Development, integration, support", icon: "⬡" },
  { name: "Education", desc: "Tutoring, training, coaching", icon: "◈" },
  { name: "Facilities", desc: "Cleaning, maintenance, repair", icon: "⬢" },
  { name: "Events", desc: "Planning, coordination, logistics", icon: "◉" },
];

const CUSTOMER_CAPS = [
  "Natural-language search & discovery",
  "Dedicated enquiry conversations",
  "Quote comparison & booking",
  "Progress tracking & scheduling",
  "Verified completion reviews",
];

const BUSINESS_CAPS = [
  "Business Brain configuration",
  "Qualified enquiry routing",
  "Governed pricing & policies",
  "Conversation & quote management",
  "Performance & execution tracking",
];

/* ── Component ─────────────────────────────────────────── */

export default function LandingPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [activeIndustry, setActiveIndustry] = useState(0);
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIndex((i) => (i + 1) % PLACEHOLDER_EXAMPLES.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) entry.target.classList.add("visible");
        });
      },
      { threshold: 0.05, rootMargin: "80px 0px -40px 0px" }
    );
    // Observe ALL .reveal elements — sections AND their children
    const els = document.querySelectorAll(".reveal");
    els.forEach((el) => {
      observer.observe(el);
      // If already in viewport at mount, reveal immediately
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) {
        el.classList.add("visible");
      }
    });
    return () => observer.disconnect();
  }, []);

  const setRef = useCallback((index: number) => (el: HTMLElement | null) => {
    sectionRefs.current[index] = el;
  }, []);

  const handleEnquirySubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    sessionStorage.setItem("fielded_query", query.trim());
    router.push("/search");
  };

  return (
    <div className="relative">
      {/* ═══ HEADER ═══ */}
      <header className="fixed top-0 left-0 right-0 z-50 glass-subtle">
        <div className="mx-auto max-w-[1400px] px-6 h-12 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--accent)] text-[10px] font-bold text-white">
              F
            </div>
            <span className="text-sm font-semibold text-[var(--text-primary)]">
              FIELDed
            </span>
          </a>
          <nav className="flex items-center gap-1">
            <a
              href="/search"
              className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Search
            </a>
            <a
              href="/network"
              className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Network
            </a>
            <a
              href="#industries"
              className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Industries
            </a>
            <span className="mx-1 h-3 w-px bg-[var(--border-default)]" aria-hidden="true" />
            <a
              href="/login"
              className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Sign In
            </a>
            <a
              href="/signup"
              className="ml-1 px-3 py-1.5 text-xs font-medium text-[var(--accent)] border border-[var(--accent)]/30 rounded-md hover:bg-[var(--accent)]/10 transition-colors"
            >
              Get Started &rarr;
            </a>
          </nav>
        </div>
      </header>

      {/* ═══ HERO ═══ */}
      <section className="relative pt-12 pb-10 overflow-hidden">
        {/* Grid background */}
        <div className="absolute inset-0 grid-bg" aria-hidden="true" />
        {/* Radial glow */}
        <div
          className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px]"
          style={{
            background:
              "radial-gradient(ellipse at 50% 0%, var(--accent) 0%, transparent 65%)",
            opacity: 0.08,
            animation: "glow-pulse 6s ease-in-out infinite",
          }}
          aria-hidden="true"
        />

        <div className="relative mx-auto max-w-[1400px] px-6 pt-16 pb-6">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2 mb-4">
              <span
                className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
                style={{ animation: "status-blink 2.5s ease-in-out infinite" }}
              />
              <span className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
                Service Network — Active
              </span>
            </div>
            <h1 className="text-4xl font-bold tracking-tight text-[var(--text-primary)] leading-[1.1] lg:text-5xl">
              Describe what you need.
              <br />
              <span className="text-[var(--text-secondary)] font-medium text-3xl lg:text-4xl">
                FIELDed finds where it can be done.
              </span>
            </h1>
            <p className="mt-3 text-sm text-[var(--text-secondary)] max-w-lg leading-relaxed">
              Customer-to-business service network. Intent meets capability
              through governed execution — every business operates through its
              Business Brain.
            </p>

            {/* Search interaction */}
            <form
              onSubmit={handleEnquirySubmit}
              className="mt-5 flex items-center gap-0 glass rounded-lg overflow-hidden max-w-xl"
            >
              <div className="flex items-center gap-2 flex-1 px-4">
                <svg
                  className="h-4 w-4 text-[var(--text-muted)] flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={PLACEHOLDER_EXAMPLES[placeholderIndex]}
                  className="w-full bg-transparent py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none"
                  aria-label="Describe your service need"
                />
              </div>
              <button
                type="submit"
                className="flex items-center gap-1.5 px-4 py-3 text-sm font-medium text-[var(--accent)] border-l border-white/5 hover:bg-[var(--accent)]/10 transition-colors whitespace-nowrap"
              >
                Search
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17 8l4 4m0 0l-4 4m4-4H3"
                  />
                </svg>
              </button>
            </form>
          </div>

          {/* Flow preview */}
          <div className="mt-8 flex items-center gap-2 flex-wrap">
            {[
              { label: "Intent", color: "var(--accent)" },
              { label: "Match", color: "var(--info)" },
              { label: "Enquiry", color: "var(--warning)" },
              { label: "Governed", color: "var(--accent)" },
            ].map((node, i) => (
              <div key={node.label} className="flex items-center gap-2">
                <div
                  className="glass-subtle rounded-md px-2.5 py-1 flex items-center gap-1.5"
                  style={{ animation: `slide-up 0.5s ease-out ${0.3 + i * 0.12}s both` }}
                >
                  <span
                    className="h-1 w-1 rounded-full"
                    style={{ backgroundColor: node.color }}
                  />
                  <span className="text-[10px] font-medium text-[var(--text-secondary)]">
                    {node.label}
                  </span>
                </div>
                {i < 3 && (
                  <svg
                    className="h-3 w-3 text-[var(--text-muted)] opacity-40"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                )}
              </div>
            ))}
          </div>

          {/* Status indicators */}
          <div className="mt-6 flex items-center gap-5">
            {[
              { label: "Network", value: "Active", color: "var(--accent)" },
              { label: "Discovery", value: "Online", color: "var(--info)" },
              { label: "Brain", value: "Ready", color: "var(--accent)" },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-1.5">
                <span
                  className="h-1 w-1 rounded-full"
                  style={{
                    backgroundColor: s.color,
                    animation: "status-blink 3s ease-in-out infinite",
                  }}
                />
                <span className="text-[10px] text-[var(--text-muted)]">
                  {s.label}
                </span>
                <span className="text-[10px] font-medium text-[var(--text-secondary)]">
                  {s.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ HOW FIELDed WORKS ═══ */}
      <section
        id="how"
        ref={setRef(0)}
        className="reveal relative py-14 border-t border-[var(--border-subtle)]"
      >
        <div className="mx-auto max-w-[1400px] px-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                How FIELDed Works
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Intent → discovery → enquiry → governed execution
              </p>
            </div>
            <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
              4 stages
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-0">
            {FLOW_STEPS.map((step, i) => (
              <div key={step.id} className="reveal delay-1 group relative">
                {/* Connector line */}
                {i > 0 && (
                  <div className="hidden lg:block absolute top-5 -left-4 w-8 overflow-visible">
                    <svg width="32" height="2" className="text-[var(--border-default)]">
                      <line
                        x1="0"
                        y1="1"
                        x2="32"
                        y2="1"
                        stroke="currentColor"
                        strokeWidth="1"
                        className="flow-line"
                      />
                    </svg>
                  </div>
                )}
                <div className="glass rounded-lg p-4 h-full hover:border-[var(--accent)]/20 transition-colors">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                      style={{
                        color: step.accent,
                        backgroundColor: `${step.accent}15`,
                      }}
                    >
                      {step.id}
                    </span>
                    <span className="text-sm font-semibold text-[var(--text-primary)]">
                      {step.label}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed mb-3">
                    {step.desc}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {step.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.03] text-[var(--text-muted)] border border-white/[0.04]"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ BUSINESS BRAIN ═══ */}
      <section
        id="brain"
        ref={setRef(1)}
        className="reveal relative py-14 border-t border-[var(--border-subtle)]"
      >
        <div className="absolute inset-0 opacity-[0.03]" aria-hidden="true">
          <div
            className="absolute top-1/2 right-0 w-[400px] h-[400px] -translate-y-1/2"
            style={{
              background:
                "radial-gradient(circle, var(--info) 0%, transparent 70%)",
            }}
          />
        </div>

        <div className="relative mx-auto max-w-[1400px] px-6">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            {/* Left — description */}
            <div className="lg:col-span-5">
              <span className="text-[10px] font-medium text-[var(--info)] uppercase tracking-wider">
                Intelligence Layer
              </span>
              <h2 className="mt-1.5 text-xl font-bold text-[var(--text-primary)]">
                The Business Brain
              </h2>
              <p className="mt-2 text-sm text-[var(--text-secondary)] leading-relaxed">
                Every business operates through a versioned, governed Brain. AI
                interprets customer intent and classifies needs — but deterministic
                rules remain the final authority on pricing, availability,
                authorization, and transaction state.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {[
                  "Versioned",
                  "Governed",
                  "Deterministic",
                  "Auditable",
                ].map((tag) => (
                  <span
                    key={tag}
                    className="text-[10px] px-2 py-1 rounded-md border border-[var(--border-default)] text-[var(--text-secondary)]"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <a
                href="/signup"
                className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--accent)] hover:underline"
              >
                Configure your Brain
                <svg
                  className="h-3 w-3"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17 8l4 4m0 0l-4 4m4-4H3"
                  />
                </svg>
              </a>
            </div>

            {/* Right — pipeline */}
            <div className="lg:col-span-7">
              <div className="glass rounded-lg p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
                    Decision Pipeline
                  </span>
                  <span className="flex items-center gap-1">
                    <span
                      className="h-1 w-1 rounded-full bg-[var(--accent)]"
                      style={{ animation: "status-blink 2s ease-in-out infinite" }}
                    />
                    <span className="text-[10px] text-[var(--text-muted)]">
                      Active
                    </span>
                  </span>
                </div>
                <div className="space-y-2">
                  {BRAIN_STAGES.map((stage, i) => (
                    <div key={stage.label} className="reveal delay-1">
                      <div className="flex items-start gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/[0.03] hover:border-white/[0.06] transition-colors">
                        <div className="flex flex-col items-center gap-0.5 pt-0.5">
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{ backgroundColor: stage.color }}
                          />
                          {i < BRAIN_STAGES.length - 1 && (
                            <div className="w-px h-5 bg-[var(--border-default)] mt-0.5" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-semibold text-[var(--text-primary)]">
                            {stage.label}
                          </div>
                          <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
                            {stage.desc}
                          </div>
                        </div>
                        <span
                          className="text-[9px] font-medium px-1.5 py-0.5 rounded self-center"
                          style={{
                            color: stage.color,
                            backgroundColor: `${stage.color}12`,
                          }}
                        >
                          Stage {i + 1}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-white/[0.04] flex items-center justify-between">
                  <span className="text-[10px] text-[var(--text-muted)]">
                    AI proposes &middot; Rules validate &middot; Owner decides
                  </span>
                  <span className="text-[10px] text-[var(--accent)] font-medium">
                    Authority: deterministic
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══ INDUSTRIES ═══ */}
      <section
        id="industries"
        ref={setRef(2)}
        className="reveal py-14 border-t border-[var(--border-subtle)]"
      >
        <div className="mx-auto max-w-[1400px] px-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                Industry-Agnostic Infrastructure
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Same operational layer — any service vertical
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {INDUSTRIES.map((ind, i) => (
              <button
                key={ind.name}
                type="button"
                onClick={() => setActiveIndustry(i)}
                className={`reveal glass rounded-lg p-3 text-left transition-all hover:border-[var(--accent)]/20 ${
                  activeIndustry === i ? "border-[var(--accent)]/30" : ""
                }`}
                style={{ transitionDelay: `${i * 0.06}s` }}
              >
                <span
                  className="text-lg block mb-1.5"
                  style={{
                    color:
                      activeIndustry === i
                        ? "var(--accent)"
                        : "var(--text-muted)",
                  }}
                  aria-hidden="true"
                >
                  {ind.icon}
                </span>
                <span className="text-xs font-medium text-[var(--text-primary)] block">
                  {ind.name}
                </span>
                <span className="text-[10px] text-[var(--text-muted)] block mt-0.5">
                  {ind.desc}
                </span>
                <div
                  className="mt-2 h-px w-full origin-left transition-transform duration-500"
                  style={{
                    backgroundColor: "var(--accent)",
                    transform:
                      activeIndustry === i ? "scaleX(1)" : "scaleX(0)",
                  }}
                />
              </button>
            ))}
          </div>
          <p className="mt-4 text-[11px] text-[var(--text-muted)] text-center">
            One platform &middot; Governed rules &middot; Every vertical
          </p>
        </div>
      </section>

      {/* ═══ TWO SIDES ═══ */}
      <section
        id="network"
        ref={setRef(3)}
        className="reveal py-14 border-t border-[var(--border-subtle)]"
      >
        <div className="mx-auto max-w-[1400px] px-6">
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Two-Sided Network
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              Both sides equally important — connected through governed
              infrastructure
            </p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Customer panel */}
            <div className="reveal delay-1 lg:col-span-5 glass rounded-lg p-5 hover:border-[var(--info)]/15 transition-colors">
              <div className="flex items-center gap-2 mb-3">
                <span className="h-2 w-2 rounded-full bg-[var(--info)]" />
                <span className="text-xs font-semibold text-[var(--info)]">
                  Customer Network
                </span>
              </div>
              <ul className="space-y-2">
                {CUSTOMER_CAPS.map((cap) => (
                  <li
                    key={cap}
                    className="flex items-center gap-2 text-xs text-[var(--text-secondary)]"
                  >
                    <svg
                      className="h-3 w-3 text-[var(--info)] flex-shrink-0"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                    {cap}
                  </li>
                ))}
              </ul>
            </div>

            {/* Connection */}
            <div className="reveal delay-2 hidden lg:flex lg:col-span-2 flex-col items-center justify-center gap-2">
              <svg
                width="80"
                height="40"
                viewBox="0 0 80 40"
                className="text-[var(--border-default)]"
              >
                <line
                  x1="0"
                  y1="12"
                  x2="80"
                  y2="12"
                  stroke="currentColor"
                  strokeWidth="1"
                  className="flow-line"
                />
                <line
                  x1="80"
                  y1="28"
                  x2="0"
                  y2="28"
                  stroke="currentColor"
                  strokeWidth="1"
                  className="flow-line"
                />
              </svg>
              <span className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider">
                Governed
              </span>
            </div>

            {/* Business panel */}
            <div className="reveal delay-3 lg:col-span-5 glass rounded-lg p-5 hover:border-[var(--accent)]/15 transition-colors">
              <div className="flex items-center gap-2 mb-3">
                <span className="h-2 w-2 rounded-full bg-[var(--accent)]" />
                <span className="text-xs font-semibold text-[var(--accent)]">
                  Business Operations
                </span>
              </div>
              <ul className="space-y-2">
                {BUSINESS_CAPS.map((cap) => (
                  <li
                    key={cap}
                    className="flex items-center gap-2 text-xs text-[var(--text-secondary)]"
                  >
                    <svg
                      className="h-3 w-3 text-[var(--accent)] flex-shrink-0"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    {cap}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ═══ TRUST ═══ */}
      <section
        ref={setRef(4)}
        className="reveal py-10 border-t border-[var(--border-subtle)]"
      >
        <div className="mx-auto max-w-[1400px] px-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 sm:gap-8">
            <div className="flex-shrink-0">
              <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
                Trust &amp; Security
              </span>
            </div>
            <div className="flex flex-wrap gap-3">
              {[
                {
                  label: "Private by Design",
                  detail: "Tenant-isolated data",
                },
                {
                  label: "Secure Access",
                  detail: "JWT + bcrypt auth",
                },
                {
                  label: "Full Audit Trail",
                  detail: "Every action tracked",
                },
                {
                  label: "Deterministic Rules",
                  detail: "AI proposes, logic decides",
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-[var(--border-subtle)] bg-white/[0.01]"
                >
                  <svg
                    className="h-3 w-3 text-[var(--accent)] flex-shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                    />
                  </svg>
                  <span className="text-[11px] font-medium text-[var(--text-primary)]">
                    {item.label}
                  </span>
                  <span className="text-[10px] text-[var(--text-muted)] hidden sm:inline">
                    &middot; {item.detail}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══ CTA ═══ */}
      <section className="relative py-14 border-t border-[var(--border-subtle)] overflow-hidden">
        <div className="absolute inset-0 grid-bg opacity-50" aria-hidden="true" />
        <div
          className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px]"
          style={{
            background:
              "radial-gradient(ellipse at 50% 100%, var(--accent) 0%, transparent 65%)",
            opacity: 0.06,
          }}
          aria-hidden="true"
        />
        <div className="relative mx-auto max-w-[1400px] px-6 text-center">
          <h2 className="text-xl font-bold text-[var(--text-primary)]">
            Start with an enquiry
          </h2>
          <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
            Describe what you need. FIELDed handles the rest.
          </p>
          <div className="mt-5 flex items-center justify-center gap-3">
            <a
              href="/signup"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--accent)] border border-[var(--accent)]/30 rounded-md px-4 py-2 hover:bg-[var(--accent)]/10 transition-colors"
            >
              Create Account
              <svg
                className="h-3.5 w-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17 8l4 4m0 0l-4 4m4-4H3"
                />
              </svg>
            </a>
            <a
              href="/search"
              className="inline-flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Try Search
              <svg
                className="h-3 w-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </a>
          </div>
        </div>
      </section>

      {/* ═══ FOOTER ══ */}
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
                  { href: "#how", label: "How It Works" },
                  { href: "#brain", label: "Business Brain" },
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
                  { href: "#industries", label: "Industries" },
                  { href: "#network", label: "Two-Sided Network" },
                  { href: "#how", label: "Trust &amp; Security" },
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
            <a
              href="mailto:hello@fielded.online"
              className="text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              hello@fielded.online
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
