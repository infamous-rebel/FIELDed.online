"use client";

import { useEffect, useState } from "react";
import {
  businesses,
  invoices,
  payments,
  type BusinessSummary,
  type InvoiceData,
  type PaymentData,
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
  { label: "Processing", value: "processing" },
  { label: "Failed", value: "failed" },
  { label: "Refunded", value: "refunded" },
];

export default function BusinessPaymentsPage() {
  const [businessesList, setBusinessesList] = useState<BusinessSummary[]>([]);
  const [selectedBiz, setSelectedBiz] = useState<string>("");
  const [paymentsList, setPaymentsList] = useState<PaymentData[]>([]);
  const [invoicesList, setInvoicesList] = useState<InvoiceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState("all");
  const [showPayModal, setShowPayModal] = useState(false);
  const [refundModal, setRefundModal] = useState<PaymentData | null>(null);

  // Payment form state
  const [payInvoiceId, setPayInvoiceId] = useState("");
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState("card");
  const [payNotes, setPayNotes] = useState("");
  const [payLoading, setPayLoading] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  // Refund form state
  const [refundAmount, setRefundAmount] = useState("");
  const [refundReason, setRefundReason] = useState("");
  const [refundLoading, setRefundLoading] = useState(false);

  useEffect(() => {
    async function fetchData() {
      try {
        const bizList = await businesses.list();
        setBusinessesList(bizList);
        if (bizList.length > 0) {
          const bizId = bizList[0].id;
          setSelectedBiz(bizId);
          await loadPayments(bizId);
          await loadInvoices(bizId);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  async function loadPayments(bizId: string, status?: string) {
    const params = status && status !== "all" ? { status } : undefined;
    const data = await payments.listForBusiness(bizId, params);
    setPaymentsList(data);
  }

  async function loadInvoices(bizId: string) {
    const data = await invoices.listForBusiness(bizId);
    setInvoicesList(data.filter((inv) => inv.payment_status !== "paid" && inv.payment_status !== "void"));
  }

  async function handleFilterChange(filter: string) {
    setActiveFilter(filter);
    if (selectedBiz) {
      await loadPayments(selectedBiz, filter);
    }
  }

  async function handleCreatePayment() {
    if (!selectedBiz || !payInvoiceId || !payAmount) return;
    setPayLoading(true);
    setPayError(null);
    try {
      await payments.create(selectedBiz, {
        invoice_id: payInvoiceId,
        amount: payAmount,
        currency: "GBP",
        payment_method: payMethod,
        idempotency_key: `ui-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        notes: payNotes || undefined,
      });
      setShowPayModal(false);
      setPayInvoiceId("");
      setPayAmount("");
      setPayNotes("");
      await loadPayments(selectedBiz, activeFilter);
      await loadInvoices(selectedBiz);
    } catch (err) {
      setPayError(err instanceof Error ? err.message : "Payment failed");
    } finally {
      setPayLoading(false);
    }
  }

  async function handleRefund() {
    if (!selectedBiz || !refundModal) return;
    setRefundLoading(true);
    try {
      await payments.refund(selectedBiz, refundModal.id, {
        amount: refundAmount || undefined,
        reason: refundReason || undefined,
      });
      setRefundModal(null);
      setRefundAmount("");
      setRefundReason("");
      await loadPayments(selectedBiz, activeFilter);
    } catch (err) {
      // Refund error — could show in modal
    } finally {
      setRefundLoading(false);
    }
  }

  if (loading) return <LoadingSkeleton lines={5} variant="list" />;
  if (error) return <div className="text-red-400 p-4">{error}</div>;

  const selectedBusiness = businessesList.find((b) => b.id === selectedBiz);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            Payments
          </h1>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            {selectedBusiness?.name || "Business"} — Transaction history & payment management
          </p>
        </div>
        <button
          onClick={() => setShowPayModal(true)}
          className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 transition-opacity"
        >
          Record Payment
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 overflow-x-auto">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleFilterChange(tab.value)}
            className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              activeFilter === tab.value
                ? "bg-[var(--accent)] text-white"
                : "bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
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
          description="Record a payment against an invoice to get started."
        />
      ) : (
        <div className="space-y-3">
          {paymentsList.map((payment) => (
            <Card key={payment.id} className="p-4">
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
                    Provider: {payment.provider}
                    {payment.provider_reference && (
                      <span> — Ref: {payment.provider_reference.slice(0, 20)}</span>
                    )}
                  </div>
                  <div className="text-xs text-[var(--text-muted)]">
                    Created: {formatDate(payment.created_at)}
                    {payment.paid_at && <span> — Paid: {formatDate(payment.paid_at)}</span>}
                  </div>
                  {payment.notes && (
                    <div className="text-xs text-[var(--text-secondary)]">
                      {payment.notes}
                    </div>
                  )}
                  {payment.failure_message && (
                    <div className="text-xs text-red-400">
                      Failed: {payment.failure_message}
                    </div>
                  )}
                  {parseFloat(payment.refunded_amount) > 0 && (
                    <div className="text-xs text-amber-400">
                      Refunded: {formatCurrency(payment.refunded_amount, payment.currency)}
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  {payment.status === "succeeded" && (
                    <button
                      onClick={() => setRefundModal(payment)}
                      className="rounded-lg border border-red-500/30 px-3 py-1 text-xs font-medium text-red-400 hover:bg-red-500/10 transition-colors"
                    >
                      Refund
                    </button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Invoice payment status summary */}
      {invoicesList.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-3">
            Outstanding Invoices
          </h2>
          <div className="space-y-2">
            {invoicesList.map((inv) => (
              <Card key={inv.id} className="p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {inv.invoice_number}
                    </span>
                    <span className="ml-2 text-xs text-[var(--text-muted)]">
                      {formatCurrency(inv.total, inv.currency)}
                    </span>
                  </div>
                  <Badge variant={statusBadgeVariant(inv.payment_status)}>
                    {formatStatus(inv.payment_status)}
                  </Badge>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Create payment modal */}
      {showPayModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-md p-6 space-y-4">
            <h3 className="text-lg font-semibold text-[var(--text-primary)]">
              Record Payment
            </h3>
            {payError && (
              <div className="rounded-lg bg-red-500/10 p-3 text-sm text-red-400">
                {payError}
              </div>
            )}
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                  Invoice
                </label>
                <select
                  value={payInvoiceId}
                  onChange={(e) => setPayInvoiceId(e.target.value)}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
                >
                  <option value="">Select invoice...</option>
                  {invoicesList.map((inv) => (
                    <option key={inv.id} value={inv.id}>
                      {inv.invoice_number} — {formatCurrency(inv.total, inv.currency)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                  Amount
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={payAmount}
                  onChange={(e) => setPayAmount(e.target.value)}
                  placeholder="0.00"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                  Payment Method
                </label>
                <select
                  value={payMethod}
                  onChange={(e) => setPayMethod(e.target.value)}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
                >
                  <option value="card">Card</option>
                  <option value="bank_transfer">Bank Transfer</option>
                  <option value="cash">Cash</option>
                  <option value="digital_wallet">Digital Wallet</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                  Notes (optional)
                </label>
                <input
                  type="text"
                  value={payNotes}
                  onChange={(e) => setPayNotes(e.target.value)}
                  placeholder="Payment notes..."
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowPayModal(false);
                  setPayError(null);
                }}
                className="rounded-lg px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                Cancel
              </button>
              <button
                onClick={handleCreatePayment}
                disabled={payLoading || !payInvoiceId || !payAmount}
                className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {payLoading ? "Processing..." : "Record Payment"}
              </button>
            </div>
          </Card>
        </div>
      )}

      {/* Refund modal */}
      {refundModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-md p-6 space-y-4">
            <h3 className="text-lg font-semibold text-[var(--text-primary)]">
              Refund Payment
            </h3>
            <div className="text-sm text-[var(--text-secondary)]">
              Refunding payment of{" "}
              <strong>{formatCurrency(refundModal.amount, refundModal.currency)}</strong>
              {parseFloat(refundModal.refunded_amount) > 0 && (
                <span> (already refunded {formatCurrency(refundModal.refunded_amount, refundModal.currency)})</span>
              )}
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                  Refund Amount (leave empty for full refund)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={refundAmount}
                  onChange={(e) => setRefundAmount(e.target.value)}
                  placeholder="Full amount"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                  Reason (optional)
                </label>
                <input
                  type="text"
                  value={refundReason}
                  onChange={(e) => setRefundReason(e.target.value)}
                  placeholder="Refund reason..."
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setRefundModal(null);
                  setRefundAmount("");
                  setRefundReason("");
                }}
                className="rounded-lg px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                Cancel
              </button>
              <button
                onClick={handleRefund}
                disabled={refundLoading}
                className="rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {refundLoading ? "Processing..." : "Process Refund"}
              </button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
