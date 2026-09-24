"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  businesses,
  type BusinessDetail,
  type BusinessProfileData,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

export default function BusinessProfilePage() {
  const [authed, setAuthed] = useState(false);
  const [business, setBusiness] = useState<BusinessDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [facebook, setFacebook] = useState("");
  const [instagram, setInstagram] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [addressLine1, setAddressLine1] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [country, setCountry] = useState("");
  const [publicStatus, setPublicStatus] = useState("incomplete");
  const [logoUrl, setLogoUrl] = useState("");
  const [coverImageUrl, setCoverImageUrl] = useState("");
  const [serviceArea, setServiceArea] = useState("");

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  const loadBusiness = useCallback(async () => {
    try {
      setLoading(true);
      const bizList = await businesses.list();
      if (bizList.length === 0) {
        setError("No business found. Create one first.");
        return;
      }
      const detail = await businesses.get(bizList[0].id);
      setBusiness(detail);
      setName(detail.name);

      if (detail.profile) {
        const p = detail.profile;
        setDescription(p.description || "");
        setPhone(p.phone || "");
        setEmail(p.email || "");
        setWebsite(p.social_links?.website || "");
        setFacebook(p.social_links?.facebook || "");
        setInstagram(p.social_links?.instagram || "");
        setLinkedin(p.social_links?.linkedin || "");
        setAddressLine1(p.address_line1 || "");
        setCity(p.city || "");
        setState(p.state || "");
        setPostalCode(p.postal_code || "");
        setCountry(p.country || "");
        setPublicStatus(p.public_status);
        setLogoUrl(p.logo_url || "");
        setCoverImageUrl(p.cover_image_url || "");
        setServiceArea(p.service_area ? JSON.stringify(p.service_area, null, 2) : "");
      }
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed) loadBusiness();
  }, [authed, loadBusiness]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!business) return;

    try {
      setSaving(true);
      setError("");
      setSuccess("");

      // Update business name
      await businesses.update(business.id, { name });

      // Update profile
      let parsedServiceArea: Record<string, unknown> | null = null;
      if (serviceArea.trim()) {
        try {
          parsedServiceArea = JSON.parse(serviceArea);
        } catch {
          setError("Service area must be valid JSON (e.g. {\"cities\": [\"Austin\"]}).");
          setSaving(false);
          return;
        }
      }

      await businesses.updateProfile(business.id, {
        description: description || null,
        phone: phone || null,
        email: email || null,
        address_line1: addressLine1 || null,
        city: city || null,
        state: state || null,
        postal_code: postalCode || null,
        country: country || null,
        public_status: publicStatus,
        logo_url: logoUrl || null,
        cover_image_url: coverImageUrl || null,
        service_area: parsedServiceArea,
        social_links: {
          website: website || null,
          facebook: facebook || null,
          instagram: instagram || null,
          linkedin: linkedin || null,
        },
      });

      setSuccess("Profile saved successfully.");
      await loadBusiness();
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (!authed) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <p className="text-[var(--text-secondary)]">Please sign in to manage your business profile.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <LoadingSkeleton lines={2} />
        <div className="mt-8">
          <LoadingSkeleton variant="card" />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-12">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Business Profile</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Manage your public-facing business information.
          </p>
          {business && publicStatus === "active" && (
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
                See in network
              </Link>
            </div>
          )}
        </div>
        {business && publicStatus === "active" && (
          <span className="inline-flex items-center rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-400">
            Publicly visible
          </span>
        )}
        {business && publicStatus !== "active" && (
          <span className="inline-flex items-center rounded-full bg-[var(--bg-elevated)] px-2.5 py-1 text-xs font-medium text-[var(--text-muted)]">
            Not publicly visible
          </span>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-md bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">{error}</div>
      )}
      {success && (
        <div className="mt-4 rounded-md bg-emerald-500/10 p-3 text-sm text-emerald-400">{success}</div>
      )}

      <form onSubmit={handleSave} className="mt-6 space-y-8">
        {/* Basic Info */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Basic Information</h2>
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-[var(--text-primary)]">
              Business Name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              required
            />
          </div>
          <div>
            <label htmlFor="description" className="block text-sm font-medium text-[var(--text-primary)]">
              Description
            </label>
            <textarea
              id="description"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={2000}
              className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            />
          </div>
          <div>
            <label htmlFor="publicStatus" className="block text-sm font-medium text-[var(--text-primary)]">
              Public Profile Status
            </label>
            <select
              id="publicStatus"
              value={publicStatus}
              onChange={(e) => setPublicStatus(e.target.value)}
              className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            >
              <option value="incomplete">Incomplete (not publicly visible)</option>
              <option value="active">Active (publicly visible)</option>
            </select>
          </div>
        </section>

        {/* Contact */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Contact Information</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="phone" className="block text-sm font-medium text-[var(--text-primary)]">Phone</label>
              <input id="phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-[var(--text-primary)]">Email</label>
              <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
          </div>
        </section>

        {/* Address */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Address</h2>
          <div>
            <label htmlFor="addressLine1" className="block text-sm font-medium text-[var(--text-primary)]">Address</label>
            <input id="addressLine1" type="text" value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)} className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="city" className="block text-sm font-medium text-[var(--text-primary)]">City</label>
              <input id="city" type="text" value={city} onChange={(e) => setCity(e.target.value)} className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
            <div>
              <label htmlFor="state" className="block text-sm font-medium text-[var(--text-primary)]">State</label>
              <input id="state" type="text" value={state} onChange={(e) => setState(e.target.value)} className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
            <div>
              <label htmlFor="postalCode" className="block text-sm font-medium text-[var(--text-primary)]">Postal Code</label>
              <input id="postalCode" type="text" value={postalCode} onChange={(e) => setPostalCode(e.target.value)} className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
          </div>
          <div>
            <label htmlFor="country" className="block text-sm font-medium text-[var(--text-primary)]">Country</label>
            <input id="country" type="text" value={country} onChange={(e) => setCountry(e.target.value)} className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
          </div>
        </section>

        {/* Branding */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Branding</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="logoUrl" className="block text-sm font-medium text-[var(--text-primary)]">Logo URL</label>
              <input id="logoUrl" type="url" value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)} placeholder="https://cdn.example.com/logo.png" className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
            <div>
              <label htmlFor="coverImageUrl" className="block text-sm font-medium text-[var(--text-primary)]">Cover Image URL</label>
              <input id="coverImageUrl" type="url" value={coverImageUrl} onChange={(e) => setCoverImageUrl(e.target.value)} placeholder="https://cdn.example.com/cover.jpg" className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
          </div>
        </section>

        {/* Service Area (advanced) */}
        <section className="space-y-4">
          <details className="group">
            <summary className="cursor-pointer text-lg font-semibold text-[var(--text-primary)] select-none">
              Service Area <span className="font-normal text-[var(--text-muted)] text-sm">(advanced)</span>
            </summary>
            <div className="mt-4">
              <label htmlFor="serviceArea" className="block text-sm font-medium text-[var(--text-primary)]">
                Service Area Configuration <span className="font-normal text-[var(--text-muted)]">(JSON)</span>
              </label>
              <textarea
                id="serviceArea"
                rows={3}
                value={serviceArea}
                onChange={(e) => setServiceArea(e.target.value)}
                placeholder='{ "cities": ["Austin", "Round Rock"] }'
                className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 font-mono text-sm shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              />
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Define the geographic areas your business serves.
              </p>
            </div>
          </details>
        </section>

        {/* Social Links */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Online Presence</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="website" className="block text-sm font-medium text-[var(--text-primary)]">Website</label>
              <input id="website" type="url" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://example.com" className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
            <div>
              <label htmlFor="facebook" className="block text-sm font-medium text-[var(--text-primary)]">Facebook</label>
              <input id="facebook" type="url" value={facebook} onChange={(e) => setFacebook(e.target.value)} placeholder="https://facebook.com/..." className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
            <div>
              <label htmlFor="instagram" className="block text-sm font-medium text-[var(--text-primary)]">Instagram</label>
              <input id="instagram" type="url" value={instagram} onChange={(e) => setInstagram(e.target.value)} placeholder="https://instagram.com/..." className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
            <div>
              <label htmlFor="linkedin" className="block text-sm font-medium text-[var(--text-primary)]">LinkedIn</label>
              <input id="linkedin" type="url" value={linkedin} onChange={(e) => setLinkedin(e.target.value)} placeholder="https://linkedin.com/company/..." className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 shadow-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]" />
            </div>
          </div>
        </section>

        <div>
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[var(--accent-hover)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2 focus:ring-offset-[var(--bg-primary)] disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save Profile"}
          </button>
        </div>
      </form>
    </div>
  );
}
