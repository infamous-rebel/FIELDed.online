"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { enquiries, EnquiryData, FieldedApiError } from "@/lib/api-client";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
  submitted: "bg-blue-500/15 text-blue-400",
  received: "bg-blue-500/15 text-blue-400",
  in_review: "bg-amber-500/15 text-amber-400",
  needs_information: "bg-amber-500/15 text-amber-400",
  declined: "bg-red-500/15 text-red-400",
  cancelled: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
  expired: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
  rejected: "bg-red-500/15 text-red-400",
};

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
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">My Enquiries</h1>
        <p className="mt-4 text-[var(--text-secondary)]">Loading...</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-[var(--text-primary)]">My Enquiries</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Track your service enquiries and conversations.
      </p>

      {error && (
        <div className="mt-4 rounded-md bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      )}

      {enquiryList.length === 0 ? (
        <div className="mt-8 rounded-lg border-2 border-dashed border-[var(--border-default)] p-8 text-center">
          <p className="text-[var(--text-secondary)]">No enquiries yet.</p>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Browse businesses and submit an enquiry to get started.
          </p>
          <Link
            href="/search"
            className="mt-4 inline-block rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-hover)]"
          >
            Find a Service
          </Link>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          {enquiryList.map((enquiry) => (
            <Link
              key={enquiry.id}
              href={`/customer/enquiries/${enquiry.id}`}
              className="block rounded-lg border border-[var(--border-subtle)] p-4 transition hover:border-[var(--border-default)] hover:shadow-sm"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-mono text-[var(--text-muted)]">
                    {enquiry.reference}
                  </p>
                  <h3 className="mt-1 font-medium text-[var(--text-primary)]">
                    {enquiry.subject}
                  </h3>
                  <p className="mt-1 text-sm text-[var(--text-secondary)] line-clamp-2">
                    {enquiry.message}
                  </p>
                </div>
                <span
                  className={`ml-4 shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    STATUS_COLORS[enquiry.status] || "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
                  }`}
                >
                  {formatStatus(enquiry.status)}
                </span>
              </div>
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                {formatDate(enquiry.created_at)}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
