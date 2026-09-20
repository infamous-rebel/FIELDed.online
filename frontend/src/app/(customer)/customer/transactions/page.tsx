"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  auth,
  enquiries,
  quotes,
  bookings,
  serviceExecutions,
  invoices,
  payments,
  reviews,
  type UserResponse,
  type EnquiryData,
  type QuoteData,
  type BookingData,
  type ServiceExecutionData,
  type InvoiceData,
  type PaymentData,
  type ReviewData,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";

/** Correlated row: one per enquiry with all linked entities */
interface TransactionRow {
  enquiry: EnquiryData;
  quote: QuoteData | null;
  booking: BookingData | null;
  execution: ServiceExecutionData | null;
  invoice: InvoiceData | null;
  payment: PaymentData | null;
  review: ReviewData | null;
  reviewEligible: boolean;
}

function statusBadge(status: string): string {
  const colors: Record<string, string> = {
    draft: "bg-gray-500/20 text-gray-300",
    submitted: "bg-blue-500/20 text-blue-300",
    received: "bg-blue-500/20 text-blue-300",
    in_review: "bg-blue-500/20 text-blue-300",
    quoted: "bg-amber-500/20 text-amber-300",
    customer_accepted: "bg-emerald-500/20 text-emerald-300",
    booking_proposed: "bg-amber-500/20 text-amber-300",
    booked: "bg-emerald-500/20 text-emerald-300",
    in_progress: "bg-amber-500/20 text-amber-300",
    completed: "bg-emerald-500/20 text-emerald-300",
    cancelled: "bg-gray-500/20 text-gray-400",
    declined: "bg-red-500/20 text-red-300",
    requested: "bg-blue-500/20 text-blue-300",
    proposed: "bg-amber-500/20 text-amber-300",
    accepted: "bg-emerald-500/20 text-emerald-300",
    confirmed: "bg-emerald-500/20 text-emerald-300",
    scheduled: "bg-blue-500/20 text-blue-300",
    pending: "bg-amber-500/20 text-amber-300",
    processing: "bg-blue-500/20 text-blue-300",
    succeeded: "bg-emerald-500/20 text-emerald-300",
    outstanding: "bg-amber-500/20 text-amber-300",
    paid: "bg-emerald-500/20 text-emerald-300",
    no_show: "bg-red-500/20 text-red-300",
    visible: "bg-emerald-500/20 text-emerald-300",
  };
  return colors[status] || "bg-gray-500/20 text-gray-300";
}

function reviewStatus(row: TransactionRow): { label: string; cls: string } {
  if (row.review) {
    return { label: "Submitted", cls: "text-emerald-400" };
  }
  if (row.reviewEligible) {
    return { label: "Eligible", cls: "text-amber-400" };
  }
  return { label: "Not yet", cls: "text-[var(--text-muted)]" };
}

export default function TransactionHistoryPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [rows, setRows] = useState<TransactionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [reviewFormFor, setReviewFormFor] = useState<string | null>(null);
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewTitle, setReviewTitle] = useState("");
  const [reviewBody, setReviewBody] = useState("");
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    async function load() {
      try {
        const [u, enqs, qts, bks, execs, invs, pays, revs] = await Promise.all([
          auth.me(),
          enquiries.listMine().catch(() => [] as EnquiryData[]),
          quotes.listMine().catch(() => [] as QuoteData[]),
          bookings.listMine().catch(() => [] as BookingData[]),
          serviceExecutions.listMy().catch(() => [] as ServiceExecutionData[]),
          invoices.listMy().catch(() => [] as InvoiceData[]),
          payments.listMine().catch(() => [] as PaymentData[]),
          reviews.listMine().catch(() => [] as ReviewData[]),
        ]);
        setUser(u);

        // Correlate by enquiry_id / booking_id / service_execution_id
        const correlated: TransactionRow[] = enqs.map((enq) => {
          const quote = qts.find((q) => q.enquiry_id === enq.id) ?? null;
          const booking = bks.find((b) => b.enquiry_id === enq.id) ?? null;
          const execution = booking
            ? execs.find((e) => e.booking_id === booking.id) ?? null
            : null;
          const invoice = execution
            ? invs.find((i) => i.service_execution_id === execution.id) ?? null
            : null;
          const payment = invoice
            ? pays.find((p) => p.invoice_id === invoice.id) ?? null
            : null;
          const review = execution
            ? revs.find((r) => r.service_execution_id === execution.id) ?? null
            : null;

          // Eligible: execution completed, booking not cancelled, no existing review
          const reviewEligible =
            !!execution &&
            execution.status === "completed" &&
            !!booking &&
            booking.status !== "cancelled" &&
            !review;

          return {
            enquiry: enq,
            quote,
            booking,
            execution,
            invoice,
            payment,
            review,
            reviewEligible,
          };
        });

        // Sort by enquiry created_at descending
        correlated.sort(
          (a, b) =>
            new Date(b.enquiry.created_at).getTime() -
            new Date(a.enquiry.created_at).getTime()
        );

        setRows(correlated);
      } catch (err) {
        if (err instanceof FieldedApiError && err.status === 401) {
          router.push("/login");
        }
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [router]);

  const sortedRows = useMemo(() => rows, [rows]);

  async function handleReviewSubmit(execution: ServiceExecutionData) {
    setReviewSubmitting(true);
    setReviewError(null);
    try {
      await reviews.create({
        service_execution_id: execution.id,
        rating: reviewRating,
        title: reviewTitle || null,
        body: reviewBody || null,
      });
      // Refresh rows to reflect the submitted review
      const revs = await reviews.listMine().catch(() => [] as ReviewData[]);
      setRows((prev) =>
        prev.map((row) => {
          if (row.execution?.id === execution.id) {
            const review = revs.find((r) => r.service_execution_id === execution.id) ?? null;
            return { ...row, review, reviewEligible: false };
          }
          return row;
        })
      );
      setReviewFormFor(null);
      setReviewTitle("");
      setReviewBody("");
      setReviewRating(5);
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setReviewError(err.message || "Failed to submit review");
      } else {
        setReviewError("Failed to submit review");
      }
    } finally {
      setReviewSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-1/3 rounded bg-[var(--bg-elevated)]" />
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-xl bg-[var(--bg-elevated)]" />
          ))}
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Transaction History
        </h1>
        <Link
          href="/customer/dashboard"
          className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          &larr; Back to Dashboard
        </Link>
      </div>

      {sortedRows.length === 0 ? (
        <div className="mt-12 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-12 text-center">
          <p className="text-[var(--text-muted)]">No transactions yet.</p>
          <Link
            href="/network"
            className="mt-4 inline-block rounded-lg bg-[var(--accent)] px-6 py-2.5 text-sm font-semibold text-white hover:bg-[var(--accent-hover)]"
          >
            Browse Network
          </Link>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          {sortedRows.map((row) => {
            const rev = reviewStatus(row);
            return (
              <div
                key={row.enquiry.id}
                className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5"
              >
                {/* Top row: enquiry reference + service offer */}
                <div className="flex flex-wrap items-center gap-3">
                  <Link
                    href={`/customer/enquiries/${row.enquiry.id}`}
                    className="text-sm font-semibold text-[var(--text-primary)] hover:underline"
                  >
                    {row.enquiry.subject || `Enquiry ${row.enquiry.reference}`}
                  </Link>
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${statusBadge(row.enquiry.status)}`}
                  >
                    {row.enquiry.status.replace(/_/g, " ")}
                  </span>
                  <span className="ml-auto text-xs text-[var(--text-muted)]">
                    {new Date(row.enquiry.created_at).toLocaleDateString()}
                  </span>
                </div>

                {/* Chain row */}
                <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs">
                  {/* Quote */}
                  <div>
                    <span className="text-[var(--text-muted)]">Quote: </span>
                    {row.quote ? (
                      <span className="text-[var(--text-primary)]">
                        {row.quote.currency} {row.quote.amount}
                      </span>
                    ) : (
                      <span className="text-[var(--text-muted)]">&mdash;</span>
                    )}
                  </div>

                  {/* Booking */}
                  <div>
                    <span className="text-[var(--text-muted)]">Booking: </span>
                    {row.booking ? (
                      <span
                        className={`capitalize ${statusBadge(row.booking.status) !== "" ? "text-[var(--text-primary)]" : ""}`}
                      >
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${statusBadge(row.booking.status)}`}
                        >
                          {row.booking.status.replace(/_/g, " ")}
                        </span>
                        <span className="ml-1 text-[var(--text-muted)]">
                          {new Date(row.booking.requested_at).toLocaleDateString()}
                        </span>
                      </span>
                    ) : (
                      <span className="text-[var(--text-muted)]">&mdash;</span>
                    )}
                  </div>

                  {/* Payment */}
                  <div>
                    <span className="text-[var(--text-muted)]">Payment: </span>
                    {row.invoice ? (
                      <span>
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${statusBadge(row.invoice.payment_status)}`}
                        >
                          {row.invoice.payment_status.replace(/_/g, " ")}
                        </span>
                        <span className="ml-1 text-[var(--text-primary)]">
                          {row.invoice.currency} {row.invoice.total}
                        </span>
                      </span>
                    ) : row.payment ? (
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${statusBadge(row.payment.status)}`}
                      >
                        {row.payment.status.replace(/_/g, " ")}
                      </span>
                    ) : (
                      <span className="text-[var(--text-muted)]">&mdash;</span>
                    )}
                  </div>

                  {/* Service execution */}
                  <div>
                    <span className="text-[var(--text-muted)]">Service: </span>
                    {row.execution ? (
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${statusBadge(row.execution.status)}`}
                      >
                        {row.execution.status.replace(/_/g, " ")}
                      </span>
                    ) : (
                      <span className="text-[var(--text-muted)]">&mdash;</span>
                    )}
                  </div>

                  {/* Review */}
                  <div>
                    <span className="text-[var(--text-muted)]">Review: </span>
                    <span className={`font-medium ${rev.cls}`}>
                      {rev.label}
                    </span>
                    {row.reviewEligible && row.execution && (
                      <button
                        onClick={() => {
                          setReviewFormFor(
                            reviewFormFor === row.execution!.id ? null : row.execution!.id
                          );
                          setReviewError(null);
                        }}
                        className="ml-2 text-xs font-medium text-[var(--accent)] hover:underline"
                      >
                        Leave a review
                      </button>
                    )}
                  </div>
                </div>

                {/* Review submission form (inline, when eligible) */}
                {reviewFormFor === row.execution?.id && row.execution && (
                  <div className="mt-4 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-[var(--text-primary)]">Rating:</span>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <button
                          key={n}
                          onClick={() => setReviewRating(n)}
                          className={`text-xl leading-none ${n <= reviewRating ? "text-amber-400" : "text-[var(--text-muted)]"}`}
                          aria-label={`${n} star${n > 1 ? "s" : ""}`}
                        >
                          {n <= reviewRating ? "\u2605" : "\u2606"}
                        </button>
                      ))}
                    </div>
                    <input
                      type="text"
                      value={reviewTitle}
                      onChange={(e) => setReviewTitle(e.target.value)}
                      placeholder="Title (optional)"
                      maxLength={200}
                      className="mt-3 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                    />
                    <textarea
                      value={reviewBody}
                      onChange={(e) => setReviewBody(e.target.value)}
                      placeholder="Share your experience (optional)"
                      rows={3}
                      className="mt-2 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                    />
                    {reviewError && (
                      <p className="mt-2 text-xs text-[var(--danger)]">{reviewError}</p>
                    )}
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => handleReviewSubmit(row.execution!)}
                        disabled={reviewSubmitting}
                        className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--accent-hover)] disabled:opacity-50"
                      >
                        {reviewSubmitting ? "Submitting…" : "Submit Review"}
                      </button>
                      <button
                        onClick={() => setReviewFormFor(null)}
                        className="rounded-lg border border-[var(--border-default)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
