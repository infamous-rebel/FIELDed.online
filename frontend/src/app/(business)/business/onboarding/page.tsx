"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { businesses, type BusinessSummary } from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";

export default function BusinessOnboarding() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-generate slug from name
  function handleNameChange(value: string) {
    setName(value);
    // Simple slug generation: lowercase, replace spaces with hyphens, remove special chars
    const generatedSlug = value
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "");
    setSlug(generatedSlug);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !slug.trim()) return;

    setSubmitting(true);
    setError(null);

    try {
      const business: BusinessSummary = await businesses.create({
        name: name.trim(),
        slug: slug.trim(),
      });
      // Redirect to business profile setup or dashboard
      router.push(`/business/profile?created=${business.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create business"
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (!isAuthenticated()) {
    router.push("/login?redirect=/business/onboarding");
    return null;
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-8">
        <h1 className="text-3xl font-bold text-[var(--text-primary)]">
          Set Up Your Business
        </h1>
        <p className="mt-3 text-[var(--text-secondary)] leading-relaxed">
          Welcome to FIELDed. Create your business to start receiving enquiries,
          managing bookings, and operating through your Business Brain.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          <div>
            <label
              htmlFor="business-name"
              className="block text-sm font-medium text-[var(--text-primary)]"
            >
              Business Name
            </label>
            <input
              id="business-name"
              type="text"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="e.g. Apex Consulting, Creative Studio, Tech Repair"
              className="mt-2 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-4 py-2.5 text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              required
              maxLength={200}
            />
            <p className="mt-1.5 text-xs text-[var(--text-muted)]">
              This is how your business will appear to customers.
            </p>
          </div>

          <div>
            <label
              htmlFor="business-slug"
              className="block text-sm font-medium text-[var(--text-primary)]"
            >
              Business URL Slug
            </label>
            <div className="mt-2 flex items-center gap-2">
              <span className="text-sm text-[var(--text-muted)]">fielded.io/business/</span>
              <input
                id="business-slug"
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="your-business"
                className="flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-4 py-2.5 font-mono text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                required
                maxLength={100}
                pattern="[a-z0-9-]+"
                title="Only lowercase letters, numbers, and hyphens"
              />
            </div>
            <p className="mt-1.5 text-xs text-[var(--text-muted)]">
              A unique identifier for your business profile. Only lowercase letters, numbers, and hyphens.
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

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-[var(--accent)] px-6 py-2.5 text-sm font-semibold text-white hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors"
            >
              {submitting ? "Creating..." : "Create Business"}
            </button>
            <button
              type="button"
              onClick={() => router.push("/")}
              className="rounded-lg px-4 py-2.5 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>

        <div className="mt-8 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            What happens next?
          </h2>
          <ul className="mt-3 space-y-2 text-sm text-[var(--text-secondary)]">
            <li className="flex items-start gap-2">
              <span className="mt-1 text-[var(--accent)]">→</span>
              <span>Set up your business profile with contact details and description</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1 text-[var(--accent)]">→</span>
              <span>Configure your Business Brain to govern pricing, availability, and policies</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1 text-[var(--accent)]">→</span>
              <span>Add service offers so customers can find and enquire about your services</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1 text-[var(--accent)]">→</span>
              <span>Start receiving and managing customer enquiries</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
