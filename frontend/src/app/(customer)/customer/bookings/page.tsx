"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  bookings,
  type BookingData,
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

export default function CustomerBookings() {
  const router = useRouter();
  const [bookingList, setBookingList] = useState<BookingData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState("all");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    loadBookings();
  }, []);

  async function loadBookings() {
    try {
      setLoading(true);
      const data = await bookings.listMine();
      setBookingList(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load bookings"
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel(bookingId: string) {
    try {
      setActionLoading(bookingId);
      await bookings.cancelMyBooking(bookingId);
      await loadBookings();
    } catch (err) {
      setError(
        err instanceof FieldedApiError
          ? err.error.message
          : "Failed to cancel booking"
      );
    } finally {
      setActionLoading(null);
    }
  }

  async function handlePay(bookingId: string) {
    try {
      setActionLoading(bookingId);
      await bookings.payMyBooking(bookingId, "card");
      router.push("/customer/payments");
    } catch (err) {
      setError(
        err instanceof FieldedApiError
          ? err.error.message
          : "Failed to process payment"
      );
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
          Your service bookings and their status.
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
          description="Bookings will appear here after you accept a quote and request a booking."
        />
      ) : (
        <div className="space-y-3">
          {filteredList.map((booking) => (
            <Card key={booking.id} padding="sm" hover>
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

                <div className="flex flex-col items-end gap-2 flex-shrink-0">
                  {booking.status === "completed" && (
                    <button
                      onClick={() => handlePay(booking.id)}
                      disabled={actionLoading === booking.id}
                      className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
                    >
                      {actionLoading === booking.id ? "Paying…" : "Pay Now"}
                    </button>
                  )}
                  {(booking.status === "requested" ||
                    booking.status === "proposed" ||
                    booking.status === "accepted" ||
                    booking.status === "confirmed") && (
                    <button
                      onClick={() => handleCancel(booking.id)}
                      disabled={actionLoading === booking.id}
                      className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  )}
                </div>
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
          ))}
        </div>
      )}
    </div>
  );
}
