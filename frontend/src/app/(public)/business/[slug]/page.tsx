import { publicApi, type PublicBusinessProfile } from "@/lib/api-client";
import Link from "next/link";
import StartEnquiryButton from "./start-enquiry-button";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getPublicBusiness(slug: string): Promise<PublicBusinessProfile | null> {
  try {
    const res = await fetch(`${API_URL}/api/v1/public/business/${slug}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

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

export default async function PublicBusinessProfilePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const business = await getPublicBusiness(slug);

  if (!business) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Business Not Found</h1>
        <p className="mt-2 text-[var(--text-secondary)]">
          The business &ldquo;{slug}&rdquo; could not be found or is not currently public.
        </p>
        <Link href="/network" className="mt-4 inline-block text-sm text-[var(--accent)] hover:underline">
          &larr; Browse the network
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* Cover + Header */}
      <div className="relative overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        {business.cover_image_url && (
          <div className="h-48 w-full bg-[var(--bg-elevated)]">
            <img
              src={business.cover_image_url}
              alt={`${business.name} cover`}
              className="h-full w-full object-cover"
            />
          </div>
        )}
        <div className={`flex items-end gap-5 p-6 ${business.cover_image_url ? "-mt-14 relative z-10" : ""}`}>
          {business.logo_url ? (
            <img
              src={business.logo_url}
              alt={`${business.name} logo`}
              className="h-24 w-24 rounded-xl border-4 border-[var(--bg-surface)] object-cover shadow-lg"
            />
          ) : (
            <div className="flex h-24 w-24 items-center justify-center rounded-xl border-4 border-[var(--bg-surface)] bg-[var(--accent)] text-3xl font-bold text-white shadow-lg">
              {business.name.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="flex-1 pb-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-[var(--text-primary)]">{business.name}</h1>
              {business.is_verified && (
                <span className="inline-flex items-center gap-1 rounded-full bg-[var(--accent)]/15 px-2.5 py-1 text-xs font-medium text-[var(--accent)]">
                  <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                  Verified
                </span>
              )}
            </div>
            {/* Trust row */}
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-[var(--text-muted)]">
              {business.average_rating != null && business.review_count > 0 && (
                <span className="flex items-center gap-1">
                  <span className="text-amber-400">&#9733;</span>
                  <span className="text-[var(--text-secondary)]">{business.average_rating.toFixed(1)}</span>
                  <span>({business.review_count} review{business.review_count !== 1 ? "s" : ""})</span>
                </span>
              )}
              {(business.city || business.state || business.country) && (
                <span className="flex items-center gap-1">
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {[business.city, business.state, business.country].filter(Boolean).join(", ")}
                </span>
              )}
              {business.active_offer_count > 0 && (
                <span>
                  {business.active_offer_count} service{business.active_offer_count !== 1 ? "s" : ""} available
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Description */}
      {business.description && (
        <div className="mt-6 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">About</h2>
          <p className="mt-3 whitespace-pre-wrap text-[var(--text-secondary)] leading-relaxed">{business.description}</p>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main content: Services */}
        <div className="lg:col-span-2">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Services</h2>
            {business.service_offers.length === 0 ? (
              <p className="mt-4 text-sm text-[var(--text-muted)]">No services currently available.</p>
            ) : (
              <div className="mt-4 space-y-3">
                {business.service_offers.map((offer) => (
                  <Link
                    key={offer.id}
                    href={`/business/${business.slug}/services/${offer.slug}`}
                    className="group block rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4 transition-all hover:border-[var(--accent)]/30 hover:shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <h3 className="font-medium text-[var(--text-primary)] group-hover:text-[var(--accent)]">
                          {offer.name}
                        </h3>
                        {offer.category_name && (
                          <span className="mt-1 inline-block rounded-full bg-[var(--accent)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--accent)]">
                            {offer.category_name}
                          </span>
                        )}
                        {offer.description && (
                          <p className="mt-2 text-sm text-[var(--text-secondary)] line-clamp-2">{offer.description}</p>
                        )}
                      </div>
                      <div className="shrink-0 text-right">
                        <span className="inline-block rounded bg-[var(--bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--text-muted)]">
                          {formatPricingLabel(offer.pricing_model)}
                        </span>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                        <span className="rounded bg-[var(--bg-elevated)] px-1.5 py-0.5">
                          {formatDeliveryLabel(offer.delivery_mode)}
                        </span>
                      </div>
                      <span className="text-xs font-medium text-[var(--accent)] opacity-0 transition-opacity group-hover:opacity-100">
                        View details &rarr;
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Start Enquiry CTA */}
          {business.service_offers.length > 0 && (
            <StartEnquiryButton
              businessId={business.id}
              businessSlug={business.slug}
              serviceOffers={business.service_offers.map((o) => ({
                id: o.id,
                name: o.name,
              }))}
            />
          )}

          {/* Contact */}
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">Contact</h3>
            <div className="mt-3 space-y-2">
              {business.phone && (
                <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  <svg className="h-4 w-4 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                  {business.phone}
                </div>
              )}
              {business.email && (
                <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  <svg className="h-4 w-4 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  {business.email}
                </div>
              )}
              {!business.phone && !business.email && (
                <p className="text-sm text-[var(--text-muted)]">No contact information provided</p>
              )}
            </div>
          </div>

          {/* Location */}
          {(business.city || business.state || business.country) && (
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">Location</h3>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                {[business.city, business.state, business.country].filter(Boolean).join(", ")}
              </p>
            </div>
          )}

          {/* Social Links */}
          {business.social_links && Object.values(business.social_links).some(Boolean) && (
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">Online</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {business.social_links.website && (
                  <a
                    href={business.social_links.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-full bg-[var(--bg-elevated)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--accent)]"
                  >
                    Website
                  </a>
                )}
                {business.social_links.facebook && (
                  <a
                    href={business.social_links.facebook}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-full bg-[var(--bg-elevated)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--accent)]"
                  >
                    Facebook
                  </a>
                )}
                {business.social_links.instagram && (
                  <a
                    href={business.social_links.instagram}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-full bg-[var(--bg-elevated)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--accent)]"
                  >
                    Instagram
                  </a>
                )}
                {business.social_links.linkedin && (
                  <a
                    href={business.social_links.linkedin}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-full bg-[var(--bg-elevated)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--accent)]"
                  >
                    LinkedIn
                  </a>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Back link */}
      <div className="mt-8">
        <Link href="/network" className="text-sm text-[var(--accent)] hover:underline">
          &larr; Back to network
        </Link>
      </div>
    </div>
  );
}
