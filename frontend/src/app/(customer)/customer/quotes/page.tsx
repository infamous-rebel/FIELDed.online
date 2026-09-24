"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  bookings,
  quotes,
  type QuoteData,
} from "@/lib/api-client";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-500/10 text-gray-400",
  issued: "bg-blue-500/10 text-blue-400",
  accepted: "bg-green-500/10 text-green-400",
  declined: "bg-red-500/10 text-red-400",
  expired: "bg-yellow-500/10 text-yellow-400",
};

export default function CustomerQuotes() {
  const router = useRouter();
  const [quotesList, setQuotesList] = useState<QuoteData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [bookingQuoteId, setBookingQuoteId] = useState<string | null>(null);
  const [bookingAt, setBookingAt] = useState("");
  const [bookingNotes, setBookingNotes] = useState("");
  const [bookingLoading, setBookingLoading] = useState(false);

  useEffect(() => {
    loadQuotes();
  }, []);

  async function loadQuotes() {
    try {
      setLoading(true);
      const data = await quotes.listMine();
      setQuotesList(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load quotes");
    } finally {
      setLoading(false);
    }
  }

  async function handleAccept(quoteId: string) {
    try {
      setActionLoading(quoteId);
      await quotes.transitionMyQuote(quoteId, "accepted");
      await loadQuotes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept quote");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDecline(quoteId: string) {
    try {
      setActionLoading(quoteId);
      await quotes.transitionMyQuote(quoteId, "declined");
      await loadQuotes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to decline quote");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRequestBooking(quoteId: string) {
    if (!bookingAt) return;
    setBookingLoading(true);
    setError(null);
    try {
      await bookings.create({
        quote_id: quoteId,
        requested_at: new Date(bookingAt).toISOString(),
        notes: bookingNotes.trim() || undefined,
      });
      router.push("/customer/bookings");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to request booking");
      setBookingLoading(false);
    }
  }

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Quotes</h1>
        <p className="mt-2 text-[var(--text-secondary)]">Loading quotes...</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-[var(--text-primary)]">Quotes</h1>
      <p className="mt-2 text-[var(--text-secondary)]">
        Review and respond to quotes from businesses.
      </p>

      {error && (
        <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {quotesList.length === 0 ? (
        <div className="mt-8 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-12 text-center">
          <p className="text-[var(--text-muted)]">No quotes yet.</p>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Quotes will appear here when businesses respond to your enquiries.
          </p>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          {quotesList.map((quote) => (
            <div
              key={quote.id}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm text-[var(--text-muted)]">
                      {quote.reference}
                    </span>
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        STATUS_COLORS[quote.status] || "bg-gray-500/10 text-gray-400"
                      }`}
                    >
                      {quote.status}
                    </span>
                  </div>
                  <p className="mt-2 text-2xl font-bold text-[var(--text-primary)]">
                    {quote.currency} {parseFloat(quote.amount).toFixed(2)}
                  </p>
                  {quote.notes && (
                    <p className="mt-2 text-sm text-[var(--text-secondary)]">
                      {quote.notes}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    Created {new Date(quote.created_at).toLocaleDateString()}
                  </p>
                </div>

                {quote.status === "issued" && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleAccept(quote.id)}
                      disabled={actionLoading === quote.id}
                      className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                    >
                      Accept
                    </button>
                    <button
                      onClick={() => handleDecline(quote.id)}
                      disabled={actionLoading === quote.id}
                      className="rounded-lg border border-red-500/30 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                    >
                      Decline
                    </button>
                  </div>
                )}
                {quote.status === "accepted" && bookingQuoteId !== quote.id && (
                  <button
                    onClick={() => {
                      setBookingQuoteId(quote.id);
                      setBookingAt("");
                      setBookingNotes("");
                    }}
                    className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-hover)]"
                  >
                    Request Booking
                  </button>
                )}
              </div>

              {quote.pricing_evidence && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
                    Pricing details
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded bg-[var(--bg-elevated)] p-3 text-xs text-[var(--text-muted)]">
                    {JSON.stringify(quote.pricing_evidence, null, 2)}
                  </pre>
                </details>
              )}

              {bookingQuoteId === quote.id && (
                <div className="mt-4 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] p-4">
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                    Request a booking
                  </h3>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    Pick when you need the service. The business will confirm based on
                    availability.
                  </p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div>
                      <label
                        htmlFor={`booking-at-${quote.id}`}
                        className="block text-xs font-medium text-[var(--text-secondary)]"
                      >
                        Date &amp; time
                      </label>
                      <input
                        id={`booking-at-${quote.id}`}
                        type="datetime-local"
                        value={bookingAt}
                        onChange={(e) => setBookingAt(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                        required
                      />
                    </div>
                    <div>
                      <label
                        htmlFor={`booking-notes-${quote.id}`}
                        className="block text-xs font-medium text-[var(--text-secondary)]"
                      >
                        Notes (optional)
                      </label>
                      <input
                        id={`booking-notes-${quote.id}`}
                        type="text"
                        value={bookingNotes}
                        onChange={(e) => setBookingNotes(e.target.value)}
                        placeholder="e.g. Access via rear door"
                        className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                      />
                    </div>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => handleRequestBooking(quote.id)}
                      disabled={!bookingAt || bookingLoading}
                      className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-50"
                    >
                      {bookingLoading ? "Requesting..." : "Confirm Booking Request"}
                    </button>
                    <button
                      onClick={() => setBookingQuoteId(null)}
                      disabled={bookingLoading}
                      className="rounded-lg px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
