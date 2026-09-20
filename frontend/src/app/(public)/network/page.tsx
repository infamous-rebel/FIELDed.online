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

  const loadBusinesses = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const params: Record<string, string | number> = { limit: 40 };
      if (selectedCategory) params.category = selectedCategory;
      if (locationFilter) params.city = locationFilter;
      const response = await publicApi.listBusinesses(params);
      setBusinesses(response.businesses);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load businesses");
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, locationFilter]);

  useEffect(() => {
    categories.list().then(setAllCategories).catch(() => {});
  }, []);

  useEffect(() => {
    loadBusinesses();
  }, [loadBusinesses]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-[var(--text-primary)]">Business Network</h1>
        <p className="mt-2 text-[var(--text-secondary)]">
          Discover trusted businesses and professional services on FIELDed.
        </p>
      </div>

      {/* Filters */}
      <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-end">
        <div className="flex-1">
          <label htmlFor="location" className="block text-sm font-medium text-[var(--text-secondary)]">
            Location
          </label>
          <input
            id="location"
            type="text"
            value={locationFilter}
            onChange={(e) => setLocationFilter(e.target.value)}
            placeholder="City name..."
            className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
          />
        </div>
        <button
          onClick={() => { setLocationFilter(""); setSelectedCategory(""); }}
          className="rounded-lg border border-[var(--border-default)] px-4 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
        >
          Clear filters
        </button>
      </div>

      {/* Category pills */}
      {allCategories.length > 0 && (
        <div className="mt-6">
          <div className="flex flex-wrap gap-2">
            {allCategories.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(selectedCategory === cat.slug ? "" : cat.slug)}
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

      {/* Results count */}
      {!loading && (
        <div className="mt-8 flex items-center justify-between">
          <p className="text-sm text-[var(--text-secondary)]">
            {total > 0 ? `${total} business${total !== 1 ? "es" : ""} found` : ""}
          </p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
              <div className="flex items-center gap-3">
                <div className="h-12 w-12 rounded-lg bg-[var(--bg-elevated)]" />
                <div className="flex-1">
                  <div className="h-4 w-3/4 rounded bg-[var(--bg-elevated)]" />
                  <div className="mt-2 h-3 w-1/2 rounded bg-[var(--bg-elevated)]" />
                </div>
              </div>
              <div className="mt-4 h-3 w-full rounded bg-[var(--bg-elevated)]" />
              <div className="mt-2 h-3 w-2/3 rounded bg-[var(--bg-elevated)]" />
            </div>
          ))}
        </div>
      )}

      {/* Business grid */}
      {!loading && businesses.length === 0 && (
        <div className="mt-8 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-12 text-center">
          <p className="text-lg font-medium text-[var(--text-primary)]">No businesses found</p>
          <p className="mt-2 text-sm text-[var(--text-muted)]">
            Try adjusting your filters or search criteria.
          </p>
        </div>
      )}

      {!loading && businesses.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {businesses.map((biz) => (
            <Link
              key={biz.slug}
              href={`/business/${biz.slug}`}
              className="group rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 transition-all hover:border-[var(--accent)]/30 hover:shadow-lg hover:shadow-[var(--accent)]/5"
            >
              <div className="flex items-start gap-3">
                {biz.logo_url ? (
                  <img
                    src={biz.logo_url}
                    alt={`${biz.name} logo`}
                    className="h-12 w-12 rounded-lg object-cover"
                  />
                ) : (
                  <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-[var(--accent)]/15 text-lg font-bold text-[var(--accent)]">
                    {biz.name.charAt(0).toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent)]">
                      {biz.name}
                    </h3>
                    {biz.is_verified && (
                      <span className="inline-flex shrink-0 items-center rounded-full bg-[var(--accent)]/15 px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent)]">
                        Verified
                      </span>
                    )}
                  </div>
                  {(biz.city || biz.state) && (
                    <p className="text-sm text-[var(--text-muted)]">
                      {[biz.city, biz.state].filter(Boolean).join(", ")}
                    </p>
                  )}
                </div>
              </div>

              {biz.description && (
                <p className="mt-3 text-sm text-[var(--text-secondary)] line-clamp-2">
                  {biz.description}
                </p>
              )}

              {/* Stats row */}
              <div className="mt-4 flex items-center gap-3 text-xs text-[var(--text-muted)]">
                {biz.active_offer_count > 0 && (
                  <span className="rounded bg-[var(--bg-elevated)] px-2 py-0.5">
                    {biz.active_offer_count} service{biz.active_offer_count !== 1 ? "s" : ""}
                  </span>
                )}
                {biz.average_rating != null && biz.review_count > 0 && (
                  <span className="flex items-center gap-1">
                    <span className="text-amber-400">&#9733;</span>
                    <span>{biz.average_rating.toFixed(1)}</span>
                    <span>({biz.review_count})</span>
                  </span>
                )}
              </div>

              {/* Categories */}
              {biz.top_categories.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {biz.top_categories.slice(0, 3).map((cat) => (
                    <span
                      key={cat}
                      className="rounded-full bg-[var(--accent)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--accent)]"
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
  );
}
