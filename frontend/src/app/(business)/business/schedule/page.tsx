"use client";

import { useEffect, useState } from "react";
import {
  bookings,
  businesses,
  serviceExecutions,
  type BookingData,
  type BusinessSummary,
  type ServiceExecutionData,
  FieldedApiError,
} from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge, statusBadgeVariant } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateFull(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

type TabValue = "upcoming" | "active" | "completed";

const TABS: { label: string; value: TabValue }[] = [
  { label: "Upcoming", value: "upcoming" },
  { label: "Active", value: "active" },
  { label: "Completed", value: "completed" },
];

const UPCOMING_STATUSES = new Set(["requested", "proposed", "accepted", "confirmed"]);
const ACTIVE_STATUSES = new Set(["in_progress", "scheduled"]);
const COMPLETED_STATUSES = new Set(["completed", "cancelled", "no_show", "declined"]);

const BUSINESS_TRANSITIONS: Record<string, { target: string; label: string; style: "success" | "danger" | "primary" }[]> = {
  requested: [
    { target: "proposed", label: "Propose", style: "primary" },
    { target: "declined", label: "Decline", style: "danger" },
  ],
  proposed: [
    { target: "confirmed", label: "Confirm", style: "success" },
    { target: "declined", label: "Decline", style: "danger" },
  ],
  accepted: [
    { target: "confirmed", label: "Confirm", style: "success" },
  ],
  confirmed: [
    // Must go through service execution: Start Work → execution created → Complete execution
    { target: "in_progress", label: "Start Work", style: "primary" },
  ],
  in_progress: [
    { target: "completed", label: "Complete", style: "success" },
  ],
};

export default function BusinessSchedulePage() {
  const [business, setBusiness] = useState<BusinessSummary | null>(null);
  const [bookingList, setBookingList] = useState<BookingData[]>([]);
  const [executionList, setExecutionList] = useState<ServiceExecutionData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabValue>("upcoming");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const bizList = await businesses.list();
        if (bizList.length === 0) {
          setError("No business found. Create one from Settings.");
          setLoading(false);
          return;
        }
        const biz = bizList[0];
        setBusiness(biz);

        const [bkData, exData] = await Promise.all([
          bookings.listForBusiness(biz.id).catch(() => [] as BookingData[]),
          serviceExecutions.listForBusiness(biz.id).catch(() => [] as ServiceExecutionData[]),
        ]);
        setBookingList(bkData);
        setExecutionList(exData);
      } catch (err) {
        setError(err instanceof FieldedApiError ? err.error.message : "Failed to load schedule");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleTransition(bookingId: string, targetStatus: string) {
    if (!business) return;
    try {
      setActionLoading(`${bookingId}:${targetStatus}`);
      await bookings.transitionBusiness(business.id, bookingId, targetStatus);
      const data = await bookings.listForBusiness(business.id);
      setBookingList(data);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to update");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleStartWork(bookingId: string) {
    if (!business) return;
    try {
      setActionLoading(`${bookingId}:start`);
      await serviceExecutions.create(business.id, bookingId);
      const [bkData, exData] = await Promise.all([
        bookings.listForBusiness(business.id).catch(() => [] as BookingData[]),
        serviceExecutions.listForBusiness(business.id).catch(() => [] as ServiceExecutionData[]),
      ]);
      setBookingList(bkData);
      setExecutionList(exData);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to start work");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleCompleteExecution(executionId: string) {
    if (!business) return;
    try {
      setActionLoading(`${executionId}:complete`);
      await serviceExecutions.complete(business.id, executionId);
      const exData = await serviceExecutions.listForBusiness(business.id);
      setExecutionList(exData);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to complete");
    } finally {
      setActionLoading(null);
    }
  }

  // Categorize bookings
  const upcomingBookings = bookingList.filter((b) => UPCOMING_STATUSES.has(b.status));
  const activeBookings = bookingList.filter((b) => ACTIVE_STATUSES.has(b.status));
  const completedBookings = bookingList.filter((b) => COMPLETED_STATUSES.has(b.status));

  // Active executions
  const activeExecutions = executionList.filter((e) => ["scheduled", "in_progress"].includes(e.status));
  const completedExecutions = executionList.filter((e) => e.status === "completed");

  const tabCounts = {
    upcoming: upcomingBookings.length,
    active: activeBookings.length + activeExecutions.length,
    completed: completedBookings.length + completedExecutions.length,
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Schedule</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Manage bookings, track work in progress, and complete services.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]" role="alert">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-[var(--border-subtle)]">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === tab.value
                ? "text-[var(--accent)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            }`}
          >
            {tab.label}
            {tabCounts[tab.value] > 0 && (
              <span className={`ml-1.5 inline-flex items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                activeTab === tab.value
                  ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                  : "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
              }`}>
                {tabCounts[tab.value]}
              </span>
            )}
            {activeTab === tab.value && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--accent)] rounded-full" />
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <LoadingSkeleton variant="list" lines={4} />
      ) : activeTab === "upcoming" ? (
        upcomingBookings.length === 0 ? (
          <EmptyState
            title="No upcoming bookings"
            description="Bookings will appear here when customers accept quotes and request a booking."
          />
        ) : (
          <div className="space-y-3">
            {upcomingBookings.map((booking) => {
              const transitions = BUSINESS_TRANSITIONS[booking.status] || [];
              return (
                <Card key={booking.id} padding="sm">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <p className="text-xs font-mono text-[var(--text-muted)]">{booking.reference}</p>
                        <Badge variant={statusBadgeVariant(booking.status)}>{formatStatus(booking.status)}</Badge>
                      </div>
                      <p className="mt-2 text-sm text-[var(--text-secondary)]">
                        Requested for <span className="font-medium text-[var(--text-primary)]">{formatDate(booking.requested_at)}</span>
                      </p>
                      {booking.notes && (
                        <p className="mt-1 text-sm text-[var(--text-muted)]">{booking.notes}</p>
                      )}
                    </div>
                    {transitions.length > 0 && (
                      <div className="flex gap-2 flex-shrink-0">
                        {transitions.map((t) => (
                          <button
                            key={t.target}
                            onClick={() => handleTransition(booking.id, t.target)}
                            disabled={actionLoading === `${booking.id}:${t.target}`}
                            className={`rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50 transition-colors ${
                              t.style === "success"
                                ? "bg-emerald-600 text-white hover:bg-emerald-700"
                                : t.style === "danger"
                                  ? "border border-red-500/30 text-red-400 hover:bg-red-500/10"
                                  : "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]"
                            }`}
                          >
                            {t.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )
      ) : activeTab === "active" ? (
        activeBookings.length === 0 && activeExecutions.length === 0 ? (
          <EmptyState
            title="Nothing active"
            description="Active bookings and work in progress will appear here."
          />
        ) : (
          <div className="space-y-3">
            {/* Active executions first */}
            {activeExecutions.map((exec) => (
              <Card key={exec.id} padding="sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-3">
                      <p className="text-xs font-mono text-[var(--text-muted)]">{exec.id.slice(0, 8)}</p>
                      <Badge variant={statusBadgeVariant(exec.status)}>{formatStatus(exec.status)}</Badge>
                      <span className="rounded-full bg-[var(--accent)]/10 px-2 py-0.5 text-[10px] font-medium text-[var(--accent)]">
                        Work in Progress
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-[var(--text-secondary)]">
                      Started {formatDateFull(exec.started_at || exec.created_at)}
                    </p>
                    {exec.notes && (
                      <p className="mt-1 text-sm text-[var(--text-muted)]">{exec.notes}</p>
                    )}
                  </div>
                  <button
                    onClick={() => handleCompleteExecution(exec.id)}
                    disabled={actionLoading === `${exec.id}:complete`}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                  >
                    Mark Complete
                  </button>
                </div>
              </Card>
            ))}
            {/* Active bookings without execution */}
            {activeBookings.map((booking) => (
              <Card key={booking.id} padding="sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-3">
                      <p className="text-xs font-mono text-[var(--text-muted)]">{booking.reference}</p>
                      <Badge variant={statusBadgeVariant(booking.status)}>{formatStatus(booking.status)}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-[var(--text-secondary)]">
                      {booking.status === "confirmed" ? "Ready to start" : "In progress"} — requested for{" "}
                      <span className="font-medium text-[var(--text-primary)]">{formatDate(booking.requested_at)}</span>
                    </p>
                  </div>
                  {booking.status === "confirmed" && (
                    <button
                      onClick={() => handleStartWork(booking.id)}
                      disabled={actionLoading === `${booking.id}:start`}
                      className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors"
                    >
                      Start Work
                    </button>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )
      ) : (
        /* Completed tab */
        completedBookings.length === 0 && completedExecutions.length === 0 ? (
          <EmptyState
            title="No completed work"
            description="Completed services and cancelled bookings will appear here."
          />
        ) : (
          <div className="space-y-3">
            {[...completedExecutions, ...completedBookings]
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((item) => {
                const isExecution = "booking_id" in item;
                return (
                  <Card key={item.id} padding="sm">
                    <div className="flex items-center gap-3">
                      <p className="text-xs font-mono text-[var(--text-muted)]">
                        {isExecution ? (item as ServiceExecutionData).id.slice(0, 8) : (item as BookingData).reference}
                      </p>
                      <Badge variant={statusBadgeVariant(item.status)}>{formatStatus(item.status)}</Badge>
                      <span className="text-xs text-[var(--text-muted)]">
                        {isExecution ? "Service" : "Booking"} — {formatDateFull(item.created_at)}
                      </span>
                    </div>
                  </Card>
                );
              })}
          </div>
        )
      )}
    </div>
  );
}
