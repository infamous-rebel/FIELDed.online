"use client";

import { useEffect, useState } from "react";
import {
  bookings,
  businesses,
  type BookingData,
  type BusinessSummary,
  FieldedApiError,
} from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge, statusBadgeVariant } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

function formatStatus(status: string): string {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const FILTER_TABS = [
  { label: "All", value: "all" },
  { label: "Requested", value: "requested" },
  { label: "Confirmed", value: "confirmed" },
  { label: "In Progress", value: "in_progress" },
  { label: "Completed", value: "completed" },
  { label: "Cancelled", value: "cancelled" },
];

/** Valid next transitions per booking status for business actors */
const BUSINESS_TRANSITIONS: Record<string, { target: string; label: string; variant: string }[]> = {
  requested: [
    { target: "proposed", label: "Propose", variant: "accent" },
    { target: "accepted", label: "Accept", variant: "success" },
    { target: "declined", label: "Decline", variant: "danger" },
  ],
  proposed: [
    { target: "accepted", label: "Accept", variant: "success" },
    { target: "declined", label: "Decline", variant: "danger" },
  ],
  accepted: [
    { target: "confirmed", label: "Confirm", variant: "success" },
  ],
  confirmed: [
    { target: "in_progress", label: "Start", variant: "accent" },
    { target: "cancelled", label: "Cancel", variant: "danger" },
  ],
  in_progress: [
    { target: "completed", label: "Complete", variant: "success" },
    { target: "no_show", label: "No Show", variant: "danger" },
  ],
};

export default function BusinessBookingsPage() {
  const [business, setBusiness] = useState<BusinessSummary | null>(null);
  const [bookingList, setBookingList] = useState<BookingData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState("all");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const bizList = await businesses.list();
        if (bizList.length === 0) {
          setError("No business found. Create one first.");
          setLoading(false);
          return;
        }
        const biz = bizList[0];
        setBusiness(biz);

        const data = await bookings.listForBusiness(biz.id);
        setBookingList(data);
      } catch (err) {
        if (err instanceof FieldedApiError) {
          setError(err.error.message);
        } else {
          setError("Failed to load bookings");
        }
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
      setError(
        err instanceof FieldedApiError
          ? err.error.message
          : "Failed to transition booking"
      );
    } finally {
      setActionLoading(null);
    }
  }

  const filteredList =
    activeFilter === "all"
      ? bookingList
      : bookingList.filter((b) => b.status === activeFilter);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Bookings
        </h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Manage customer bookings and service scheduling.
        </p>
      </div>

      {error && (
        <div
          className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]"
          role="alert"
        >
          {error}
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-1 overflow-x-auto border-b border-[var(--border-subtle)] pb-px">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveFilter(tab.value)}
            className={`whitespace-nowrap rounded-t-lg px-4 py-2 text-sm font-medium transition-colors ${
              activeFilter === tab.value
                ? "border-b-2 border-[var(--accent)] text-[var(--accent)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <LoadingSkeleton variant="list" lines={4} />
      ) : filteredList.length === 0 ? (
        <EmptyState
          title={
            activeFilter === "all"
              ? "No bookings yet"
              : `No ${formatStatus(activeFilter).toLowerCase()} bookings`
          }
          description="Customer bookings will appear here after they accept quotes and request a booking."
        />
      ) : (
        <div className="space-y-3">
          {filteredList.map((booking) => {
            const transitions = BUSINESS_TRANSITIONS[booking.status] || [];
            return (
              <Card key={booking.id} padding="sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-3">
                      <p className="text-xs font-mono text-[var(--text-muted)]">
                        {booking.reference}
                      </p>
                      <Badge variant={statusBadgeVariant(booking.status)}>
                        {formatStatus(booking.status)}
                      </Badge>
                    </div>
                    <p className="mt-2 text-sm text-[var(--text-secondary)]">
                      Requested for{" "}
                      <span className="font-medium text-[var(--text-primary)]">
                        {formatDate(booking.requested_at)}
                      </span>
                    </p>
                    {booking.notes && (
                      <p className="mt-1 text-sm text-[var(--text-muted)]">
                        {booking.notes}
                      </p>
                    )}
                    <p className="mt-1 text-xs text-[var(--text-muted)]">
                      Created {formatDate(booking.created_at)}
                    </p>
                  </div>

                  {transitions.length > 0 && (
                    <div className="flex gap-2 flex-shrink-0">
                      {transitions.map((t) => (
                        <button
                          key={t.target}
                          onClick={() =>
                            handleTransition(booking.id, t.target)
                          }
                          disabled={
                            actionLoading === `${booking.id}:${t.target}`
                          }
                          className={`rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
                            t.variant === "success"
                              ? "bg-green-600 text-white hover:bg-green-700"
                              : t.variant === "danger"
                                ? "border border-red-500/30 text-red-400 hover:bg-red-500/10"
                                : "bg-[var(--accent)] text-white hover:opacity-90"
                          }`}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {booking.decision_evidence && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
                      Decision evidence
                    </summary>
                    <pre className="mt-2 overflow-x-auto rounded bg-[var(--bg-elevated)] p-3 text-xs text-[var(--text-muted)]">
                      {JSON.stringify(booking.decision_evidence, null, 2)}
                    </pre>
                  </details>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
