"use client";

import { useEffect, useState } from "react";
import {
  bookings,
  invoices,
  payments,
  reviews,
  type BookingData,
  type InvoiceData,
  type PaymentData,
  type ReviewData,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";
import { Card } from "@/components/ui/card";
import { Badge, statusBadgeVariant } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatAmount(amount: string | number, currency: string = "USD"): string {
  const num = typeof amount === "string" ? parseFloat(amount) : amount;
  return num.toLocaleString(undefined, {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

type TabValue = "services" | "invoices" | "payments" | "reviews";

const TABS: { label: string; value: TabValue }[] = [
  { label: "Services", value: "services" },
  { label: "Invoices", value: "invoices" },
  { label: "Payments", value: "payments" },
  { label: "Reviews", value: "reviews" },
];

export default function CustomerHistoryPage() {
  const [bookingList, setBookingList] = useState<BookingData[]>([]);
  const [invoiceList, setInvoiceList] = useState<InvoiceData[]>([]);
  const [paymentList, setPaymentList] = useState<PaymentData[]>([]);
  const [reviewList, setReviewList] = useState<ReviewData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabValue>("services");

  useEffect(() => {
    if (!isAuthenticated()) return;

    async function load() {
      try {
        const [bkData, invData, payData, revData] = await Promise.all([
          bookings.listMine().catch(() => [] as BookingData[]),
          invoices.listMy().catch(() => [] as InvoiceData[]),
          payments.listMine().catch(() => [] as PaymentData[]),
          reviews.listMine().catch(() => [] as ReviewData[]),
        ]);
        setBookingList(bkData);
        setInvoiceList(invData);
        setPaymentList(payData);
        setReviewList(revData);
      } catch {
        setError("Failed to load history");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Completed/cancelled bookings are "history"
  const completedBookings = bookingList.filter((b) =>
    ["completed", "cancelled", "no_show"].includes(b.status)
  );
  const allBookings = bookingList;

  const tabCounts = {
    services: allBookings.length,
    invoices: invoiceList.length,
    payments: paymentList.length,
    reviews: reviewList.length,
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">History</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Your completed services, invoices, payments, and reviews.
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
      ) : activeTab === "services" ? (
        allBookings.length === 0 ? (
          <EmptyState
            title="No service history"
            description="Your bookings will appear here as they progress through completion."
          />
        ) : (
          <div className="space-y-3">
            {allBookings
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((booking) => (
                <Card key={booking.id} padding="sm">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <p className="text-xs font-mono text-[var(--text-muted)]">{booking.reference}</p>
                        <Badge variant={statusBadgeVariant(booking.status)}>{formatStatus(booking.status)}</Badge>
                      </div>
                      <p className="mt-2 text-sm text-[var(--text-secondary)]">
                        Requested for <span className="font-medium text-[var(--text-primary)]">{formatDate(booking.requested_at)}</span>
                      </p>
                      {booking.notes && (
                        <p className="mt-1 text-xs text-[var(--text-muted)]">{booking.notes}</p>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
          </div>
        )
      ) : activeTab === "invoices" ? (
        invoiceList.length === 0 ? (
          <EmptyState
            title="No invoices"
            description="Invoices are generated when services are completed."
          />
        ) : (
          <div className="space-y-3">
            {invoiceList
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((invoice) => (
                <Card key={invoice.id} padding="sm">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <p className="text-xs font-mono text-[var(--text-muted)]">{invoice.invoice_number}</p>
                        <Badge variant={statusBadgeVariant(invoice.payment_status)}>{formatStatus(invoice.payment_status)}</Badge>
                      </div>
                      <p className="mt-2 text-sm text-[var(--text-secondary)]">
                        <span className="font-semibold text-[var(--text-primary)]">{formatAmount(invoice.total, invoice.currency)}</span>
                        <span className="ml-2 text-[var(--text-muted)]">Issued {formatDate(invoice.issue_date)}</span>
                      </p>
                    </div>
                  </div>
                </Card>
              ))}
          </div>
        )
      ) : activeTab === "payments" ? (
        paymentList.length === 0 ? (
          <EmptyState
            title="No payments"
            description="Your payment history will appear here."
          />
        ) : (
          <div className="space-y-3">
            {paymentList
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((payment) => (
                <Card key={payment.id} padding="sm">
                  <div className="flex items-center gap-3">
                    <p className="text-xs font-mono text-[var(--text-muted)]">{payment.id.slice(0, 8)}</p>
                    <Badge variant={statusBadgeVariant(payment.status)}>{formatStatus(payment.status)}</Badge>
                    <span className="text-sm font-semibold text-[var(--text-primary)]">{formatAmount(payment.amount, payment.currency)}</span>
                    <span className="text-xs text-[var(--text-muted)]">{payment.payment_method}</span>
                    {payment.paid_at && (
                      <span className="text-xs text-[var(--text-muted)]">{formatDate(payment.paid_at)}</span>
                    )}
                  </div>
                </Card>
              ))}
          </div>
        )
      ) : (
        reviewList.length === 0 ? (
          <EmptyState
            title="No reviews yet"
            description="After completed services, you can leave reviews for businesses."
          />
        ) : (
          <div className="space-y-3">
            {reviewList
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((review) => (
                <Card key={review.id} padding="sm">
                  <div className="flex items-start gap-3">
                    <div className="flex items-center gap-0.5 text-amber-400">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <span key={i} className={i < review.rating ? "opacity-100" : "opacity-30"}>&#9733;</span>
                      ))}
                    </div>
                    <div className="min-w-0 flex-1">
                      {review.title && <p className="text-sm font-medium text-[var(--text-primary)]">{review.title}</p>}
                      <p className="text-sm text-[var(--text-secondary)]">{review.body || "No comment"}</p>
                      <p className="mt-1 text-xs text-[var(--text-muted)]">Posted {formatDate(review.created_at)}</p>
                    </div>
                  </div>
                </Card>
              ))}
          </div>
        )
      )}
    </div>
  );
}
