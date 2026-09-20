"use client";

import { useEffect, useState } from "react";
import {
  businesses,
  serviceExecutions,
  invoices,
  ledger,
  type BusinessSummary,
  type ServiceExecutionData,
  type InvoiceData,
  type LedgerSummaryData,
} from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

export default function BusinessOperationsPage() {
  const [bizList, setBizList] = useState<BusinessSummary[]>([]);
  const [executions, setExecutions] = useState<ServiceExecutionData[]>([]);
  const [summary, setSummary] = useState<LedgerSummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"operations" | "invoices" | "ledger">("operations");

  useEffect(() => {
    async function loadData() {
      try {
        const bizData = await businesses.list();
        setBizList(bizData);
        if (bizData.length > 0) {
          const [execData, summaryData] = await Promise.all([
            serviceExecutions.listForBusiness(bizData[0].id),
            ledger.getSummary(bizData[0].id),
          ]);
          setExecutions(execData);
          setSummary(summaryData);
        }
      } catch {
        // API error — show empty states
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const businessId = bizList[0]?.id;

  const handleComplete = async (executionId: string) => {
    if (!businessId) return;
    try {
      await serviceExecutions.complete(businessId, executionId);
      // Reload data
      const [execData, summaryData] = await Promise.all([
        serviceExecutions.listForBusiness(businessId),
        ledger.getSummary(businessId),
      ]);
      setExecutions(execData);
      setSummary(summaryData);
    } catch (err) {
      console.error("Failed to complete service:", err);
    }
  };

  const handleTransition = async (executionId: string, targetStatus: string) => {
    if (!businessId) return;
    try {
      await serviceExecutions.transition(businessId, executionId, targetStatus);
      const execData = await serviceExecutions.listForBusiness(businessId);
      setExecutions(execData);
    } catch (err) {
      console.error("Failed to transition:", err);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Service Operations</h1>
        <p className="mt-1 text-[var(--text-secondary)]">
          Manage service delivery, invoices, and ledger
        </p>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <p className="text-sm text-[var(--text-muted)]">Completed Services</p>
            <p className="mt-1 text-2xl font-bold text-[var(--text-primary)]">
              {summary.total_entries}
            </p>
          </Card>
          <Card>
            <p className="text-sm text-[var(--text-muted)]">Total Revenue</p>
            <p className="mt-1 text-2xl font-bold text-[var(--text-primary)]">
              {summary.total_net}
            </p>
          </Card>
          <Card>
            <p className="text-sm text-[var(--text-muted)]">Paid</p>
            <p className="mt-1 text-2xl font-bold text-green-600">
              {summary.paid_amount}
            </p>
          </Card>
          <Card>
            <p className="text-sm text-[var(--text-muted)]">Outstanding</p>
            <p className="mt-1 text-2xl font-bold text-orange-600">
              {summary.outstanding_amount}
            </p>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-[var(--border-subtle)]">
        {(["operations", "invoices", "ledger"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? "border-[var(--accent)] text-[var(--accent)]"
                : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "operations" && (
        <OperationsTab
          executions={executions}
          loading={loading}
          onComplete={handleComplete}
          onTransition={handleTransition}
        />
      )}
      {activeTab === "invoices" && businessId && (
        <InvoicesTab businessId={businessId} />
      )}
      {activeTab === "ledger" && businessId && (
        <LedgerTab businessId={businessId} summary={summary} />
      )}
    </div>
  );
}

function OperationsTab({
  executions,
  loading,
  onComplete,
  onTransition,
}: {
  executions: ServiceExecutionData[];
  loading: boolean;
  onComplete: (id: string) => void;
  onTransition: (id: string, status: string) => void;
}) {
  if (loading) return <LoadingSkeleton lines={5} />;

  if (executions.length === 0) {
    return (
      <Card>
        <div className="text-center py-8">
          <p className="text-[var(--text-muted)]">No service executions yet</p>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Service executions are created from confirmed bookings
          </p>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {executions.map((exec) => (
        <Card key={exec.id} padding="sm" hover>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Booking: {exec.booking_id.slice(0, 8)}...
              </p>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Customer: {exec.customer_id.slice(0, 8)}...
                {exec.scheduled_at && ` · Scheduled: ${new Date(exec.scheduled_at).toLocaleDateString()}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={statusVariant(exec.status)}>{exec.status}</Badge>
              {exec.status === "scheduled" && (
                <>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => onTransition(exec.id, "in_progress")}
                  >
                    Start
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => onTransition(exec.id, "cancelled")}
                  >
                    Cancel
                  </Button>
                </>
              )}
              {exec.status === "in_progress" && (
                <Button
                  size="sm"
                  onClick={() => onComplete(exec.id)}
                >
                  Complete
                </Button>
              )}
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

function InvoicesTab({ businessId }: { businessId: string }) {
  const [invoiceList, setInvoiceList] = useState<InvoiceData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await invoices.listForBusiness(businessId);
        setInvoiceList(data);
      } catch {
        // Error
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [businessId]);

  if (loading) return <LoadingSkeleton lines={3} />;

  if (invoiceList.length === 0) {
    return (
      <Card>
        <div className="text-center py-8">
          <p className="text-[var(--text-muted)]">No invoices yet</p>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Invoices are generated when services are completed
          </p>
        </div>
      </Card>
    );
  }

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const token = typeof window !== "undefined" ? localStorage.getItem("fielded_access_token") : null;

  return (
    <div className="space-y-3">
      {invoiceList.map((inv) => (
        <Card key={inv.id} padding="sm" hover>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {inv.invoice_number}
              </p>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                {inv.currency} {inv.total} · Issued: {new Date(inv.issue_date).toLocaleDateString()}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={paymentVariant(inv.payment_status)}>
                {inv.payment_status}
              </Badge>
              <a
                href={`${apiUrl}/api/v1/businesses/${businessId}/invoices/${inv.id}/pdf`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-[var(--accent)] hover:underline"
              >
                PDF
              </a>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

function LedgerTab({
  businessId,
  summary,
}: {
  businessId: string;
  summary: LedgerSummaryData | null;
}) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const token = typeof window !== "undefined" ? localStorage.getItem("fielded_access_token") : null;

  return (
    <div className="space-y-4">
      {/* Export buttons */}
      <div className="flex gap-3">
        <a
          href={`${apiUrl}/api/v1/businesses/${businessId}/ledger/export/csv`}
          className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
        >
          Export CSV
        </a>
        <a
          href={`${apiUrl}/api/v1/businesses/${businessId}/ledger/export/pdf`}
          className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
        >
          Export PDF
        </a>
      </div>

      {/* Summary */}
      {summary && (
        <Card>
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">Ledger Summary</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-[var(--text-muted)]">Gross</p>
              <p className="font-medium">{summary.total_gross}</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">Discount</p>
              <p className="font-medium">{summary.total_discount}</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">Tax</p>
              <p className="font-medium">{summary.total_tax}</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">Net</p>
              <p className="font-medium">{summary.total_net}</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function statusVariant(status: string): "info" | "warning" | "danger" | "muted" | "default" {
  switch (status.toLowerCase()) {
    case "scheduled":
      return "info";
    case "in_progress":
      return "warning";
    case "completed":
      return "default";
    case "cancelled":
      return "danger";
    case "no_show":
      return "danger";
    default:
      return "muted";
  }
}

function paymentVariant(status: string): "info" | "warning" | "danger" | "muted" | "default" {
  switch (status.toLowerCase()) {
    case "paid":
      return "default";
    case "unpaid":
      return "warning";
    case "partially_paid":
      return "info";
    case "void":
      return "danger";
    default:
      return "muted";
  }
}
