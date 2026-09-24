"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  discovery,
  categories,
  type DiscoveryResponse,
  type ServiceCategory,
  FieldedApiError,
} from "@/lib/api-client";

const SEARCH_PLACEHOLDERS = [
  'I need a consultant for my startup...',
  'I need a photographer for an event...',
  'I need a developer for a website...',
  'I need a tutor for mathematics...',
  'I need a designer for a logo...',
  'I need a cleaner for my office...',
  'I need a repair service for appliances...',
  'I need a planner for a corporate event...',
];

function formatPricingLabel(pricingModel: string): string {
  const labels: Record<string, string> = {
    fixed: "Fixed Price",
    hourly: "Hourly Rate",
    starting_at: "Starting At",
    quote_required: "Quote Required",
    custom: "Custom",
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

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<DiscoveryResponse | null>(null);
  const [error, setError] = useState("");
  const [allCategories, setAllCategories] = useState<ServiceCategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [placeholderIndex, setPlaceholderIndex] = useState(0);

  // Rotate placeholder placeholder text
  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIndex((i) => (i + 1) % SEARCH_PLACEHOLDERS.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  // Restore preserved query from landing page
  useEffect(() => {
    const savedQuery = sessionStorage.getItem("fielded_query");
    if (savedQuery) {
      setQuery(savedQuery);
      sessionStorage.removeItem("fielded_query");
    }
  }, []);

  useEffect(() => {
    categories.list().then(setAllCategories).catch(() => {});
  }, []);

  const handleSearch = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() && !selectedCategory) return;

    try {
      setSearching(true);
      setError("");
      setResult(null);

      let response: DiscoveryResponse;
      if (selectedCategory && !query.trim()) {
        response = await discovery.structured({ category_slug: selectedCategory });
      } else {
        response = await discovery.search(query);
      }
      setResult(response);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }, [query, selectedCategory]);

  const handleCategorySelect = (slug: string) => {
    setSelectedCategory(slug);
    setQuery("");
    setResult(null);
    discovery
      .structured({ category_slug: slug })
      .then((res) => {
        setResult(res);
        setError("");
      })
      .catch((err) => {
        setError(err instanceof FieldedApiError ? err.error.message : "Search failed");
      });
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="text-3xl font-bold text-[var(--text-primary)]">Find a Service</h1>
      <p className="mt-2 text-[var(--text-secondary)]">
        Describe what you need in plain English, or browse by category.
      </p>

      {/* Search Form */}
      <form onSubmit={handleSearch} className="mt-8">
        <textarea
          value={query}
          onChange={(e) => { setQuery(e.target.value); setSelectedCategory(""); }}
          className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none"
          rows={3}
          placeholder={SEARCH_PLACEHOLDERS[placeholderIndex]}
        />
        <div className="mt-4 flex items-center gap-3">
          <button
            type="submit"
            disabled={searching || (!query.trim() && !selectedCategory)}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm text-white font-medium hover:bg-[var(--accent-hover)] disabled:opacity-50"
          >
            {searching ? "Searching..." : "Search"}
          </button>
          {query && (
            <button
              type="button"
              onClick={() => { setQuery(""); setResult(null); }}
              className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            >
              Clear
            </button>
          )}
        </div>
      </form>

      {/* Category Browser */}
      {allCategories.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wide">
            Browse by Category
          </h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {allCategories.map((cat) => (
              <button
                key={cat.id}
                onClick={() => handleCategorySelect(cat.slug)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  selectedCategory === cat.slug
                    ? "bg-[var(--accent)] text-white"
                    : "bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:bg-[var(--border-subtle)]"
                }`}
              >
                {cat.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-6 rounded-md bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">{error}</div>
      )}

      {/* Clarification */}
      {result?.clarification && (
        <div className="mt-6 rounded-md bg-[var(--warning)]/10 border border-[var(--warning)]/30 p-4">
          <p className="text-sm font-medium text-[var(--warning)]">Needs clarification</p>
          <p className="mt-1 text-sm text-[var(--warning)]">{result.clarification}</p>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="mt-8">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              {result.total_matches > 0
                ? `${result.total_matches} result${result.total_matches !== 1 ? "s" : ""} found`
                : "No results found"}
            </h2>
            {result.status && (
              <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                {result.status}
              </span>
            )}
          </div>

          {result.matches.length === 0 && !result.clarification && (
            <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-8 text-center">
              <p className="text-[var(--text-muted)]">
                No businesses matched your search. Try different keywords or{" "}
                <Link href="/network" className="text-[var(--accent)] hover:underline">
                  browse the network
                </Link>.
              </p>
            </div>
          )}

          <div className="mt-4 space-y-4">
            {result.matches.map((biz) => (
              <div
                key={biz.business_id}
                className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="flex items-start gap-4">
                  {/* Logo */}
                  {biz.logo_url ? (
                    <img
                      src={biz.logo_url}
                      alt={`${biz.business_name} logo`}
                      className="h-14 w-14 rounded-xl object-cover"
                    />
                  ) : (
                    <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-[var(--accent)]/15 text-xl font-bold text-[var(--accent)]">
                      {biz.business_name.charAt(0).toUpperCase()}
                    </div>
                  )}

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/business/${biz.business_slug}`}
                        className="text-lg font-semibold text-[var(--text-primary)] hover:text-[var(--accent)]"
                      >
                        {biz.business_name}
                      </Link>
                      {biz.is_verified && (
                        <span className="inline-flex items-center gap-0.5 rounded-full bg-[var(--accent)]/15 px-2 py-0.5 text-[11px] font-medium text-[var(--accent)]">
                          <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                          Verified
                        </span>
                      )}
                    </div>
                    {(biz.city || biz.state) && (
                      <p className="text-sm text-[var(--text-muted)]">
                        {[biz.city, biz.state].filter(Boolean).join(", ")}
                      </p>
                    )}
                    {biz.description && (
                      <p className="mt-1 text-sm text-[var(--text-secondary)] line-clamp-2">{biz.description}</p>
                    )}

                    {/* Matching Service Offers */}
                    {biz.service_offers.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {biz.service_offers.map((offer) => (
                          <Link
                            key={offer.id}
                            href={`/business/${biz.business_slug}/services/${offer.slug}`}
                            className="group block rounded-lg bg-[var(--bg-elevated)] p-3 transition-colors hover:bg-[var(--bg-primary)]"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-medium text-[var(--text-primary)] group-hover:text-[var(--accent)]">
                                {offer.name}
                              </span>
                              <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                                {offer.category_name && (
                                  <span className="rounded bg-[var(--accent)]/10 px-1.5 py-0.5 text-[var(--accent)]">
                                    {offer.category_name}
                                  </span>
                                )}
                                <span className="rounded bg-[var(--bg-surface)] px-1.5 py-0.5">
                                  {formatDeliveryLabel(offer.delivery_mode)}
                                </span>
                                <span className="rounded bg-[var(--bg-surface)] px-1.5 py-0.5">
                                  {formatPricingLabel(offer.pricing_model)}
                                </span>
                              </div>
                            </div>
                            {offer.description && (
                              <p className="mt-1 text-sm text-[var(--text-muted)] line-clamp-1">
                                {offer.description}
                              </p>
                            )}
                            {offer.match_reason && (
                              <p className="mt-1 text-xs text-emerald-400">
                                Match: {offer.match_reason}
                              </p>
                            )}
                          </Link>
                        ))}
                      </div>
                    )}

                    {/* View business link */}
                    <div className="mt-3">
                      <Link
                        href={`/business/${biz.business_slug}`}
                        className="text-xs font-medium text-[var(--accent)] hover:underline"
                      >
                        View full profile &rarr;
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
