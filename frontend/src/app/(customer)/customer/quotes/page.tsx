"use client";

import { useEffect, useState } from "react";
import { quotes, type QuoteData } from "@/lib/api-client";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-500/10 text-gray-400",
  issued: "bg-blue-500/10 text-blue-400",
  accepted: "bg-green-500/10 text-green-400",
  declined: "bg-red-500/10 text-red-400",
  expired: "bg-yellow-500/10 text-yellow-400",
};

export default function CustomerQuotes() {
  const [quotesList, setQuotesList] = useState<QuoteData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

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
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
