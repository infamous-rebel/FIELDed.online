"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  businesses,
  categories,
  serviceOffers,
  type BusinessSummary,
  type ServiceCategory,
  type ServiceOffer,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";

const DELIVERY_MODES = [
  { value: "on_site", label: "On Site" },
  { value: "remote", label: "Remote" },
  { value: "in_store", label: "In Store" },
  { value: "hybrid", label: "Hybrid" },
];

const PRICING_MODELS = [
  { value: "fixed", label: "Fixed Price" },
  { value: "hourly", label: "Hourly Rate" },
  { value: "starting_at", label: "Starting At" },
  { value: "quote_required", label: "Quote Required" },
  { value: "custom", label: "Custom" },
];

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
  active: "bg-emerald-500/15 text-emerald-400",
  paused: "bg-amber-500/15 text-amber-400",
  archived: "bg-red-500/15 text-red-400",
};

export default function BusinessServicesPage() {
  const [authed, setAuthed] = useState(false);
  const [business, setBusiness] = useState<BusinessSummary | null>(null);
  const [offers, setOffers] = useState<ServiceOffer[]>([]);
  const [allCategories, setAllCategories] = useState<ServiceCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingOffer, setEditingOffer] = useState<ServiceOffer | null>(null);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formCategoryId, setFormCategoryId] = useState("");
  const [formDeliveryMode, setFormDeliveryMode] = useState("on_site");
  const [formPricingModel, setFormPricingModel] = useState("quote_required");
  const [formSaving, setFormSaving] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const bizList = await businesses.list();
      if (bizList.length === 0) {
        setError("No business found. Create one first.");
        return;
      }
      setBusiness(bizList[0]);

      const [offersData, catsData] = await Promise.all([
        serviceOffers.list(bizList[0].id),
        categories.list(),
      ]);
      setOffers(offersData);
      setAllCategories(catsData);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed) loadData();
  }, [authed, loadData]);

  const resetForm = () => {
    setFormName("");
    setFormDescription("");
    setFormCategoryId("");
    setFormDeliveryMode("on_site");
    setFormPricingModel("quote_required");
    setFormError("");
    setEditingOffer(null);
    setShowForm(false);
  };

  const startEdit = (offer: ServiceOffer) => {
    setEditingOffer(offer);
    setFormName(offer.name);
    setFormDescription(offer.description || "");
    setFormCategoryId(offer.category_id || "");
    setFormDeliveryMode(offer.delivery_mode);
    setFormPricingModel(offer.pricing_model);
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!business) return;

    try {
      setFormSaving(true);
      setFormError("");

      const data = {
        name: formName,
        description: formDescription || undefined,
        category_id: formCategoryId || undefined,
        delivery_mode: formDeliveryMode,
        pricing_model: formPricingModel,
      };

      if (editingOffer) {
        await serviceOffers.update(business.id, editingOffer.id, data);
      } else {
        await serviceOffers.create(business.id, data);
      }

      resetForm();
      await loadData();
    } catch (err) {
      setFormError(err instanceof FieldedApiError ? err.error.message : "Failed to save");
    } finally {
      setFormSaving(false);
    }
  };

  const handleTransition = async (offerId: string, targetStatus: string) => {
    if (!business) return;
    try {
      await serviceOffers.transition(business.id, offerId, targetStatus);
      await loadData();
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Transition failed");
    }
  };

  if (!authed) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12">
        <p className="text-[var(--text-secondary)]">Please sign in to manage your services.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12">
        <p className="text-[var(--text-secondary)]">Loading...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Service Offers</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Create and manage your service offerings. These are what customers see and enquire about.
          </p>
          {business && (
            <div className="mt-2 flex items-center gap-3">
              <Link
                href={`/business/${business.slug}`}
                target="_blank"
                className="text-xs font-medium text-[var(--accent)] hover:underline"
              >
                View public profile &rarr;
              </Link>
              <Link
                href="/network"
                target="_blank"
                className="text-xs text-[var(--text-muted)] hover:text-[var(--accent)]"
              >
                Browse network
              </Link>
            </div>
          )}
        </div>
        <button
          onClick={() => { resetForm(); setShowForm(true); }}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--accent-hover)]"
        >
          New Service
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">{error}</div>
      )}

      {/* Create/Edit Form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="mt-6 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {editingOffer ? "Edit Service" : "New Service"}
          </h2>
          {formError && (
            <div className="mt-2 rounded-md border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-2 text-sm text-[var(--danger)]">{formError}</div>
          )}
          <div className="mt-4 space-y-4">
            <div>
              <label htmlFor="offerName" className="block text-sm font-medium text-[var(--text-primary)]">Service Name</label>
              <input
                id="offerName"
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                className="mt-1 block w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                required
              />
            </div>
            <div>
              <label htmlFor="offerDesc" className="block text-sm font-medium text-[var(--text-primary)]">Description</label>
              <textarea
                id="offerDesc"
                rows={3}
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                className="mt-1 block w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label htmlFor="offerCat" className="block text-sm font-medium text-[var(--text-primary)]">Category</label>
                <select
                  id="offerCat"
                  value={formCategoryId}
                  onChange={(e) => setFormCategoryId(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                >
                  <option value="">No category</option>
                  {allCategories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="offerDelivery" className="block text-sm font-medium text-[var(--text-primary)]">Delivery Mode</label>
                <select
                  id="offerDelivery"
                  value={formDeliveryMode}
                  onChange={(e) => setFormDeliveryMode(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                >
                  {DELIVERY_MODES.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="offerPricing" className="block text-sm font-medium text-[var(--text-primary)]">Pricing Model</label>
                <select
                  id="offerPricing"
                  value={formPricingModel}
                  onChange={(e) => setFormPricingModel(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                >
                  {PRICING_MODELS.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              disabled={formSaving}
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--accent-hover)] disabled:opacity-50"
            >
              {formSaving ? "Saving..." : editingOffer ? "Update" : "Create"}
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="rounded-md border border-[var(--border-default)] px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Service List */}
      <div className="mt-6 space-y-3">
        {offers.length === 0 && (
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-8 text-center">
            <p className="text-sm text-[var(--text-muted)]">No service offers yet. Create your first one to start appearing in customer searches.</p>
          </div>
        )}
        {offers.map((offer) => (
          <div
            key={offer.id}
            className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h3 className="truncate font-medium text-[var(--text-primary)]">{offer.name}</h3>
                <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[offer.status] || "bg-[var(--bg-elevated)] text-[var(--text-muted)]"}`}>
                  {offer.status}
                </span>
                {offer.status === "active" && business && (
                  <Link
                    href={`/business/${business.slug}/services/${offer.slug}`}
                    target="_blank"
                    className="text-[10px] text-[var(--accent)] hover:underline"
                  >
                    Preview
                  </Link>
                )}
              </div>
              <p className="mt-1 truncate text-sm text-[var(--text-secondary)]">
                {offer.description || "No description"}
                {offer.category_id && ` \u00b7 Category: ${allCategories.find(c => c.id === offer.category_id)?.name || "\u2014"}`}
                {" \u00b7 "}{DELIVERY_MODES.find(m => m.value === offer.delivery_mode)?.label || offer.delivery_mode}
                {" \u00b7 "}{PRICING_MODELS.find(m => m.value === offer.pricing_model)?.label || offer.pricing_model}
              </p>
            </div>
            <div className="ml-4 flex shrink-0 items-center gap-2">
              {offer.status === "draft" && (
                <button
                  onClick={() => handleTransition(offer.id, "active")}
                  className="rounded-md bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-700"
                >
                  Publish
                </button>
              )}
              {offer.status === "active" && (
                <button
                  onClick={() => handleTransition(offer.id, "paused")}
                  className="rounded-md bg-yellow-500 px-3 py-1 text-xs font-medium text-white hover:bg-yellow-600"
                >
                  Pause
                </button>
              )}
              {offer.status === "paused" && (
                <button
                  onClick={() => handleTransition(offer.id, "active")}
                  className="rounded-md bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-700"
                >
                  Resume
                </button>
              )}
              {offer.status !== "archived" && (
                <button
                  onClick={() => handleTransition(offer.id, "archived")}
                  className="rounded-md border border-[var(--danger)]/30 px-3 py-1 text-xs font-medium text-[var(--danger)] hover:bg-[var(--danger)]/10"
                >
                  Archive
                </button>
              )}
              {offer.status !== "archived" && (
                <button
                  onClick={() => startEdit(offer)}
                  className="rounded-md border border-[var(--border-default)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
                >
                  Edit
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
