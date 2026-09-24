"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  auth,
  customer,
  type UserResponse,
  type CustomerProfile,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

export default function CustomerAccountPage() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Form state
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [country, setCountry] = useState("");

  useEffect(() => {
    if (!isAuthenticated()) return;

    async function load() {
      try {
        const [userData, profileData] = await Promise.all([
          auth.me(),
          customer.getProfile().catch(() => null),
        ]);
        setUser(userData);
        setProfile(profileData);

        if (profileData) {
          setFirstName(profileData.first_name || "");
          setLastName(profileData.last_name || "");
          setPhone(profileData.phone || "");
          setCity(profileData.city || "");
          setState(profileData.state || "");
          setCountry(profileData.country || "");
        } else if (userData?.customer_profile) {
          setFirstName(userData.customer_profile.first_name || "");
          setLastName(userData.customer_profile.last_name || "");
          setPhone(userData.customer_profile.phone || "");
        }
      } catch {
        setError("Failed to load account");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const updated = await customer.updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim() || undefined,
        city: city.trim() || undefined,
        state: state.trim() || undefined,
        country: country.trim() || undefined,
      });
      setProfile(updated);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <LoadingSkeleton lines={2} />
        <LoadingSkeleton variant="card" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Account</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Manage your profile and account settings.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]" role="alert">
          {error}
        </div>
      )}

      {success && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-400" role="status">
          Profile saved successfully.
        </div>
      )}

      {/* Profile section */}
      <Card>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">Profile</h2>
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="first-name" className="block text-sm font-medium text-[var(--text-secondary)]">
                First name
              </label>
              <input
                id="first-name"
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                required
              />
            </div>
            <div>
              <label htmlFor="last-name" className="block text-sm font-medium text-[var(--text-secondary)]">
                Last name
              </label>
              <input
                id="last-name"
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                required
              />
            </div>
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-[var(--text-secondary)]">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={user?.email || ""}
              disabled
              className="mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-muted)] cursor-not-allowed"
            />
            <p className="mt-1 text-xs text-[var(--text-muted)]">Email cannot be changed.</p>
          </div>

          <div>
            <label htmlFor="phone" className="block text-sm font-medium text-[var(--text-secondary)]">
              Phone
            </label>
            <input
              id="phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Your phone number"
              className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="city" className="block text-sm font-medium text-[var(--text-secondary)]">
                City
              </label>
              <input
                id="city"
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Your city"
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              />
            </div>
            <div>
              <label htmlFor="state" className="block text-sm font-medium text-[var(--text-secondary)]">
                State / Region
              </label>
              <input
                id="state"
                type="text"
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder="Your state or region"
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              />
            </div>
            <div>
              <label htmlFor="country" className="block text-sm font-medium text-[var(--text-secondary)]">
                Country
              </label>
              <input
                id="country"
                type="text"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="Your country"
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              />
            </div>
          </div>

          <div className="pt-2">
            <Button type="submit" loading={saving}>
              Save Changes
            </Button>
          </div>
        </form>
      </Card>

      {/* Account info */}
      <Card>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">Account Info</h2>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-[var(--text-muted)]">Account ID</span>
            <span className="font-mono text-xs text-[var(--text-secondary)]">{user?.id?.slice(0, 12)}...</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--text-muted)]">Status</span>
            <span className="text-[var(--text-secondary)]">{user?.is_active ? "Active" : "Inactive"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--text-muted)]">Verified</span>
            <span className="text-[var(--text-secondary)]">{user?.is_verified ? "Yes" : "No"}</span>
          </div>
        </div>
      </Card>
    </div>
  );
}
