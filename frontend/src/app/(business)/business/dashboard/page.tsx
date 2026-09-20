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
  type UserResponse,
  type BusinessSummary,
  type EnquiryData,
  type QuoteData,
  type BookingData,
  type ServiceExecutionData,
  type LedgerSummaryData,
} from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

export default function BusinessDashboardPage() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [bizList, setBizList] = useState<BusinessSummary[]>([]);
  const [enquiryList, setEnquiryList] = useState<EnquiryData[]>([]);
  const [quoteList, setQuoteList] = useState<QuoteData[]>([]);
  const [bookingList, setBookingList] = useState<BookingData[]>([]);
  const [executionList, setExecutionList] = useState<ServiceExecutionData[]>([]);
  const [summary, setSummary] = useState<LedgerSummaryData | null>(null);
  const [loading, setLoading] = useState(true);

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
        }
      } catch {
        // Auth or API error — page shows empty states
      } finally {
        setLoading(false);
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

  // Recent activity: 3 most recent across enquiries and bookings (not an infinite feed)
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
    .slice(0, 3);

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div>
        {loading ? (
          <LoadingSkeleton lines={2} />
        ) : (
          <>
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">
              Good {getGreeting()}, {user?.customer_profile?.first_name || user?.email || "Operator"}
            </h1>
            <p className="mt-1 text-[var(--text-secondary)]">
              {bizList.length > 0
                ? `Managing ${bizList.length} business${bizList.length > 1 ? "es" : ""}`
                : "No businesses registered yet"}
            </p>
          </>
        )}
      </div>

      {/* Real metrics */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-live="polite">
        <Card>
          <p className="text-sm text-[var(--text-muted)]">Active Enquiries</p>
          {loading ? (
            <LoadingSkeleton lines={1} />
          ) : (
            <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">
              {activeEnquiries.length}
            </p>
          )}
        </Card>

        <Card>
          <p className="text-sm text-[var(--text-muted)]">Pending Quotes</p>
          {loading ? (
            <LoadingSkeleton lines={1} />
          ) : (
            <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">
              {pendingQuotes.length}
            </p>
          )}
        </Card>

        <Card>
          <p className="text-sm text-[var(--text-muted)]">Upcoming Bookings</p>
          {loading ? (
            <LoadingSkeleton lines={1} />
          ) : (
            <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">
              {upcomingBookings.length}
            </p>
          )}
        </Card>

        <Card>
          <p className="text-sm text-[var(--text-muted)]">Active Services</p>
          {loading ? (
            <LoadingSkeleton lines={1} />
          ) : (
            <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">
              {activeExecutions.length}
            </p>
          )}
        </Card>

        <Card>
          <p className="text-sm text-[var(--text-muted)]">Revenue (paid)</p>
          {loading || !summary ? (
            <LoadingSkeleton lines={1} />
          ) : (
            <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">
              {Number(summary.paid_amount).toLocaleString(undefined, {
                maximumFractionDigits: 2,
              })}
            </p>
          )}
        </Card>

        <Card>
          <p className="text-sm text-[var(--text-muted)]">Outstanding</p>
          {loading || !summary ? (
            <LoadingSkeleton lines={1} />
          ) : (
            <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">
              {Number(summary.outstanding_amount).toLocaleString(undefined, {
                maximumFractionDigits: 2,
              })}
            </p>
          )}
        </Card>
      </div>

      {/* NOT YET AVAILABLE — Business Brain Metrics */}
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
          Business Brain Insights
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <NotAvailableCard
            title="Conversion Rate"
            message="Not configured — requires Business Brain rules"
          />
          <NotAvailableCard
            title="Business Brain Uptime"
            message="Business Brain not yet configured"
          />
          <NotAvailableCard
            title="Avg. Response Time"
            message="No data available"
          />
        </div>
      </div>

      {/* NOT YET AVAILABLE — Performance */}
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
          Service Performance
        </h2>
        <Card>
          <div className="text-center py-8">
            <p className="text-[var(--text-muted)]">
              Connect your Business Brain to see performance data
            </p>
          </div>
        </Card>
      </div>

      {/* NOT YET AVAILABLE — AI-Human Handover */}
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
          AI-Human Handover
        </h2>
        <Card>
          <div className="text-center py-8">
            <p className="text-[var(--text-muted)]">
              No handover rules configured yet
            </p>
          </div>
        </Card>
      </div>

      {/* NOT YET AVAILABLE — Workflow Automation */}
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
          Workflow Automation
        </h2>
        <div className="space-y-3">
          {["Auto-qualify enquiries", "Auto-respond to common queries", "Escalate high-value leads"].map(
            (item) => (
              <Card key={item} padding="sm">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[var(--text-secondary)]">
                    {item}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[var(--text-muted)]">
                      Not yet configured
                    </span>
                    <div
                      className="h-5 w-9 rounded-full bg-[var(--bg-elevated)] border border-[var(--border-default)]"
                      role="switch"
                      aria-disabled="true"
                      aria-label={`${item} — not yet available`}
                    />
                  </div>
                </div>
              </Card>
            )
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-3">
          <a
            href="/business/enquiries"
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
          >
            View Enquiries
          </a>
          <a
            href="/business/services"
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
          >
            Manage Services
          </a>
          <a
            href="/business/payments"
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
          >
            Payments
          </a>
          <a
            href="/business/profile"
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
          >
            Edit Profile
          </a>
        </div>
      </div>

      {/* Recent activity — 3 most recent events */}
      <div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
          Recent Activity
        </h2>
        {recentItems.length === 0 ? (
          <Card>
            <div className="text-center py-8">
              <p className="text-[var(--text-muted)]">No activity yet.</p>
            </div>
          </Card>
        ) : (
          <div className="space-y-3">
            {recentItems.map((item) => (
              <Card key={`${item.type}-${item.id}`} padding="sm" hover>
                <a
                  href={
                    item.type === "enquiry"
                      ? `/business/${bizList[0]?.id}/enquiries/${item.id}`
                      : "/business/bookings"
                  }
                  className="flex items-center justify-between"
                >
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">
                      {item.label}
                    </p>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">{item.sub}</p>
                  </div>
                  <Badge variant={statusVariant(item.status)}>
                    {item.status.replace(/_/g, " ")}
                  </Badge>
                </a>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function NotAvailableCard({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <Card>
      <p className="text-sm text-[var(--text-muted)]">{title}</p>
      <p className="mt-1 text-sm text-[var(--text-secondary)] italic">
        {message}
      </p>
    </Card>
  );
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

function statusVariant(status: string): "info" | "warning" | "danger" | "muted" | "default" {
  switch (status.toLowerCase()) {
    case "submitted":
    case "received":
      return "info";
    case "in_review":
    case "needs_information":
    case "in_progress":
    case "requested":
    case "proposed":
      return "warning";
    case "cancelled":
    case "declined":
    case "expired":
    case "no_show":
      return "danger";
    case "draft":
      return "muted";
    default:
      return "default";
  }
}
