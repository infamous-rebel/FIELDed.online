"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  publicApi,
  enquiries,
  type PublicServiceOfferDetail,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";

function formatPricingLabel(pricingModel: string): string {
  const labels: Record<string, string> = {
    fixed: "Fixed Price",
    hourly: "Hourly Rate",
    starting_at: "Starting At",
    quote_required: "Quote Required",
    custom: "Custom Pricing",
  };
  return labels[pricingModel] || pricingModel.replace("_", " ");
}

function formatDeliveryLabel(mode: string): string {
  const labels: Record<string, string> = {
    on_site: "On Site",
    remote: "Remote",
    in_store: "In Store",
    hybrid: "Hybrid",
  };
  return labels[mode] || mode.replace("_", " ");
}

export default function ServiceDetailPage() {
  const params = useParams<{ slug: string; offerSlug: string }>();
  const router = useRouter();
  const [service, setService] = useState<PublicServiceOfferDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Enquiry form
  const [showEnquiry, setShowEnquiry] = useState(false);
  const [enquirySubject, setEnquirySubject] = useState("");
  const [enquiryMessage, setEnquiryMessage] = useState("");
  const [enquirySending, setEnquirySending] = useState(false);
  const [enquiryError, setEnquiryError] = useState("");
  const [enquirySuccess, setEnquirySuccess] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  const loadService = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const data = await publicApi.getServiceDetail(params.slug, params.offerSlug);
      setService(data);
      // Pre-fill subject with service name
      setEnquirySubject(`Enquiry about ${data.name}`);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load service");
    } finally {
      setLoading(false);
    }
  }, [params.slug, params.offerSlug]);

  useEffect(() => {
    loadService();
  }, [loadService]);

  const handleEnquirySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!service || !authed) return;

    try {
      setEnquirySending(true);
      setEnquiryError("");

      // Create enquiry using the business_id from the public service detail
      const enquiry = await enquiries.create(service.business_id, {
        service_offer_id: service.id,
        subject: enquirySubject,
        message: enquiryMessage,
      });

      setEnquirySuccess(true);
      // Redirect to the enquiry detail page
      router.push(`/customer/enquiries/${enquiry.id}`);
    } catch (err) {
      setEnquiryError(err instanceof FieldedApiError ? err.error.message : "Failed to create enquiry");
    } finally {
      setEnquirySending(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-1/3 rounded bg-[var(--bg-elevated)]" />
          <div className="h-4 w-2/3 rounded bg-[var(--bg-elevated)]" />
          <div className="h-32 w-full rounded-xl bg-[var(--bg-elevated)]" />
        </div>
      </div>
    );
  }

  if (error || !service) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-16">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Service Not Found</h1>
        <p className="mt-2 text-[var(--text-secondary)]">{error || "This service is not currently available."}</p>
        <Link href={`/business/${params.slug}`} className="mt-4 inline-block text-sm text-[var(--accent)] hover:underline">
          &larr; Back to business
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
        <Link href="/network" className="hover:text-[var(--accent)]">Network</Link>
        <span>/</span>
        <Link href={`/business/${service.business_slug}`} className="hover:text-[var(--accent)]">
          {service.business_name}
        </Link>
        <span>/</span>
        <span className="text-[var(--text-secondary)]">{service.name}</span>
      </nav>

      {/* Header */}
      <div className="mt-6 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-[var(--text-primary)]">{service.name}</h1>
              {service.business_is_verified && (
                <span className="inline-flex items-center gap-1 rounded-full bg-[var(--accent)]/15 px-2 py-0.5 text-xs font-medium text-[var(--accent)]">
                  <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                  Verified
                </span>
              )}
            </div>
            <Link
              href={`/business/${service.business_slug}`}
              className="mt-1 text-sm text-[var(--text-secondary)] hover:text-[var(--accent)]"
            >
              by {service.business_name}
            </Link>
          </div>
          {/* Pricing badge */}
          <div className="shrink-0 text-right">
            {service.pricing_summary && (
              <div>
                <span className="inline-block rounded-lg bg-[var(--accent)]/15 px-3 py-1.5 text-sm font-semibold text-[var(--accent)]">
                  {formatPricingLabel(service.pricing_summary.pricing_model)}
                </span>
                {service.pricing_summary.fixed_price && (
                  <p className="mt-1 text-lg font-bold text-[var(--text-primary)]">
                    {service.pricing_summary.currency || "£"}{service.pricing_summary.fixed_price}
                  </p>
                )}
                {service.pricing_summary.starting_price && (
                  <p className="mt-1 text-sm text-[var(--text-secondary)]">
                    from {service.pricing_summary.currency || "£"}{service.pricing_summary.starting_price}
                  </p>
                )}
                {service.pricing_summary.hourly_rate && (
                  <p className="mt-1 text-sm text-[var(--text-secondary)]">
                    {service.pricing_summary.currency || "£"}{service.pricing_summary.hourly_rate}/hr
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Tags row */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {service.category_name && (
            <span className="rounded-full bg-[var(--accent)]/10 px-3 py-1 text-xs font-medium text-[var(--accent)]">
              {service.category_name}
            </span>
          )}
          <span className="rounded-full bg-[var(--bg-elevated)] px-3 py-1 text-xs font-medium text-[var(--text-muted)]">
            {formatDeliveryLabel(service.delivery_mode)}
          </span>
        </div>

        {/* Description */}
        {service.description && (
          <div className="mt-6">
            <p className="whitespace-pre-wrap text-[var(--text-secondary)] leading-relaxed">{service.description}</p>
          </div>
        )}
      </div>

      {/* Details grid */}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Service Area */}
        {service.service_area && Object.keys(service.service_area).length > 0 && (
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">Service Area</h3>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              {typeof service.service_area === "object"
                ? [service.service_area.city, service.service_area.state, service.service_area.country]
                    .filter(Boolean)
                    .join(", ") || "Contact for availability"
                : "Contact for availability"}
            </p>
          </div>
        )}

        {/* Requirements */}
        {service.qualification_requirements && Object.keys(service.qualification_requirements).length > 0 && (
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">Requirements</h3>
            <ul className="mt-2 space-y-1">
              {Object.entries(service.qualification_requirements).map(([key, value]) => (
                <li key={key} className="text-sm text-[var(--text-secondary)]">
                  <span className="font-medium text-[var(--text-primary)]">{key}:</span> {String(value)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Enquiry CTA */}
      <div className="mt-6 rounded-xl border border-[var(--accent)]/20 bg-[var(--bg-surface)] p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-[var(--text-primary)]">Interested in this service?</h3>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Send an enquiry directly to {service.business_name}. They&apos;ll respond to discuss your needs.
            </p>
          </div>
          {!showEnquiry && (
            <button
              onClick={() => {
                if (!authed) {
                  router.push(`/login?redirect=/business/${params.slug}/services/${params.offerSlug}`);
                  return;
                }
                setShowEnquiry(true);
              }}
              className="shrink-0 rounded-lg bg-[var(--accent)] px-6 py-3 text-sm font-semibold text-white hover:bg-[var(--accent-hover)]"
            >
              Start Enquiry
            </button>
          )}
        </div>

        {/* Enquiry form */}
        {showEnquiry && (
          <form onSubmit={handleEnquirySubmit} className="mt-6 space-y-4">
            {enquiryError && (
              <div className="rounded-md bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">{enquiryError}</div>
            )}
            {enquirySuccess && (
              <div className="rounded-md bg-emerald-500/10 p-3 text-sm text-emerald-400">
                Enquiry sent! You&apos;ll be redirected to the conversation.
              </div>
            )}
            <div>
              <label htmlFor="subject" className="block text-sm font-medium text-[var(--text-primary)]">
                Subject
              </label>
              <input
                id="subject"
                type="text"
                value={enquirySubject}
                onChange={(e) => setEnquirySubject(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                required
              />
            </div>
            <div>
              <label htmlFor="message" className="block text-sm font-medium text-[var(--text-primary)]">
                Message
              </label>
              <textarea
                id="message"
                rows={4}
                value={enquiryMessage}
                onChange={(e) => setEnquiryMessage(e.target.value)}
                placeholder="Describe what you need, when you need it, and any relevant details..."
                className="mt-1 block w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                required
              />
            </div>
            <div className="flex gap-3">
              <button
                type="submit"
                disabled={enquirySending || !enquiryMessage.trim()}
                className="rounded-lg bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[var(--accent-hover)] disabled:opacity-50"
              >
                {enquirySending ? "Sending..." : "Send Enquiry"}
              </button>
              <button
                type="button"
                onClick={() => setShowEnquiry(false)}
                className="rounded-lg border border-[var(--border-default)] px-4 py-2.5 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Back links */}
      <div className="mt-8 flex items-center gap-4">
        <Link href={`/business/${service.business_slug}`} className="text-sm text-[var(--accent)] hover:underline">
          &larr; Back to {service.business_name}
        </Link>
        <Link href="/network" className="text-sm text-[var(--text-muted)] hover:text-[var(--accent)]">
          Browse network
        </Link>
      </div>
    </div>
  );
}
