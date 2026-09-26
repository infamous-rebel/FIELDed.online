"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  publicApi,
  categories,
  type PublicBusinessDirectoryItem,
  type ServiceCategory,
  FieldedApiError,
} from "@/lib/api-client";

export default function NetworkPage() {
  const [businesses, setBusinesses] = useState<PublicBusinessDirectoryItem[]>([]);
  const [allCategories, setAllCategories] = useState<ServiceCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [total, setTotal] = useState(0);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [minRating, setMinRating] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [sortBy, setSortBy] = useState("name");

  const loadBusinesses = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const params: Record<string, string | number | boolean> = { limit: 40 };
      if (selectedCategory) params.category = selectedCategory;
      if (locationFilter) params.city = locationFilter;
      if (searchFilter) params.search = searchFilter;
      if (minRating) params.min_rating = parseFloat(minRating);
      if (verifiedOnly) params.verified_only = true;
      params.sort = sortBy;
      const response = await publicApi.listBusinesses(params);
      setBusinesses(response.businesses);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load businesses");
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, locationFilter, searchFilter, minRating, verifiedOnly, sortBy]);

  useEffect(() => {
    categories.list().then(setAllCategories).catch(() => {});
  }, []);

  useEffect(() => {
    loadBusinesses();
  }, [loadBusinesses]);

  const clearFilters = () => {
    setLocationFilter("");
    setSelectedCategory("");
    setSearchFilter("");
    setMinRating("");
    setVerifiedOnly(false);
    setSortBy("name");
  };

  const hasActiveFilters = selectedCategory || locationFilter || searchFilter || minRating || verifiedOnly;

  return (
    <div className="relative">
      {/* Background */}
      <div className="absolute inset-0 grid-bg opacity-30" aria-hidden="true" />

      <div className="relative mx-auto max-w-[1400px] px-6 pt-10 pb-16">
        {/* Page header */}
        <div className="max-w-2xl">
          <div className="flex items-center gap-2 mb-3">
            <span
              className="h-1.5 w-1.5 rounded-full bg-[var(--info)]"
              style={{ animation: "status-blink 2.5s ease-in-out infinite" }}
            />
            <span className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Business Network
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)] lg:text-3xl">
            Discover businesses on FIELDed.
          </h1>
          <p className="mt-1.5 text-sm text-[var(--text-secondary)] max-w-lg">
            Browse verified businesses, their services, and capabilities — filtered and sorted to your needs.
          </p>
        </div>

        {/* Compact filter bar */}
        <div className="mt-5 glass rounded-lg p-3">
          <div className="flex flex-col sm:flex-row gap-2">
            {/* Search */}
            <div className="flex-1 flex items-center gap-2 px-3 rounded-md bg-white/[0.03] border border-white/[0.05]">
              <svg className="h-3.5 w-3.5 text-[var(--text-muted)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Business name or description..."
                className="w-full bg-transparent py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none"
              />
            </div>
            {/* Location */}
            <div className="flex items-center gap-2 px-3 rounded-md bg-white/[0.03] border border-white/[0.05] sm:w-40">
              <svg className="h-3.5 w-3.5 text-[var(--text-muted)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <input
                type="text"
                value={locationFilter}
                onChange={(e) => setLocationFilter(e.target.value)}
                placeholder="City..."
                className="w-full bg-transparent py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none"
              />
            </div>
            {/* Rating */}
            <select
              value={minRating}
              onChange={(e) => setMinRating(e.target.value)}
              className="rounded-md bg-white/[0.03] border border-white/[0.05] px-3 py-2 text-xs text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]/30 sm:w-28"
            >
              <option value="">Any rating</option>
              <option value="3">3+</option>
              <option value="3.5">3.5+</option>
              <option value="4">4+</option>
              <option value="4.5">4.5+</option>
            </select>
            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="rounded-md bg-white/[0.03] border border-white/[0.05] px-3 py-2 text-xs text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]/30 sm:w-28"
            >
              <option value="name">Name</option>
              <option value="rating">Rating</option>
              <option value="review_count">Reviews</option>
              <option value="newest">Newest</option>
            </select>
          </div>
          {/* Second row: verified + clear */}
          <div className="mt-2 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={verifiedOnly}
                  onChange={(e) => setVerifiedOnly(e.target.checked)}
                  className="h-3 w-3 rounded border-[var(--border-default)] bg-transparent text-[var(--accent)] focus:ring-[var(--accent)]"
                />
                <span className="text-[10px] font-medium text-[var(--text-secondary)]">Verified only</span>
              </label>
            </div>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-[10px] font-medium text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        {/* Category pills */}
        {allCategories.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {allCategories.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(selectedCategory === cat.slug ? "" : cat.slug)}
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
        )}

        {/* Error */}
        {error && (
          <div className="mt-6 rounded-lg bg-[var(--danger)]/10 border border-[var(--danger)]/20 p-3 text-sm text-[var(--danger)]">
            {error}
          </div>
        )}

        {/* Results count */}
        {!loading && (
          <div className="mt-6 flex items-center gap-2">
            <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
              {total > 0 ? `${total} business${total !== 1 ? "es" : ""} found` : ""}
            </span>
          </div>
        )}

        {/* Loading skeletons */}
        {loading && (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="glass rounded-lg p-4 animate-pulse">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-white/[0.05]" />
                  <div className="flex-1">
                    <div className="h-3.5 w-3/4 rounded bg-white/[0.05]" />
                    <div className="mt-1.5 h-2.5 w-1/2 rounded bg-white/[0.03]" />
                  </div>
                </div>
                <div className="mt-3 h-2.5 w-full rounded bg-white/[0.03]" />
                <div className="mt-1.5 h-2.5 w-2/3 rounded bg-white/[0.03]" />
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && businesses.length === 0 && (
          <div className="mt-6 glass rounded-lg p-8 text-center">
            <div className="flex items-center justify-center mb-3">
              <div className="h-10 w-10 rounded-lg bg-[var(--info)]/10 flex items-center justify-center">
                <svg className="h-5 w-5 text-[var(--info)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
              </div>
            </div>
            <p className="text-sm font-medium text-[var(--text-primary)]">
              No businesses found
            </p>
            <p className="mt-1.5 text-xs text-[var(--text-muted)] max-w-sm mx-auto leading-relaxed">
              The Network will surface relevant businesses and services as they join FIELDed.
              Try adjusting your filters or check back soon.
            </p>
          </div>
        )}

        {/* Business grid */}
        {!loading && businesses.length > 0 && (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {businesses.map((biz) => (
              <Link
                key={biz.slug}
                href={`/business/${biz.slug}`}
                className="group glass rounded-lg p-4 hover:border-[var(--accent)]/20 transition-colors"
              >
                <div className="flex items-start gap-3">
                  {biz.logo_url ? (
                    <img
                      src={biz.logo_url}
                      alt={`${biz.name} logo`}
                      className="h-10 w-10 rounded-lg object-cover flex-shrink-0"
                    />
                  ) : (
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--accent)]/15 text-sm font-bold text-[var(--accent)] flex-shrink-0">
                      {biz.name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="truncate text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors">
                        {biz.name}
                      </h3>
                      {biz.is_verified && (
                        <span className="inline-flex shrink-0 items-center gap-0.5 rounded-md bg-[var(--accent)]/10 px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent)] border border-[var(--accent)]/20">
                          <svg className="h-2.5 w-2.5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                          Verified
                        </span>
                      )}
                    </div>
                    {(biz.city || biz.state) && (
                      <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
                        {[biz.city, biz.state].filter(Boolean).join(", ")}
                      </p>
                    )}
                  </div>
                </div>

                {biz.description && (
                  <p className="mt-2 text-xs text-[var(--text-secondary)] line-clamp-2 leading-relaxed">
                    {biz.description}
                  </p>
                )}

                {/* Stats row */}
                <div className="mt-3 flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
                  {biz.active_offer_count > 0 && (
                    <span className="rounded bg-white/[0.03] border border-white/[0.04] px-1.5 py-0.5">
                      {biz.active_offer_count} service{biz.active_offer_count !== 1 ? "s" : ""}
                    </span>
                  )}
                  {biz.average_rating != null && biz.review_count > 0 && (
                    <span className="flex items-center gap-1">
                      <span className="text-amber-400">&#9733;</span>
                      <span>{biz.average_rating.toFixed(1)}</span>
                      <span className="text-[var(--text-muted)]">({biz.review_count})</span>
                    </span>
                  )}
                </div>

                {/* Categories */}
                {biz.top_categories.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {biz.top_categories.slice(0, 3).map((cat) => (
                      <span
                        key={cat}
                        className="rounded bg-[var(--accent)]/8 px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent)]"
                      >
                        {cat}
                      </span>
                    ))}
                  </div>
                )}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
