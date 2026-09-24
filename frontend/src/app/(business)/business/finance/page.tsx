"use client";

import { useEffect, useState } from "react";
import {
  businesses,
  quotes,
  invoices,
  payments,
  type BusinessSummary,
  type QuoteData,
  type InvoiceData,
  type PaymentData,
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

type TabValue = "quotes" | "invoices" | "payments";

const TABS: { label: string; value: TabValue }[] = [
  { label: "Quotes", value: "quotes" },
  { label: "Invoices", value: "invoices" },
  { label: "Payments", value: "payments" },
];

export default function BusinessFinancePage() {
  const [business, setBusiness] = useState<BusinessSummary | null>(null);
  const [quoteList, setQuoteList] = useState<QuoteData[]>([]);
  const [invoiceList, setInvoiceList] = useState<InvoiceData[]>([]);
  const [paymentList, setPaymentList] = useState<PaymentData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabValue>("quotes");

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

        const [qtData, invData, payData] = await Promise.all([
          quotes.listForBusiness(biz.id).catch(() => [] as QuoteData[]),
          invoices.listForBusiness(biz.id).catch(() => [] as InvoiceData[]),
          payments.listForBusiness(biz.id).catch(() => [] as PaymentData[]),
        ]);
        setQuoteList(qtData);
        setInvoiceList(invData);
        setPaymentList(payData);
      } catch (err) {
        setError(err instanceof FieldedApiError ? err.error.message : "Failed to load finance data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Summary stats
  const pendingQuotes = quoteList.filter((q) => ["draft", "issued"].includes(q.status));
  const totalQuoted = quoteList.reduce((sum, q) => sum + parseFloat(q.amount || "0"), 0);
  const paidInvoices = invoiceList.filter((i) => i.payment_status === "paid");
  const totalRevenue = paidInvoices.reduce((sum, i) => sum + parseFloat(i.total || "0"), 0);
  const outstandingInvoices = invoiceList.filter((i) => ["unpaid", "partial"].includes(i.payment_status));
  const totalOutstanding = outstandingInvoices.reduce((sum, i) => sum + parseFloat(i.total || "0"), 0);

  const tabCounts = {
    quotes: quoteList.length,
    invoices: invoiceList.length,
    payments: paymentList.length,
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Finance</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Quotes, invoices, and payments in one place.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]" role="alert">
          {error}
        </div>
      )}

      {/* Summary cards */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <LoadingSkeleton variant="card" />
          <LoadingSkeleton variant="card" />
          <LoadingSkeleton variant="card" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <Card padding="sm">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">Quoted</p>
            <p className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{formatAmount(totalQuoted)}</p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">{quoteList.length} quote{quoteList.length !== 1 ? "s" : ""}</p>
          </Card>
          <Card padding="sm">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">Revenue</p>
            <p className="mt-1 text-2xl font-bold text-emerald-400">{formatAmount(totalRevenue)}</p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">{paidInvoices.length} paid invoice{paidInvoices.length !== 1 ? "s" : ""}</p>
          </Card>
          <Card padding="sm">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">Outstanding</p>
            <p className="mt-1 text-2xl font-bold text-amber-400">{formatAmount(totalOutstanding)}</p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">{outstandingInvoices.length} unpaid</p>
          </Card>
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
      ) : activeTab === "quotes" ? (
        quoteList.length === 0 ? (
          <EmptyState
            title="No quotes yet"
            description="Quotes are created from enquiries. Go to Enquiries to create your first quote."
          />
        ) : (
          <div className="space-y-3">
            {quoteList
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((quote) => (
                <Card key={quote.id} padding="sm">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <p className="text-xs font-mono text-[var(--text-muted)]">{quote.reference}</p>
                        <Badge variant={statusBadgeVariant(quote.status)}>{formatStatus(quote.status)}</Badge>
                      </div>
                      <p className="mt-2 text-sm text-[var(--text-secondary)]">
                        <span className="font-semibold text-[var(--text-primary)]">{formatAmount(quote.amount, quote.currency)}</span>
                        {quote.notes && <span className="ml-2 text-[var(--text-muted)]">— {quote.notes}</span>}
                      </p>
                      <p className="mt-1 text-xs text-[var(--text-muted)]">Created {formatDate(quote.created_at)}</p>
                    </div>
                    <a
                      href={`/business/enquiries`}
                      className="text-xs font-medium text-[var(--accent)] hover:underline flex-shrink-0"
                    >
                      View enquiry &rarr;
                    </a>
                  </div>
                </Card>
              ))}
          </div>
        )
      ) : activeTab === "invoices" ? (
        invoiceList.length === 0 ? (
          <EmptyState
            title="No invoices yet"
            description="Invoices are generated automatically when services are completed."
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
      ) : (
        paymentList.length === 0 ? (
          <EmptyState
            title="No payments yet"
            description="Payments will appear here when customers pay invoices."
          />
        ) : (
          <div className="space-y-3">
            {paymentList
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((payment) => (
                <Card key={payment.id} padding="sm">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <p className="text-xs font-mono text-[var(--text-muted)]">{payment.id.slice(0, 8)}</p>
                        <Badge variant={statusBadgeVariant(payment.status)}>{formatStatus(payment.status)}</Badge>
                        <span className="text-xs text-[var(--text-muted)]">{payment.payment_method}</span>
                      </div>
                      <p className="mt-2 text-sm text-[var(--text-secondary)]">
                        <span className="font-semibold text-[var(--text-primary)]">{formatAmount(payment.amount, payment.currency)}</span>
                        {payment.paid_at && (
                          <span className="ml-2 text-[var(--text-muted)]">Paid {formatDate(payment.paid_at)}</span>
                        )}
                      </p>
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
