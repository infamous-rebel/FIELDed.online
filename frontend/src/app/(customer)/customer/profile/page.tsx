"use client";

import { useState, useEffect, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { customer as customerApi, type CustomerProfile, FieldedApiError } from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

export default function CustomerProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Form state
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [addressLine1, setAddressLine1] = useState("");
  const [addressLine2, setAddressLine2] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [country, setCountry] = useState("");

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    async function loadProfile() {
      try {
        const p = await customerApi.getProfile();
        setProfile(p);
        setFirstName(p.first_name);
        setLastName(p.last_name);
        setPhone(p.phone || "");
        setAddressLine1(p.address_line1 || "");
        setAddressLine2(p.address_line2 || "");
        setCity(p.city || "");
        setState(p.state || "");
        setPostalCode(p.postal_code || "");
        setCountry(p.country || "");
      } catch (err) {
        if (err instanceof FieldedApiError && err.status === 401) {
          router.push("/login");
        } else {
          setError("Failed to load profile");
        }
      } finally {
        setLoading(false);
      }
    }

    loadProfile();
  }, [router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSaving(true);

    try {
      const updated = await customerApi.updateProfile({
        first_name: firstName,
        last_name: lastName,
        phone: phone || undefined,
        address_line1: addressLine1 || undefined,
        address_line2: addressLine2 || undefined,
        city: city || undefined,
        state: state || undefined,
        postal_code: postalCode || undefined,
        country: country || undefined,
      });
      setProfile(updated);
      setSuccess("Profile updated successfully");
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to update profile");
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">My Profile</h1>
        <div className="mt-8">
          <LoadingSkeleton variant="card" />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-bold text-[var(--text-primary)]">My Profile</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Status: <span className="font-medium capitalize">{profile?.status}</span>
      </p>

      {error && (
        <div className="mt-4 rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      )}
      {success && (
        <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-400">
          {success}
        </div>
      )}

      <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="firstName" className="block text-sm font-medium text-[var(--text-primary)]">First Name</label>
            <input id="firstName" type="text" required value={firstName} onChange={(e) => setFirstName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
          </div>
          <div>
            <label htmlFor="lastName" className="block text-sm font-medium text-[var(--text-primary)]">Last Name</label>
            <input id="lastName" type="text" required value={lastName} onChange={(e) => setLastName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
          </div>
        </div>

        <div>
          <label htmlFor="phone" className="block text-sm font-medium text-[var(--text-primary)]">Phone</label>
          <input id="phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
            className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
        </div>

        <div>
          <label htmlFor="address1" className="block text-sm font-medium text-[var(--text-primary)]">Address Line 1</label>
          <input id="address1" type="text" value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)}
            className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
        </div>

        <div>
          <label htmlFor="address2" className="block text-sm font-medium text-[var(--text-primary)]">Address Line 2</label>
          <input id="address2" type="text" value={addressLine2} onChange={(e) => setAddressLine2(e.target.value)}
            className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="city" className="block text-sm font-medium text-[var(--text-primary)]">City</label>
            <input id="city" type="text" value={city} onChange={(e) => setCity(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
          </div>
          <div>
            <label htmlFor="state" className="block text-sm font-medium text-[var(--text-primary)]">State</label>
            <input id="state" type="text" value={state} onChange={(e) => setState(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="postalCode" className="block text-sm font-medium text-[var(--text-primary)]">Postal Code</label>
            <input id="postalCode" type="text" value={postalCode} onChange={(e) => setPostalCode(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
          </div>
          <div>
            <label htmlFor="country" className="block text-sm font-medium text-[var(--text-primary)]">Country</label>
            <input id="country" type="text" value={country} onChange={(e) => setCountry(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--border-default)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none" />
          </div>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="w-full rounded-lg bg-[var(--accent)] px-4 py-3 text-white font-medium hover:bg-[var(--accent-hover)] disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </form>
    </div>
  );
}
