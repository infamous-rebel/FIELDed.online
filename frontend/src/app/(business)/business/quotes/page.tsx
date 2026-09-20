"use client";

import { useEffect, useState } from "react";
import {
  quotes,
  businesses,
  type QuoteData,
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
  { label: "Draft", value: "draft" },
  { label: "Issued", value: "issued" },
  { label: "Accepted", value: "accepted" },
  { label: "Declined", value: "declined" },
  { label: "Expired", value: "expired" },
];

export default function BusinessQuotesPage() {
  const [business, setBusiness] = useState<BusinessSummary | null>(null);
  const [quoteList, setQuoteList] = useState<QuoteData[]>([]);
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

        const data = await quotes.listForBusiness(biz.id);
        setQuoteList(data);
      } catch (err) {
        if (err instanceof FieldedApiError) {
          setError(err.error.message);
        } else {
          setError("Failed to load quotes");
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleIssue(quoteId: string) {
    if (!business) return;
    try {
      setActionLoading(quoteId);
      await quotes.transitionBusiness(business.id, quoteId, "issued");
      const data = await quotes.listForBusiness(business.id);
      setQuoteList(data);
    } catch (err) {
      setError(
        err instanceof FieldedApiError
          ? err.error.message
          : "Failed to issue quote"
      );
    } finally {
      setActionLoading(null);
    }
  }

  async function handleExpire(quoteId: string) {
    if (!business) return;
    try {
      setActionLoading(quoteId);
      await quotes.transitionBusiness(business.id, quoteId, "expired");
      const data = await quotes.listForBusiness(business.id);
      setQuoteList(data);
    } catch (err) {
      setError(
        err instanceof FieldedApiError
          ? err.error.message
          : "Failed to expire quote"
      );
    } finally {
      setActionLoading(null);
    }
  }

  const filteredList =
    activeFilter === "all"
      ? quoteList
      : quoteList.filter((q) => q.status === activeFilter);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Quotes
        </h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Manage quotes sent to customers.
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
              ? "No quotes yet"
              : `No ${formatStatus(activeFilter).toLowerCase()} quotes`
          }
          description="Quotes will appear here when you respond to customer enquiries with pricing."
        />
      ) : (
        <div className="space-y-3">
          {filteredList.map((quote) => (
            <Card key={quote.id} padding="sm">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-3">
                    <p className="text-xs font-mono text-[var(--text-muted)]">
                      {quote.reference}
                    </p>
                    <Badge variant={statusBadgeVariant(quote.status)}>
                      {formatStatus(quote.status)}
                    </Badge>
                  </div>
                  <p className="mt-2 text-xl font-bold text-[var(--text-primary)]">
                    {quote.currency} {parseFloat(quote.amount).toFixed(2)}
                  </p>
                  {quote.notes && (
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">
                      {quote.notes}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    Created {formatDate(quote.created_at)}
                  </p>
                </div>

                <div className="flex flex-col items-end gap-2 flex-shrink-0">
                  {quote.status === "draft" && (
                    <button
                      onClick={() => handleIssue(quote.id)}
                      disabled={actionLoading === quote.id}
                      className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
                    >
                      Issue to Customer
                    </button>
                  )}
                  {quote.status === "issued" && (
                    <button
                      onClick={() => handleExpire(quote.id)}
                      disabled={actionLoading === quote.id}
                      className="rounded-lg border border-amber-500/30 px-3 py-1.5 text-xs font-medium text-amber-400 hover:bg-amber-500/10 disabled:opacity-50"
                    >
                      Expire
                    </button>
                  )}
                </div>
              </div>

              {quote.pricing_evidence && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
                    Pricing evidence
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded bg-[var(--bg-elevated)] p-3 text-xs text-[var(--text-muted)]">
                    {JSON.stringify(quote.pricing_evidence, null, 2)}
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
