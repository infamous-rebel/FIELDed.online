"use client";

import { useEffect, useState } from "react";
import {
  serviceExecutions,
  invoices,
  type ServiceExecutionData,
  type InvoiceData,
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

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatCurrency(amount: string, currency: string = "AUD"): string {
  const num = parseFloat(amount);
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency,
  }).format(num);
}

type TabKey = "services" | "invoices";

const TABS: { key: TabKey; label: string }[] = [
  { key: "services", label: "Service History" },
  { key: "invoices", label: "Invoices" },
];

export default function CustomerServices() {
  const [activeTab, setActiveTab] = useState<TabKey>("services");
  const [executions, setExecutions] = useState<ServiceExecutionData[]>([]);
  const [invoiceList, setInvoiceList] = useState<InvoiceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [execData, invData] = await Promise.all([
        serviceExecutions.listMy(),
        invoices.listMy(),
      ]);
      setExecutions(execData);
      setInvoiceList(invData);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load data"
      );
    } finally {
      setLoading(false);
    }
  }

  /** Map invoice to its execution for cross-referencing */
  function invoiceForExecution(executionId: string): InvoiceData | undefined {
    return invoiceList.find((inv) => inv.service_execution_id === executionId);
  }

  const completedCount = executions.filter(
    (e) => e.status === "completed"
  ).length;
  const totalInvoiced = invoiceList.reduce(
    (sum, inv) => sum + parseFloat(inv.total),
    0
  );
  const totalPaid = invoiceList
    .filter((inv) => inv.payment_status === "paid")
    .reduce((sum, inv) => sum + parseFloat(inv.total), 0);

  return (
    <div className="space-y-5">
      <div className="mb-6">
        <h1 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
          My Services
        </h1>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          View your completed services, invoices, and payment status.
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

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 mb-6">
        <Card padding="sm">
          <p className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
            Completed Services
          </p>
          <p className="mt-2 text-2xl font-bold text-[var(--text-primary)]">
            {completedCount}
          </p>
        </Card>
        <Card padding="sm">
          <p className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
            Total Invoiced
          </p>
          <p className="mt-2 text-2xl font-bold text-[var(--text-primary)]">
            {formatCurrency(totalInvoiced.toFixed(2))}
          </p>
        </Card>
        <Card padding="sm">
          <p className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
            Total Paid
          </p>
          <p className="mt-2 text-2xl font-bold text-emerald-400">
            {formatCurrency(totalPaid.toFixed(2))}
          </p>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`rounded-lg px-3 py-1.5 text-[13px] font-medium transition-all ${
              activeTab === tab.key
                ? "bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/20"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)] border border-transparent hover:bg-white/[0.03]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {loading ? (
        <LoadingSkeleton variant="list" lines={4} />
      ) : activeTab === "services" ? (
        <ServiceHistoryTab
          executions={executions}
          invoiceForExecution={invoiceForExecution}
        />
      ) : (
        <InvoicesTab invoices={invoiceList} />
      )}
    </div>
  );
}

/* ─── Service History Tab ──────────────────────────────────────────── */

function ServiceHistoryTab({
  executions,
  invoiceForExecution,
}: {
  executions: ServiceExecutionData[];
  invoiceForExecution: (id: string) => InvoiceData | undefined;
}) {
  if (executions.length === 0) {
    return (
      <EmptyState
        title="No services yet"
        description="Your completed services will appear here after a business marks a booking as completed."
      />
    );
  }

  return (
    <div className="space-y-3">
      {executions.map((exec) => {
        const invoice = invoiceForExecution(exec.id);
        return (
          <Card key={exec.id} padding="sm" hover>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <Badge variant={statusBadgeVariant(exec.status)}>
                    {formatStatus(exec.status)}
                  </Badge>
                  <span className="text-xs text-[var(--text-muted)]">
                    {formatDate(exec.completed_at || exec.scheduled_at)}
                  </span>
                </div>

                {exec.notes && (
                  <p className="mt-2 text-sm text-[var(--text-secondary)]">
                    {exec.notes}
                  </p>
                )}

                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--text-muted)]">
                  <span>
                    Scheduled: {formatDate(exec.scheduled_at)}
                  </span>
                  {exec.started_at && (
                    <span>Started: {formatDate(exec.started_at)}</span>
                  )}
                  {exec.completed_at && (
                    <span>Completed: {formatDate(exec.completed_at)}</span>
                  )}
                </div>

                {/* Linked invoice summary */}
                {invoice && (
                  <div className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-[var(--text-muted)]">
                          Invoice {invoice.invoice_number}
                        </p>
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {formatCurrency(invoice.total, invoice.currency)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={statusBadgeVariant(invoice.payment_status)}>
                          {formatStatus(invoice.payment_status)}
                        </Badge>
                        <InvoicePdfLink invoiceId={invoice.id} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}

/* ─── Invoices Tab ─────────────────────────────────────────────────── */

function InvoicesTab({ invoices: invoiceList }: { invoices: InvoiceData[] }) {
  if (invoiceList.length === 0) {
    return (
      <EmptyState
        title="No invoices yet"
        description="Invoices are generated when a business completes a service."
      />
    );
  }

  return (
    <div className="space-y-3">
      {invoiceList.map((inv) => (
        <Card key={inv.id} padding="sm" hover>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-3">
                <p className="text-sm font-mono font-medium text-[var(--text-primary)]">
                  {inv.invoice_number}
                </p>
                <Badge variant={statusBadgeVariant(inv.status)}>
                  {formatStatus(inv.status)}
                </Badge>
                <Badge variant={statusBadgeVariant(inv.payment_status)}>
                  {formatStatus(inv.payment_status)}
                </Badge>
              </div>

              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--text-muted)]">
                <span>Issued: {formatDate(inv.issue_date)}</span>
                {inv.due_date && <span>Due: {formatDate(inv.due_date)}</span>}
              </div>

              {/* Line items */}
              {inv.line_items.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
                    Line items ({inv.line_items.length})
                  </summary>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[var(--border-subtle)] text-[var(--text-muted)]">
                          <th className="pb-1 pr-4 font-medium">Description</th>
                          <th className="pb-1 pr-4 text-right font-medium">Qty</th>
                          <th className="pb-1 pr-4 text-right font-medium">Unit</th>
                          <th className="pb-1 text-right font-medium">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {inv.line_items.map((item) => (
                          <tr
                            key={item.id}
                            className="border-b border-[var(--border-subtle)]/50"
                          >
                            <td className="py-1 pr-4 text-[var(--text-secondary)]">
                              {item.description}
                            </td>
                            <td className="py-1 pr-4 text-right text-[var(--text-secondary)]">
                              {item.quantity}
                            </td>
                            <td className="py-1 pr-4 text-right text-[var(--text-secondary)]">
                              {formatCurrency(item.unit_price, item.currency)}
                            </td>
                            <td className="py-1 text-right font-medium text-[var(--text-primary)]">
                              {formatCurrency(item.line_total, item.currency)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}
            </div>

            <div className="flex flex-col items-end gap-2 flex-shrink-0">
              <p className="text-lg font-bold text-[var(--text-primary)]">
                {formatCurrency(inv.total, inv.currency)}
              </p>
              <InvoicePdfLink invoiceId={inv.id} />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

/* ─── Shared: Invoice PDF download link ────────────────────────────── */

function InvoicePdfLink({ invoiceId }: { invoiceId: string }) {
  const pdfUrl = invoices.getMyPdfUrl(invoiceId);

  return (
    <a
      href={pdfUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] transition-colors"
      title="Download PDF"
    >
      <svg
        className="h-3.5 w-3.5"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"
        />
      </svg>
      PDF
    </a>
  );
}
