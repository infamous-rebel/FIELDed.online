"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { enquiries, EnquiryData, FieldedApiError } from "@/lib/api-client";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { statusToBadgeVariant } from "@/lib/status";
import { Badge } from "@/components/ui/badge";

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

export default function CustomerEnquiries() {
  const [enquiryList, setEnquiryList] = useState<EnquiryData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await enquiries.listMine();
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

  if (loading) {
    return (
      <div>
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">My Enquiries</h1>
        <div className="mt-6">
          <LoadingSkeleton variant="list" lines={3} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">My Enquiries</h1>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Track your service enquiries and conversations.
        </p>
      </div>

      {error && (
        <div className="mt-4 rounded-md bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      )}

      {enquiryList.length === 0 ? (
        <EmptyState
          title="No enquiries yet"
          description="Browse businesses and submit an enquiry to get started."
          action={
            <Link
              href="/search"
              className="inline-block rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)]"
            >
              Find a Service
            </Link>
          }
        />
      ) : (
        <div className="mt-6 space-y-2">
          {enquiryList.map((enquiry) => (
            <Link
              key={enquiry.id}
              href={`/customer/enquiries/${enquiry.id}`}
              className="block glass rounded-lg p-4 transition-all hover:border-[var(--accent)]/15 hover:border-white/[0.08]"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider">
                    {enquiry.reference}
                  </p>
                  <h3 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                    {enquiry.subject}
                  </h3>
                  <p className="mt-1.5 text-sm text-[var(--text-secondary)] line-clamp-2 leading-relaxed">
                    {enquiry.message}
                  </p>
                </div>
                <Badge variant={statusToBadgeVariant(enquiry.status)}>
                  {formatStatus(enquiry.status)}
                </Badge>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <span className="h-1 w-1 rounded-full bg-[var(--text-muted)]" />
                <p className="text-[11px] text-[var(--text-muted)]">
                  {formatDate(enquiry.created_at)}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
