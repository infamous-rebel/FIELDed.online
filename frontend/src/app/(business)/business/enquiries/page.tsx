"use client";

import { useEffect, useState } from "react";
import { enquiries, businesses, type EnquiryData, type BusinessSummary, FieldedApiError } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge, statusBadgeVariant } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { Button } from "@/components/ui/button";

const FILTER_TABS = [
  { label: "All", value: "all" },
  { label: "Submitted", value: "submitted" },
  { label: "In Review", value: "in_review" },
  { label: "Needs Info", value: "needs_information" },
  { label: "Declined", value: "declined" },
  { label: "Cancelled", value: "cancelled" },
];

function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
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

export default function BusinessEnquiriesPage() {
  const [business, setBusiness] = useState<BusinessSummary | null>(null);
  const [enquiryList, setEnquiryList] = useState<EnquiryData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState("all");

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

        const data = await enquiries.listForBusiness(biz.id);
        setEnquiryList(data);
      } catch (err) {
        if (err instanceof FieldedApiError) {
          setError(err.error.message);
        } else {
          setError("Failed to load enquiries");
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filteredList =
    activeFilter === "all"
      ? enquiryList
      : enquiryList.filter((e) => e.status === activeFilter);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Customer Enquiries
        </h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Manage customer enquiries and conversations.
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
            {tab.value !== "all" && (
              <span className="ml-1.5 text-xs opacity-60">
                {enquiryList.filter(
                  (e) =>
                    tab.value === "all" || e.status === tab.value
                ).length}
              </span>
            )}
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
              ? "No enquiries received yet"
              : `No ${formatStatus(activeFilter).toLowerCase()} enquiries`
          }
          description="Customer enquiries will appear here when submitted."
        />
      ) : (
        <div className="space-y-3">
          {filteredList.map((enquiry) => (
            <Card key={enquiry.id} padding="sm" hover>
              <a
                href={`/business/${business!.id}/enquiries/${enquiry.id}`}
                className="block"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-mono text-[var(--text-muted)]">
                      {enquiry.reference}
                    </p>
                    <h3 className="mt-1 text-sm font-medium text-[var(--text-primary)] truncate">
                      {enquiry.subject}
                    </h3>
                    <p className="mt-1 text-sm text-[var(--text-secondary)] line-clamp-2">
                      {enquiry.message}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-2 flex-shrink-0">
                    <Badge variant={statusBadgeVariant(enquiry.status)}>
                      {formatStatus(enquiry.status)}
                    </Badge>
                    <span className="text-xs text-[var(--text-muted)]">
                      {formatDate(enquiry.created_at)}
                    </span>
                  </div>
                </div>
              </a>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
