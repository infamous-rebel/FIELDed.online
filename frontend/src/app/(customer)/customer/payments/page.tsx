"use client";

import { useEffect, useState } from "react";
import {
  payments,
  type PaymentData,
  FieldedApiError,
} from "@/lib/api-client";
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

function formatCurrency(amount: string, currency: string): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(parseFloat(amount));
}

const FILTER_TABS = [
  { label: "All", value: "all" },
  { label: "Succeeded", value: "succeeded" },
  { label: "Pending", value: "pending" },
  { label: "Failed", value: "failed" },
  { label: "Refunded", value: "refunded" },
];

export default function CustomerPaymentsPage() {
  const [paymentsList, setPaymentsList] = useState<PaymentData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState("all");
  const [selectedPayment, setSelectedPayment] = useState<PaymentData | null>(null);

  useEffect(() => {
    loadPayments();
  }, []);

  async function loadPayments(status?: string) {
    try {
      setLoading(true);
      const params = status && status !== "all" ? { status } : undefined;
      const data = await payments.listMine(params);
      setPaymentsList(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load payments");
    } finally {
      setLoading(false);
    }
  }

  async function handleFilterChange(filter: string) {
    setActiveFilter(filter);
    await loadPayments(filter);
  }

  if (loading) return <LoadingSkeleton lines={5} variant="list" />;
  if (error) return <div className="text-red-400 p-4">{error}</div>;

  return (
    <div className="space-y-5">
      <div className="mb-6">
        <h1 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
          Payments
        </h1>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Your payment history and transaction status
        </p>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1.5 overflow-x-auto mb-4">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleFilterChange(tab.value)}
            className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-[13px] font-medium transition-all ${
              activeFilter === tab.value
                ? "bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/20"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)] border border-transparent hover:bg-white/[0.03]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Payments list */}
      {paymentsList.length === 0 ? (
        <EmptyState
          title="No payments yet"
          description="Payments will appear here once you book and pay for services."
        />
      ) : (
        <div className="space-y-2">
          {paymentsList.map((payment) => (
            <div
              key={payment.id}
              className="glass rounded-lg p-4 cursor-pointer hover:border-[var(--accent)]/15 hover:border-white/[0.08] transition-all"
              onClick={() => setSelectedPayment(payment)}
            >
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {formatCurrency(payment.amount, payment.currency)}
                    </span>
                    <Badge variant={statusBadgeVariant(payment.status)}>
                      {formatStatus(payment.status)}
                    </Badge>
                    <span className="text-xs text-[var(--text-muted)]">
                      {payment.payment_method.toUpperCase()}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--text-muted)]">
                    {formatDate(payment.created_at)}
                    {payment.paid_at && (
                      <span> — Completed: {formatDate(payment.paid_at)}</span>
                    )}
                  </div>
                  {payment.notes && (
                    <div className="text-xs text-[var(--text-secondary)]">
                      {payment.notes}
                    </div>
                  )}
                  {parseFloat(payment.refunded_amount) > 0 && (
                    <div className="text-xs text-amber-400">
                      Refunded: {formatCurrency(payment.refunded_amount, payment.currency)}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Payment detail modal */}
      {selectedPayment && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setSelectedPayment(null)}
        >
          <div
            className="w-full max-w-lg rounded-lg border border-white/[0.08] glass p-6 space-y-4 max-h-[80vh] overflow-y-auto"
            onClick={(e: React.MouseEvent) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-[var(--text-primary)]">
                Payment Details
              </h3>
              <button
                onClick={() => setSelectedPayment(null)}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-[var(--text-muted)]">Amount</span>
                <span className="text-sm font-medium text-[var(--text-primary)]">
                  {formatCurrency(selectedPayment.amount, selectedPayment.currency)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-[var(--text-muted)]">Status</span>
                <Badge variant={statusBadgeVariant(selectedPayment.status)}>
                  {formatStatus(selectedPayment.status)}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-[var(--text-muted)]">Method</span>
                <span className="text-sm text-[var(--text-primary)]">
                  {selectedPayment.payment_method.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-[var(--text-muted)]">Provider</span>
                <span className="text-sm text-[var(--text-primary)]">
                  {selectedPayment.provider}
                </span>
              </div>
              {selectedPayment.provider_reference && (
                <div className="flex justify-between">
                  <span className="text-sm text-[var(--text-muted)]">Reference</span>
                  <span className="text-sm text-[var(--text-primary)] font-mono text-xs">
                    {selectedPayment.provider_reference}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-sm text-[var(--text-muted)]">Created</span>
                <span className="text-sm text-[var(--text-primary)]">
                  {formatDate(selectedPayment.created_at)}
                </span>
              </div>
              {selectedPayment.paid_at && (
                <div className="flex justify-between">
                  <span className="text-sm text-[var(--text-muted)]">Paid at</span>
                  <span className="text-sm text-[var(--text-primary)]">
                    {formatDate(selectedPayment.paid_at)}
                  </span>
                </div>
              )}
              {parseFloat(selectedPayment.refunded_amount) > 0 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-sm text-[var(--text-muted)]">Refunded</span>
                    <span className="text-sm text-amber-400">
                      {formatCurrency(selectedPayment.refunded_amount, selectedPayment.currency)}
                    </span>
                  </div>
                  {selectedPayment.refunded_at && (
                    <div className="flex justify-between">
                      <span className="text-sm text-[var(--text-muted)]">Refunded at</span>
                      <span className="text-sm text-[var(--text-primary)]">
                        {formatDate(selectedPayment.refunded_at)}
                      </span>
                    </div>
                  )}
                </>
              )}
              {selectedPayment.failure_message && (
                <div className="rounded-lg bg-red-500/10 p-3">
                  <div className="text-sm text-red-400">
                    {selectedPayment.failure_message}
                  </div>
                </div>
              )}
              {selectedPayment.notes && (
                <div className="text-sm text-[var(--text-secondary)]">
                  {selectedPayment.notes}
                </div>
              )}
            </div>

            {/* Attempts */}
            {selectedPayment.attempts && selectedPayment.attempts.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-[var(--text-primary)] mb-2">
                  Payment Attempts
                </h4>
                <div className="space-y-2">
                  {selectedPayment.attempts.map((attempt) => (
                    <div
                      key={attempt.id}
                      className="rounded-lg bg-[var(--bg-elevated)] p-3 text-xs space-y-1"
                    >
                      <div className="flex justify-between">
                        <span className="text-[var(--text-secondary)]">
                          Attempt #{attempt.attempt_number}
                        </span>
                        <Badge variant={statusBadgeVariant(attempt.status)}>
                          {formatStatus(attempt.status)}
                        </Badge>
                      </div>
                      <div className="text-[var(--text-muted)]">
                        {formatDate(attempt.requested_at)}
                      </div>
                      {attempt.error_message && (
                        <div className="text-red-400">{attempt.error_message}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
