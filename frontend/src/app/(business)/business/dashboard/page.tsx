"use client";

import { useEffect, useState } from "react";
import {
  auth,
  businesses,
  enquiries,
  quotes,
  bookings,
  serviceExecutions,
  ledger,
  brainConversation,
  type UserResponse,
  type BusinessSummary,
  type EnquiryData,
  type QuoteData,
  type BookingData,
  type ServiceExecutionData,
  type LedgerSummaryData,
  type NeedsAttentionItem,
  type BrainProposalData,
  type BrainContext,
} from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { statusToBadgeVariant } from "@/lib/status";

type WorkTab = "all" | "enquiries" | "bookings" | "quotes";

export default function BusinessDashboardPage() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [bizList, setBizList] = useState<BusinessSummary[]>([]);
  const [enquiryList, setEnquiryList] = useState<EnquiryData[]>([]);
  const [quoteList, setQuoteList] = useState<QuoteData[]>([]);
  const [bookingList, setBookingList] = useState<BookingData[]>([]);
  const [executionList, setExecutionList] = useState<ServiceExecutionData[]>([]);
  const [summary, setSummary] = useState<LedgerSummaryData | null>(null);
  const [loading, setLoading] = useState(true);

  // Business Brain data
  const [brainAttention, setBrainAttention] = useState<NeedsAttentionItem[]>([]);
  const [brainProposals, setBrainProposals] = useState<BrainProposalData[]>([]);
  const [brainContext, setBrainContext] = useState<BrainContext | null>(null);
  const [brainLoading, setBrainLoading] = useState(true);

  const [workTab, setWorkTab] = useState<WorkTab>("all");

  useEffect(() => {
    async function loadData() {
      try {
        const [userData, bizData] = await Promise.all([
          auth.me(),
          businesses.list(),
        ]);
        setUser(userData);
        setBizList(bizData);

        if (bizData.length > 0) {
          const bizId = bizData[0].id;
          const [enqData, qtData, bkData, exData, sumData] = await Promise.all([
            enquiries.listForBusiness(bizId).catch(() => [] as EnquiryData[]),
            quotes.listForBusiness(bizId).catch(() => [] as QuoteData[]),
            bookings.listForBusiness(bizId).catch(() => [] as BookingData[]),
            serviceExecutions.listForBusiness(bizId).catch(() => [] as ServiceExecutionData[]),
            ledger.getSummary(bizId).catch(() => null),
          ]);
          setEnquiryList(enqData);
          setQuoteList(qtData);
          setBookingList(bkData);
          setExecutionList(exData);
          setSummary(sumData);

          // Load Brain data
          try {
            const [proposals, context] = await Promise.all([
              brainConversation.listPendingProposals(bizId).catch(() => []),
              brainConversation.getContext(bizId).catch(() => null),
            ]);
            setBrainProposals(proposals);
            if (context) setBrainContext(context);
            setBrainAttention(context?.attention ?? []);
          } catch {
            // Brain data optional
          }
        }
      } catch {
        // Auth or API error — page shows empty states
      } finally {
        setLoading(false);
        setBrainLoading(false);
      }
    }
    loadData();
  }, []);

  const activeEnquiries = enquiryList.filter(
    (e) => !["cancelled", "expired", "declined"].includes(e.status)
  );
  const pendingQuotes = quoteList.filter((q) => q.status === "issued");
  const upcomingBookings = bookingList.filter((b) =>
    ["requested", "proposed", "accepted", "confirmed", "in_progress"].includes(b.status)
  );
  const activeExecutions = executionList.filter((e) =>
    ["scheduled", "in_progress"].includes(e.status)
  );

  // Attention items: enquiries/quotes/bookings requiring action + Brain attention
  const attentionItems = [
    ...pendingQuotes.map((q) => ({
      type: "quote" as const,
      id: q.id,
      title: `Quote awaiting approval`,
      subtitle: `${q.reference} · ${new Date(q.created_at).toLocaleDateString()}`,
      urgent: false,
      href: "/business/quotes",
    })),
    ...enquiryList.filter((e) => e.status === "new").map((e) => ({
      type: "enquiry" as const,
      id: e.id,
      title: `New enquiry received`,
      subtitle: `${e.reference} · ${new Date(e.created_at).toLocaleDateString()}`,
      urgent: true,
      href: `/business/enquiries/${e.id}`,
    })),
    ...brainAttention.slice(0, 3).map((item, idx) => ({
      type: "brain" as const,
      id: `brain-${item.id || idx}`,
      title: item.title || "Brain attention",
      subtitle: item.affected_area || "",
      urgent: item.is_urgent ?? false,
      href: "/business/brain",
    })),
  ].sort((a, b) => (a.urgent === b.urgent ? 0 : a.urgent ? -1 : 1));

  // Recent activity: 5 most recent across enquiries and bookings
  const recentItems = [
    ...enquiryList.map((e) => ({
      type: "enquiry" as const,
      id: e.id,
      label: e.subject || `Enquiry ${e.reference}`,
      sub: `${e.reference} · ${new Date(e.created_at).toLocaleDateString()}`,
      status: e.status,
      date: e.created_at,
    })),
    ...bookingList.map((b) => ({
      type: "booking" as const,
      id: b.id,
      label: `Booking ${b.reference}`,
      sub: new Date(b.requested_at).toLocaleDateString(),
      status: b.status,
      date: b.created_at,
    })),
  ]
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 5);

  // Live work data
  const liveWorkItems = [
    ...enquiryList.slice(0, 10).map((e) => ({
      type: "enquiry" as const,
      id: e.id,
      reference: e.reference,
      subject: e.subject || "No subject",
      status: e.status,
      updated: e.updated_at || e.created_at,
      href: `/business/enquiries/${e.id}`,
    })),
    ...bookingList.slice(0, 10).map((b) => ({
      type: "booking" as const,
      id: b.id,
      reference: b.reference,
      subject: `Booking`,
      status: b.status,
      updated: b.updated_at || b.created_at,
      href: "/business/bookings",
    })),
    ...quoteList.slice(0, 10).map((q) => ({
      type: "quote" as const,
      id: q.id,
      reference: q.reference,
      subject: `Quote`,
      status: q.status,
      updated: q.updated_at || q.created_at,
      href: "/business/quotes",
    })),
  ].sort((a, b) => new Date(b.updated).getTime() - new Date(a.updated).getTime());

  const filteredWork = workTab === "all"
    ? liveWorkItems
    : liveWorkItems.filter((item) => {
        if (workTab === "enquiries") return item.type === "enquiry";
        if (workTab === "bookings") return item.type === "booking";
        if (workTab === "quotes") return item.type === "quote";
        return true;
      });

  const brainStatus = brainContext
    ? brainProposals.length > 0 || brainAttention.length > 0
      ? "Needs attention"
      : "Active"
    : "Not configured";

  return (
    <div className="space-y-6">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <div>
          {loading ? (
            <LoadingSkeleton lines={2} />
          ) : (
            <>
              <h1 className="text-2xl font-bold text-[var(--text-primary)]">
                Good {getGreeting()}, {getDisplayName(user)}
              </h1>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {bizList.length > 0
                  ? `${new Date().toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })}`
                  : (
                    <>
                      No businesses registered yet.{" "}
                      <a href="/business/onboarding" className="text-[var(--accent)] hover:underline">
                        Set up your business
                      </a>
                    </>
                  )}
              </p>
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
            <span className="w-2 h-2 rounded-full bg-[var(--accent)]"></span>
            <span>Business Online</span>
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--accent)]/15 text-xs font-semibold text-[var(--accent)]">
            {(getDisplayName(user)[0] || "?").toUpperCase()}
          </div>
        </div>
      </div>

      {/* Metrics row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-live="polite">
        <MetricCard
          label="Active Enquiries"
          value={loading ? null : activeEnquiries.length}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          }
          trend={enquiryList.length > 0 ? `${enquiryList.length} total` : undefined}
        />
        <MetricCard
          label="Pending Quotes"
          value={loading ? null : pendingQuotes.length}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          }
          trend={quoteList.length > 0 ? `${quoteList.length} total` : undefined}
        />
        <MetricCard
          label="Upcoming Bookings"
          value={loading ? null : upcomingBookings.length}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          }
          trend={bookingList.length > 0 ? `${bookingList.length} total` : undefined}
        />
        <MetricCard
          label="Revenue (paid)"
          value={loading || !summary ? null : formatAmount(Number(summary.paid_amount))}
          prefix="$"
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          trend={summary?.outstanding_amount ? `Outstanding: ${formatAmount(Number(summary.outstanding_amount))}` : undefined}
        />
      </div>

      {/* Attention + Brain + Actions row */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Attention Required */}
        <Card padding="md">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-red-500/15 flex items-center justify-center">
                <svg className="w-3.5 h-3.5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </span>
              Attention Required
              {attentionItems.length > 0 && (
                <span className="inline-flex items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-semibold text-white min-w-[18px]">
                  {attentionItems.length}
                </span>
              )}
            </h2>
            <a href="/business/enquiries" className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              View all →
            </a>
          </div>
          {attentionItems.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)] py-4">No items requiring attention</p>
          ) : (
            <div className="space-y-2">
              {attentionItems.slice(0, 4).map((item) => (
                <a
                  key={`${item.type}-${item.id}`}
                  href={item.href}
                  className={`flex items-start gap-3 rounded-lg p-2.5 transition-colors hover:bg-[var(--bg-elevated)] ${
                    item.urgent ? "bg-red-500/5" : ""
                  }`}
                >
                  <div className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                    item.urgent ? "bg-red-500/20 text-red-400" : "bg-blue-500/15 text-blue-400"
                  }`}>
                    {item.type === "quote" ? "$" : item.type === "enquiry" ? "!" : "B"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[var(--text-primary)] leading-tight">{item.title}</p>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5 truncate">{item.subtitle}</p>
                  </div>
                </a>
              ))}
            </div>
          )}
        </Card>

        {/* Business Brain Insights */}
        <Card padding="md">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-purple-500/15 flex items-center justify-center">
                <svg className="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2a8 8 0 0 0-8 8c0 3.4 2.1 6.3 5 7.5V20a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-2.5c2.9-1.2 5-4.1 5-7.5a8 8 0 0 0-8-8z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 22h4" />
                </svg>
              </span>
              Business Brain
            </h2>
            <a href="/business/brain" className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              Open →
            </a>
          </div>
          {brainLoading ? (
            <LoadingSkeleton lines={3} />
          ) : brainProposals.length === 0 && brainAttention.length === 0 ? (
            <div className="py-4">
              <p className="text-sm text-[var(--text-muted)] mb-2">
                {brainContext ? "Brain is active and learning" : "Business Brain not configured"}
              </p>
              <a href="/business/brain" className="text-xs text-[var(--accent)] hover:underline">
                {brainContext ? "View knowledge →" : "Set up your Brain →"}
              </a>
            </div>
          ) : (
            <div className="space-y-2">
              {brainProposals.slice(0, 2).map((proposal) => (
                <a
                  key={proposal.id}
                  href="/business/brain"
                  className="flex items-start gap-3 rounded-lg p-2.5 transition-colors hover:bg-[var(--bg-elevated)]"
                >
                  <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-purple-500/15 text-xs font-semibold text-purple-400">
                    P
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[var(--text-primary)] leading-tight truncate">
                      {typeof proposal.proposed_change.summary === "string"
                        ? proposal.proposed_change.summary
                        : "Proposal ready"}
                    </p>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">
                      {proposal.proposal_type.replace(/_/g, " ")}
                    </p>
                  </div>
                </a>
              ))}
              {brainAttention.slice(0, 2).map((item, idx) => (
                <a
                  key={`attn-${item.id || idx}`}
                  href="/business/brain"
                  className="flex items-start gap-3 rounded-lg p-2.5 transition-colors hover:bg-[var(--bg-elevated)]"
                >
                  <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-xs font-semibold text-amber-400">
                    !
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[var(--text-primary)] leading-tight truncate">{item.title}</p>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">{item.affected_area || ""}</p>
                  </div>
                </a>
              ))}
            </div>
          )}
        </Card>

        {/* Quick Actions */}
        <Card padding="md">
          <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-4 flex items-center gap-2">
            <span className="w-6 h-6 rounded-lg bg-blue-500/15 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </span>
            Quick Actions
          </h2>
          <div className="space-y-1.5">
            <QuickAction href="/business/enquiries" label="View enquiries" icon="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
            <QuickAction href="/business/services" label="Manage services" icon="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            <QuickAction href="/business/payments" label="Payments" icon="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
            <QuickAction href="/business/call-agent" label="Call Agent" icon="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            <QuickAction href="/business/profile" label="Edit profile" icon="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </div>
        </Card>
      </div>

      {/* Live Work + Activity Feed */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Live Work */}
        <div className="lg:col-span-2">
          <Card padding="md">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
                <span className="w-6 h-6 rounded-lg bg-emerald-500/15 flex items-center justify-center">
                  <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </span>
                Live Work
              </h2>
              <div className="flex items-center gap-1">
                {(["all", "enquiries", "bookings", "quotes"] as WorkTab[]).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setWorkTab(tab)}
                    className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                      workTab === tab
                        ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                        : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    {tab === "all" ? "All" : tab.charAt(0).toUpperCase() + tab.slice(1)}
                    {tab === "all" && ` ${liveWorkItems.length}`}
                    {tab === "enquiries" && ` ${enquiryList.length}`}
                    {tab === "bookings" && ` ${bookingList.length}`}
                    {tab === "quotes" && ` ${quoteList.length}`}
                  </button>
                ))}
              </div>
            </div>
            {filteredWork.length === 0 ? (
              <EmptyState
                title="No work items"
                description={workTab === "all" ? "Active enquiries, bookings, and quotes will appear here." : `No ${workTab} found.`}
              />
            ) : (
              <div className="space-y-1">
                {filteredWork.slice(0, 8).map((item) => (
                  <a
                    key={`${item.type}-${item.id}`}
                    href={item.href}
                    className="flex items-center justify-between rounded-lg px-3 py-2.5 transition-colors hover:bg-[var(--bg-elevated)]"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-xs text-[var(--text-muted)] font-mono w-16 truncate">
                        {item.reference}
                      </span>
                      <span className="text-sm text-[var(--text-primary)] truncate">
                        {item.subject}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant={statusToBadgeVariant(item.status)}>
                        {item.status.replace(/_/g, " ")}
                      </Badge>
                      <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">
                        {formatTimeAgo(item.updated)}
                      </span>
                      <svg className="w-4 h-4 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </a>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Activity Feed */}
        <Card padding="md">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-cyan-500/15 flex items-center justify-center">
                <svg className="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </span>
              Activity Feed
            </h2>
            <a href="/business/enquiries" className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
              View all →
            </a>
          </div>
          {recentItems.length === 0 ? (
            <EmptyState
              title="No activity yet"
              description="Recent enquiries and bookings will appear here."
            />
          ) : (
            <div className="space-y-3">
              {recentItems.map((item, idx) => (
                <a
                  key={`${item.type}-${item.id}`}
                  href={
                    item.type === "enquiry"
                      ? `/business/enquiries/${item.id}`
                      : "/business/bookings"
                  }
                  className="flex items-start gap-3"
                >
                  <div className="flex flex-col items-center">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${
                      item.type === "enquiry"
                        ? "bg-blue-500/15 text-blue-400"
                        : "bg-emerald-500/15 text-emerald-400"
                    }`}>
                      {item.type === "enquiry" ? "E" : "B"}
                    </div>
                    {idx < recentItems.length - 1 && (
                      <div className="w-px h-4 bg-[var(--border-subtle)] mt-1"></div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0 pb-3">
                    <p className="text-sm text-[var(--text-primary)] leading-tight truncate">{item.label}</p>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">{item.sub}</p>
                    <p className="text-[10px] text-[var(--text-muted)] mt-1">
                      {new Date(item.date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </a>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

// --- Subcomponents ---

function MetricCard({
  label,
  value,
  icon,
  prefix,
  trend,
}: {
  label: string;
  value: number | string | null;
  icon: React.ReactNode;
  prefix?: string;
  trend?: string;
}) {
  return (
    <Card padding="sm">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs text-[var(--text-muted)] mb-1">{label}</p>
          {value === null ? (
            <LoadingSkeleton lines={1} />
          ) : (
            <p className="text-2xl font-bold text-[var(--text-primary)] tabular-nums">
              {prefix}{value}
            </p>
          )}
          {trend && (
            <p className="text-[10px] text-[var(--text-muted)] mt-1">{trend}</p>
          )}
        </div>
        <div className="w-8 h-8 rounded-lg bg-[var(--accent)]/10 flex items-center justify-center text-[var(--accent)]">
          {icon}
        </div>
      </div>
    </Card>
  );
}

function QuickAction({ href, label, icon }: { href: string; label: string; icon: string }) {
  return (
    <a
      href={href}
      className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)] transition-colors"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d={icon} />
      </svg>
      <span className="flex-1">{label}</span>
      <svg className="w-3.5 h-3.5 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
      </svg>
    </a>
  );
}

// --- Helpers ---

function getDisplayName(user: UserResponse | null): string {
  if (!user) return "Operator";
  const firstName = user.customer_profile?.first_name;
  if (firstName) return firstName;
  return user.email || "Operator";
}

function formatAmount(amount: number): string {
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 7) return `${diffDays}d`;
  return date.toLocaleDateString();
}
