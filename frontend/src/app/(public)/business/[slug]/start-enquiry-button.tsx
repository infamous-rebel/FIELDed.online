"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { enquiries, type EnquiryCreateRequest } from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";

interface StartEnquiryButtonProps {
  businessId: string;
  businessSlug: string;
  serviceOffers: { id: string; name: string }[];
}

export default function StartEnquiryButton({
  businessId,
  businessSlug,
  serviceOffers,
}: StartEnquiryButtonProps) {
  const router = useRouter();
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedOfferId, setSelectedOfferId] = useState(
    serviceOffers.length === 1 ? serviceOffers[0].id : ""
  );
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");

  function handleClick() {
    if (!isAuthenticated()) {
      const returnTo = `/business/${businessSlug}`;
      sessionStorage.setItem("fielded_return_to", returnTo);
      router.push(`/login?returnTo=${encodeURIComponent(returnTo)}`);
      return;
    }
    setShowForm(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selectedOfferId || !subject.trim() || !message.trim()) return;

    setSubmitting(true);
    setError(null);

    try {
      const data: EnquiryCreateRequest = {
        service_offer_id: selectedOfferId,
        subject: subject.trim(),
        message: message.trim(),
      };
      const enquiry = await enquiries.create(businessId, data);
      router.push(`/customer/enquiries/${enquiry.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to submit enquiry"
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (showForm) {
    return (
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
        <h3 className="text-base font-semibold text-[var(--text-primary)]">
          Start an Enquiry
        </h3>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          Tell the business what you need. They&apos;ll respond with a quote or
          questions.
        </p>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          {serviceOffers.length > 1 && (
            <div>
              <label
                htmlFor="offer-select"
                className="block text-sm font-medium text-[var(--text-secondary)]"
              >
                Service
              </label>
              <select
                id="offer-select"
                value={selectedOfferId}
                onChange={(e) => setSelectedOfferId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                required
              >
                <option value="">Select a service...</option>
                {serviceOffers.map((offer) => (
                  <option key={offer.id} value={offer.id}>
                    {offer.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label
              htmlFor="enquiry-subject"
              className="block text-sm font-medium text-[var(--text-secondary)]"
            >
              Subject
            </label>
            <input
              id="enquiry-subject"
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. Need electrical wiring for kitchen"
              className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              maxLength={500}
              required
            />
          </div>

          <div>
            <label
              htmlFor="enquiry-message"
              className="block text-sm font-medium text-[var(--text-secondary)]"
            >
              What do you need?
            </label>
            <textarea
              id="enquiry-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Describe what you need done, any specific requirements, preferred timing..."
              rows={4}
              className="mt-1 w-full resize-none rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              maxLength={10000}
              required
            />
          </div>

          {error && (
            <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-400">
              {error}
            </p>
          )}

          <div className="flex items-center gap-3 pt-1">
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors"
            >
              {submitting ? "Submitting..." : "Submit Enquiry"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-lg px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <button
      onClick={handleClick}
      className="w-full rounded-xl bg-[var(--accent)] px-5 py-3 text-sm font-semibold text-white hover:bg-[var(--accent-hover)] transition-colors"
    >
      Start an Enquiry
    </button>
  );
}
