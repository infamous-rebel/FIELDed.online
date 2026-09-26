"use client";

import { useEffect } from "react";

const SECTORS = [
  { name: "Accounting & Bookkeeping", desc: "Tax preparation, financial reporting, payroll, audit support", icon: "◆", services: "Tax filing, bookkeeping, payroll management, financial advisory", rules: "Engagement scope, fee schedules, compliance deadlines, document requirements", evidence: "Receipts, bank statements, prior returns, regulatory filings" },
  { name: "Recruitment & Staffing", desc: "Talent sourcing, placement, workforce management", icon: "◇", services: "Permanent placement, contract staffing, executive search, screening", rules: "Candidate qualifications, salary bands, notice periods, exclusivity terms", evidence: "Resumes, interview records, reference checks, offer letters" },
  { name: "Consulting", desc: "Strategy, operations, management advisory", icon: "⬡", services: "Strategy engagement, process audit, market analysis, transformation", rules: "Engagement type, deliverable scope, billing model, IP ownership", evidence: "Briefs, deliverables, change orders, sign-off records" },
  { name: "Creative & Marketing", desc: "Design, photography, video, branding, campaigns", icon: "◈", services: "Brand identity, campaign management, content production, photography", rules: "Revision limits, usage rights, delivery formats, approval stages", evidence: "Mood boards, drafts, approval records, asset licenses" },
  { name: "Technology & IT", desc: "Development, integration, managed services, support", icon: "⬢", services: "Custom development, system integration, IT support, cloud migration", rules: "SLA tiers, scope boundaries, tech stack constraints, escalation paths", evidence: "Requirements specs, test results, deployment logs, incident reports" },
  { name: "Property Management", desc: "Tenant management, maintenance, leasing", icon: "◉", services: "Tenant screening, lease administration, maintenance coordination, inspections", rules: "Response times, vendor approvals, lease terms, compliance requirements", evidence: "Inspection reports, maintenance requests, lease documents, vendor invoices" },
  { name: "Facilities Management", desc: "Cleaning, maintenance, security, building operations", icon: "▣", services: "Scheduled cleaning, reactive maintenance, security staffing, HVAC service", rules: "Service frequency, access requirements, SLA response times, safety compliance", evidence: "Work orders, completion photos, safety certificates, incident logs" },
  { name: "Logistics & Transport", desc: "Freight, delivery, warehousing, supply chain", icon: "⬟", services: "Freight forwarding, last-mile delivery, warehousing, inventory management", rules: "Capacity limits, delivery windows, hazardous materials, insurance coverage", evidence: "Bills of lading, tracking records, delivery confirmations, customs docs" },
  { name: "Corporate Training", desc: "Professional development, certification, workshops", icon: "◫", services: "Leadership programs, compliance training, certification prep, team workshops", rules: "Group sizes, delivery mode, assessment criteria, accreditation requirements", evidence: "Attendance records, assessment results, certificates, feedback forms" },
  { name: "Events", desc: "Planning, coordination, venue management, production", icon: "◉", services: "Corporate events, conferences, team building, product launches", rules: "Venue capacity, vendor coordination, cancellation policies, budget limits", evidence: "Contracts, attendee lists, vendor agreements, run sheets" },
  { name: "Architecture & Engineering", desc: "Design, planning, structural analysis, project management", icon: "△", services: "Concept design, planning applications, structural engineering, project oversight", rules: "Planning regulations, material specifications, approval stages, budget phases", evidence: "Drawings, calculations, planning submissions, site inspection reports" },
  { name: "Professional Services", desc: "Legal, compliance, HR, advisory", icon: "▢", services: "Legal advisory, compliance review, HR consulting, policy development", rules: "Engagement terms, confidentiality, jurisdiction, conflict checks", evidence: "Engagement letters, opinions, policy documents, correspondence records" },
];

const OPERATIONAL_LAYERS = [
  { label: "Business Capabilities", desc: "Each business defines what it can do through structured Service Offers", color: "var(--accent)" },
  { label: "Enquiry Routing", desc: "Customer intent is classified and matched to relevant capabilities", color: "var(--info)" },
  { label: "Business Brain", desc: "Versioned rules govern pricing, policies, qualification, and availability", color: "var(--warning)" },
  { label: "Workflow Execution", desc: "Approved enquiries become structured operational work with evidence", color: "var(--accent)" },
  { label: "Governed Action", desc: "Every action is validated against deterministic rules before execution", color: "var(--info)" },
  { label: "Audit & Trust", desc: "Complete provenance trail for every decision, transition, and outcome", color: "var(--warning)" },
];

export default function IndustriesPage() {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) entry.target.classList.add("visible");
        });
      },
      { threshold: 0.05, rootMargin: "80px 0px -40px 0px" }
    );
    const els = document.querySelectorAll(".reveal");
    els.forEach((el) => {
      observer.observe(el);
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) {
        el.classList.add("visible");
      }
    });
    return () => observer.disconnect();
  }, []);

  return (
    <div className="relative">
      {/* Background */}
      <div className="absolute inset-0 grid-bg opacity-30" aria-hidden="true" />
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px]"
        style={{
          background: "radial-gradient(ellipse at 50% 0%, var(--info) 0%, transparent 65%)",
          opacity: 0.05,
        }}
        aria-hidden="true"
      />

      <div className="relative mx-auto max-w-[1400px] px-6 pt-10 pb-16">
        {/* Hero */}
        <div className="max-w-2xl">
          <div className="flex items-center gap-2 mb-3">
            <span
              className="h-1.5 w-1.5 rounded-full bg-[var(--info)]"
              style={{ animation: "status-blink 2.5s ease-in-out infinite" }}
            />
            <span className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Industry-Agnostic Infrastructure
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)] lg:text-3xl">
            Different industries.
            <br />
            <span className="text-[var(--text-secondary)] font-medium text-xl lg:text-2xl">
              One operational foundation.
            </span>
          </h1>
          <p className="mt-3 text-sm text-[var(--text-secondary)] max-w-lg leading-relaxed">
            FIELDed is not built for a single industry vertical. Its operational model is based on
            business capabilities, services, enquiries, workflows, and governed execution — a
            foundation that adapts to any service business through its Business Brain.
          </p>
        </div>

        {/* Flow: what changes, what stays common */}
        <section className="reveal mt-10 border-t border-[var(--border-subtle)] pt-8">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                What changes between industries
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Services, rules, evidence, and workflows — all business-specific
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {[
              { label: "Services", color: "var(--accent)" },
              { label: "Business Rules", color: "var(--info)" },
              { label: "Evidence", color: "var(--warning)" },
              { label: "Workflows", color: "var(--accent)" },
              { label: "Pricing", color: "var(--info)" },
              { label: "Policies", color: "var(--warning)" },
            ].map((node, i) => (
              <div key={node.label} className="flex items-center gap-2">
                <div className="glass rounded-md px-3 py-1.5 flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: node.color }} />
                  <span className="text-xs font-medium text-[var(--text-secondary)]">{node.label}</span>
                </div>
                {i < 5 && (
                  <svg className="h-3 w-3 text-[var(--text-muted)] opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* What remains common */}
        <section className="reveal mt-8 border-t border-[var(--border-subtle)] pt-8">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                What remains common
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                The operational layer that governs every industry
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {OPERATIONAL_LAYERS.map((layer, i) => (
              <div key={layer.label} className="reveal glass rounded-lg p-4 hover:border-[var(--accent)]/15 transition-colors" style={{ transitionDelay: `${i * 0.06}s` }}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: layer.color }} />
                  <span className="text-xs font-semibold text-[var(--text-primary)]">{layer.label}</span>
                </div>
                <p className="text-[11px] text-[var(--text-muted)] leading-relaxed">{layer.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Sectors */}
        <section className="reveal mt-8 border-t border-[var(--border-subtle)] pt-8">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                Representative sectors
              </h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Each sector operates through the same FIELDed foundation with different knowledge and rules
              </p>
            </div>
            <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
              {SECTORS.length} sectors
            </span>
          </div>

          <div className="space-y-2">
            {SECTORS.map((sector, i) => (
              <div
                key={sector.name}
                className="reveal glass rounded-lg p-4 hover:border-[var(--accent)]/15 transition-colors"
                style={{ transitionDelay: `${Math.min(i * 0.04, 0.3)}s` }}
              >
                <div className="flex items-start gap-3">
                  <span
                    className="text-lg flex-shrink-0 mt-0.5 w-6 text-center"
                    style={{ color: "var(--info)" }}
                    aria-hidden="true"
                  >
                    {sector.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{sector.name}</h3>
                      <span className="text-[10px] text-[var(--text-muted)]">{sector.desc}</span>
                    </div>
                    <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <div className="rounded-md bg-white/[0.02] border border-white/[0.03] p-2.5">
                        <span className="text-[9px] font-medium text-[var(--accent)] uppercase tracking-wider">Services</span>
                        <p className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">{sector.services}</p>
                      </div>
                      <div className="rounded-md bg-white/[0.02] border border-white/[0.03] p-2.5">
                        <span className="text-[9px] font-medium text-[var(--info)] uppercase tracking-wider">Rules</span>
                        <p className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">{sector.rules}</p>
                      </div>
                      <div className="rounded-md bg-white/[0.02] border border-white/[0.03] p-2.5">
                        <span className="text-[9px] font-medium text-[var(--warning)] uppercase tracking-wider">Evidence</span>
                        <p className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">{sector.evidence}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* How Business Brain adapts */}
        <section className="reveal mt-8 border-t border-[var(--border-subtle)] pt-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <div className="lg:col-span-5">
              <span className="text-[10px] font-medium text-[var(--info)] uppercase tracking-wider">
                Adaptation Layer
              </span>
              <h2 className="mt-1.5 text-xl font-bold text-[var(--text-primary)]">
                How the Business Brain adapts
              </h2>
              <p className="mt-2 text-sm text-[var(--text-secondary)] leading-relaxed">
                Each business configures its own Brain with industry-specific knowledge, rules, and
                policies. The Brain interprets customer intent through the lens of that business&apos;s
                expertise — but deterministic rules remain the final authority.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {["Versioned", "Business-specific", "Governed", "Auditable"].map((tag) => (
                  <span
                    key={tag}
                    className="text-[10px] px-2 py-1 rounded-md border border-[var(--border-default)] text-[var(--text-secondary)]"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            <div className="lg:col-span-7">
              <div className="glass rounded-lg p-5">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
                    Brain Configuration Areas
                  </span>
                  <span className="flex items-center gap-1">
                    <span
                      className="h-1 w-1 rounded-full bg-[var(--accent)]"
                      style={{ animation: "status-blink 2s ease-in-out infinite" }}
                    />
                    <span className="text-[10px] text-[var(--text-muted)]">Per business</span>
                  </span>
                </div>
                <div className="space-y-1.5">
                  {[
                    { area: "Identity & Services", desc: "What the business offers and how it presents itself" },
                    { area: "Pricing Rules", desc: "How prices are determined — fixed, hourly, quote-based, tiered" },
                    { area: "Policy Rules", desc: "Cancellation, rescheduling, payment terms, guarantees" },
                    { area: "Qualification Rules", desc: "What a customer must provide before an enquiry proceeds" },
                    { area: "Availability Rules", desc: "When and how the business can accept work" },
                    { area: "Escalation Rules", desc: "When and how human intervention overrides AI proposals" },
                    { area: "Communication Policy", desc: "How the business communicates through enquiries and bookings" },
                  ].map((item, i) => (
                    <div key={item.area} className="flex items-start gap-3 p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.03] hover:border-white/[0.06] transition-colors">
                      <span
                        className="h-1.5 w-1.5 rounded-full mt-1 flex-shrink-0"
                        style={{ backgroundColor: i % 3 === 0 ? "var(--accent)" : i % 3 === 1 ? "var(--info)" : "var(--warning)" }}
                      />
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-medium text-[var(--text-primary)]">{item.area}</span>
                        <span className="text-[11px] text-[var(--text-muted)] ml-2">{item.desc}</span>
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
        </section>

        {/* Enquiry → Operational Work */}
        <section className="reveal mt-8 border-t border-[var(--border-subtle)] pt-8">
          <div className="mb-5">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              From enquiry to governed execution
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              How customer intent becomes structured operational work in any industry
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-0">
            {[
              { id: "01", label: "Enquiry", desc: "Customer describes a need in plain language", tags: ["Intent", "Classification"], accent: "var(--accent)" },
              { id: "02", label: "Qualification", desc: "Business Brain validates against rules and policies", tags: ["Rules", "Policies"], accent: "var(--info)" },
              { id: "03", label: "Proposal", desc: "AI drafts a response; deterministic rules validate pricing and terms", tags: ["Pricing", "Terms"], accent: "var(--warning)" },
              { id: "04", label: "Execution", desc: "Approved work proceeds with evidence collection and audit trail", tags: ["Booking", "Evidence"], accent: "var(--accent)" },
            ].map((step, i) => (
              <div key={step.id} className="reveal group relative" style={{ transitionDelay: `${i * 0.08}s` }}>
                {i > 0 && (
                  <div className="hidden lg:block absolute top-5 -left-4 w-8 overflow-visible">
                    <svg width="32" height="2" className="text-[var(--border-default)]">
                      <line x1="0" y1="1" x2="32" y2="1" stroke="currentColor" strokeWidth="1" className="flow-line" />
                    </svg>
                  </div>
                )}
                <div className="glass rounded-lg p-4 h-full hover:border-[var(--accent)]/20 transition-colors">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                      style={{ color: step.accent, backgroundColor: `${step.accent}15` }}
                    >
                      {step.id}
                    </span>
                    <span className="text-sm font-semibold text-[var(--text-primary)]">{step.label}</span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed mb-3">{step.desc}</p>
                  <div className="flex flex-wrap gap-1">
                    {step.tags.map((tag) => (
                      <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.03] text-[var(--text-muted)] border border-white/[0.04]">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="reveal mt-10 border-t border-[var(--border-subtle)] pt-8">
          <div className="glass rounded-lg p-6 text-center">
            <h2 className="text-lg font-bold text-[var(--text-primary)]">
              Your industry, your rules, your Brain
            </h2>
            <p className="mt-1.5 text-sm text-[var(--text-secondary)] max-w-md mx-auto">
              FIELDed adapts to how your business actually operates — not the other way around.
            </p>
            <div className="mt-4 flex items-center justify-center gap-3">
              <a
                href="/signup"
                className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--accent)] border border-[var(--accent)]/30 rounded-md px-4 py-2 hover:bg-[var(--accent)]/10 transition-colors"
              >
                Get Started
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                </svg>
              </a>
              <a
                href="/search"
                className="inline-flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                Try Search
              </a>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
