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
  "I need a consultant for my startup...",
  "I need a photographer for an event...",
  "I need a developer for a website...",
  "I need a tutor for mathematics...",
  "I need a designer for a logo...",
  "I need a cleaner for my office...",
  "I need a repair service for appliances...",
  "I need a planner for a corporate event...",
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

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIndex((i) => (i + 1) % SEARCH_PLACEHOLDERS.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

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
    <div className="relative">
      {/* Subtle grid background */}
      <div className="absolute inset-0 grid-bg opacity-50" aria-hidden="true" />
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px]"
        style={{
          background: "radial-gradient(ellipse at 50% 0%, var(--accent) 0%, transparent 65%)",
          opacity: 0.05,
        }}
        aria-hidden="true"
      />

      <div className="relative mx-auto max-w-[1400px] px-6 pt-10 pb-16">
        {/* Page header */}
        <div className="max-w-2xl">
          <div className="flex items-center gap-2 mb-3">
            <span
              className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
              style={{ animation: "status-blink 2.5s ease-in-out infinite" }}
            />
            <span className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Customer Search
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)] lg:text-3xl">
            Describe what you need.
          </h1>
          <p className="mt-1.5 text-sm text-[var(--text-secondary)] max-w-lg">
            Plain-language intent matched against business capabilities — no forms, no categories required.
          </p>
        </div>

        {/* Search interaction — landing page style */}
        <form
          onSubmit={handleSearch}
          className="mt-5 flex items-center gap-0 glass rounded-lg overflow-hidden max-w-xl"
        >
          <div className="flex items-center gap-2 flex-1 px-4">
            <svg
              className="h-4 w-4 text-[var(--text-muted)] flex-shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setSelectedCategory(""); }}
              placeholder={SEARCH_PLACEHOLDERS[placeholderIndex]}
              className="w-full bg-transparent py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none"
              aria-label="Describe your service need"
            />
          </div>
          <button
            type="submit"
            disabled={searching || (!query.trim() && !selectedCategory)}
            className="flex items-center gap-1.5 px-4 py-3 text-sm font-medium text-[var(--accent)] border-l border-white/5 hover:bg-[var(--accent)]/10 transition-colors whitespace-nowrap disabled:opacity-40"
          >
            {searching ? "Searching..." : "Search"}
            {!searching && (
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            )}
          </button>
        </form>

        {/* Flow preview capsules */}
        <div className="mt-4 flex items-center gap-2 flex-wrap">
          {[
            { label: "Intent", color: "var(--accent)" },
            { label: "Match", color: "var(--info)" },
            { label: "Enquiry", color: "var(--warning)" },
            { label: "Governed", color: "var(--accent)" },
          ].map((node, i) => (
            <div key={node.label} className="flex items-center gap-2">
              <div className="glass-subtle rounded-md px-2.5 py-1 flex items-center gap-1.5">
                <span className="h-1 w-1 rounded-full" style={{ backgroundColor: node.color }} />
                <span className="text-[10px] font-medium text-[var(--text-secondary)]">{node.label}</span>
              </div>
              {i < 3 && (
                <svg className="h-3 w-3 text-[var(--text-muted)] opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
          ))}
        </div>

        {/* Category browser */}
        {allCategories.length > 0 && (
          <div className="mt-6">
            <span className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Browse by category
            </span>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {allCategories.map((cat) => (
                <button
                  key={cat.id}
                  onClick={() => handleCategorySelect(cat.slug)}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors border ${
                    selectedCategory === cat.slug
                      ? "bg-[var(--accent)]/15 text-[var(--accent)] border-[var(--accent)]/30"
                      : "bg-white/[0.02] text-[var(--text-secondary)] border-white/[0.05] hover:border-[var(--accent)]/20 hover:text-[var(--text-primary)]"
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
          <div className="mt-6 rounded-lg bg-[var(--danger)]/10 border border-[var(--danger)]/20 p-3 text-sm text-[var(--danger)]">
            {error}
          </div>
        )}

        {/* Clarification */}
        {result?.clarification && (
          <div className="mt-6 rounded-lg bg-[var(--warning)]/10 border border-[var(--warning)]/20 p-4">
            <p className="text-sm font-medium text-[var(--warning)]">Needs clarification</p>
            <p className="mt-1 text-sm text-[var(--warning)]">{result.clarification}</p>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="mt-8">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                  {result.total_matches > 0
                    ? `${result.total_matches} result${result.total_matches !== 1 ? "s" : ""}`
                    : "No results"}
                </h2>
                {result.status && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.03] text-[var(--text-muted)] border border-white/[0.04]">
                    {result.status}
                  </span>
                )}
              </div>
            </div>

            {/* Empty state */}
            {result.matches.length === 0 && !result.clarification && (
              <div className="glass rounded-lg p-8 text-center">
                <div className="flex items-center justify-center mb-3">
                  <div className="h-10 w-10 rounded-lg bg-[var(--accent)]/10 flex items-center justify-center">
                    <svg className="h-5 w-5 text-[var(--accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  </div>
                </div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  No businesses matched your search yet
                </p>
                <p className="mt-1.5 text-xs text-[var(--text-muted)] max-w-sm mx-auto leading-relaxed">
                  As businesses join FIELDed and configure their services, they will appear here.
                  Try different keywords or{" "}
                  <Link href="/network" className="text-[var(--accent)] hover:underline">
                    browse the network
                  </Link>{" "}
                  to see what is available.
                </p>
              </div>
            )}

            {/* Match cards */}
            <div className="space-y-2">
              {result.matches.map((biz) => (
                <div
                  key={biz.business_id}
                  className="glass rounded-lg p-4 hover:border-[var(--accent)]/20 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    {/* Logo */}
                    {biz.logo_url ? (
                      <img
                        src={biz.logo_url}
                        alt={`${biz.business_name} logo`}
                        className="h-10 w-10 rounded-lg object-cover flex-shrink-0"
                      />
                    ) : (
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--accent)]/15 text-sm font-bold text-[var(--accent)] flex-shrink-0">
                        {biz.business_name.charAt(0).toUpperCase()}
                      </div>
                    )}

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/business/${biz.business_slug}`}
                          className="text-sm font-semibold text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
                        >
                          {biz.business_name}
                        </Link>
                        {biz.is_verified && (
                          <span className="inline-flex items-center gap-0.5 rounded-md bg-[var(--accent)]/10 px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent)] border border-[var(--accent)]/20">
                            <svg className="h-2.5 w-2.5" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                            Verified
                          </span>
                        )}
                        {(biz.city || biz.state) && (
                          <span className="text-[10px] text-[var(--text-muted)]">
                            {[biz.city, biz.state].filter(Boolean).join(", ")}
                          </span>
                        )}
                      </div>
                      {biz.description && (
                        <p className="mt-1 text-xs text-[var(--text-secondary)] line-clamp-1">{biz.description}</p>
                      )}

                      {/* Matching Service Offers */}
                      {biz.service_offers.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {biz.service_offers.map((offer) => (
                            <Link
                              key={offer.id}
                              href={`/business/${biz.business_slug}/services/${offer.slug}`}
                              className="group flex items-center gap-2 rounded-md bg-white/[0.02] border border-white/[0.03] px-3 py-2 transition-colors hover:border-[var(--accent)]/15 hover:bg-white/[0.04]"
                            >
                              <span className="text-xs font-medium text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors flex-1 min-w-0 truncate">
                                {offer.name}
                              </span>
                              <div className="flex items-center gap-1.5 text-[10px] text-[var(--text-muted)] flex-shrink-0">
                                {offer.category_name && (
                                  <span className="rounded bg-[var(--accent)]/10 px-1.5 py-0.5 text-[var(--accent)]">
                                    {offer.category_name}
                                  </span>
                                )}
                                <span className="rounded bg-white/[0.03] px-1.5 py-0.5">
                                  {formatDeliveryLabel(offer.delivery_mode)}
                                </span>
                                <span className="rounded bg-white/[0.03] px-1.5 py-0.5">
                                  {formatPricingLabel(offer.pricing_model)}
                                </span>
                              </div>
                              {offer.match_reason && (
                                <span className="text-[10px] text-[var(--accent)] flex-shrink-0">
                                  {offer.match_reason}
                                </span>
                              )}
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* View profile link */}
                    <Link
                      href={`/business/${biz.business_slug}`}
                      className="text-[10px] font-medium text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors flex-shrink-0"
                    >
                      Profile &rarr;
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Default empty state when no search has been performed */}
        {!result && !searching && !error && (
          <div className="mt-10 glass rounded-lg p-6 text-center">
            <p className="text-xs text-[var(--text-muted)] leading-relaxed max-w-md mx-auto">
              Enter a description of what you need above, or select a category.
              FIELDed will match your intent against business capabilities and service offers.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
