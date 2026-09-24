"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  auth,
  businesses,
  communications,
  payments,
  type BusinessDetail,
  type BusinessMember,
  type ChannelConfigData,
  type MemberInvitationData,
  type PaymentData,
  type PurposeConfigData,
  type UserResponse,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";

type Tab = "identity" | "services" | "brain" | "members" | "communications" | "payments" | "security";

const TABS: { id: Tab; label: string }[] = [
  { id: "identity", label: "Profile" },
  { id: "services", label: "Services" },
  { id: "brain", label: "Business Brain" },
  { id: "members", label: "Team" },
  { id: "communications", label: "Channels" },
  { id: "payments", label: "Payments" },
  { id: "security", label: "Security" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
      <div className="mt-4">{children}</div>
    </div>
  );
}

export default function BusinessSettings() {
  const [authed, setAuthed] = useState(false);
  const [user, setUser] = useState<UserResponse | null>(null);
  const [business, setBusiness] = useState<BusinessDetail | null>(null);
  const [members, setMembers] = useState<BusinessMember[]>([]);
  const [invitations, setInvitations] = useState<MemberInvitationData[]>([]);
  const [channels, setChannels] = useState<ChannelConfigData[]>([]);
  const [purposes, setPurposes] = useState<PurposeConfigData[]>([]);
  const [recentPayments, setRecentPayments] = useState<PaymentData[]>([]);
  const [tab, setTab] = useState<Tab>("identity");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Member invite form
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("staff");
  const [memberBusy, setMemberBusy] = useState(false);
  const [memberMessage, setMemberMessage] = useState("");
  const [memberError, setMemberError] = useState("");

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const [u, bizList] = await Promise.all([
        auth.me().catch(() => null),
        businesses.list().catch(() => []),
      ]);
      setUser(u);
      if (bizList.length === 0) {
        setError("No business found. Create one first.");
        return;
      }
      const detail = await businesses.get(bizList[0].id);
      setBusiness(detail);

      // Load per-tab data; each failure is non-fatal
      businesses
        .listMembers(detail.id)
        .then(setMembers)
        .catch(() => setMembers([]));
      businesses
        .listInvitations(detail.id)
        .then(setInvitations)
        .catch(() => setInvitations([]));
      communications
        .listChannels(detail.id)
        .then(setChannels)
        .catch(() => setChannels([]));
      communications
        .listPurposes(detail.id)
        .then(setPurposes)
        .catch(() => setPurposes([]));
      payments
        .listForBusiness(detail.id, { limit: 5 })
        .then(setRecentPayments)
        .catch(() => setRecentPayments([]));
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  async function handleInviteMember(e: React.FormEvent) {
    e.preventDefault();
    if (!business) return;
    setMemberBusy(true);
    setMemberMessage("");
    setMemberError("");
    try {
      await businesses.inviteMember(business.id, memberEmail, memberRole);
      setMemberMessage(
        `Invitation sent to ${memberEmail}. They accept it from the invitation link after signing in with this email.`
      );
      setMemberEmail("");
      setMemberRole("staff");
      setInvitations(await businesses.listInvitations(business.id));
    } catch (err) {
      setMemberError(
        err instanceof FieldedApiError ? err.error.message : "Failed to send invitation"
      );
    } finally {
      setMemberBusy(false);
    }
  }

  async function handleRoleChange(memberId: string, role: string) {
    if (!business) return;
    try {
      await businesses.updateMemberRole(business.id, memberId, role);
      setMembers(await businesses.listMembers(business.id));
    } catch (err) {
      setMemberError(
        err instanceof FieldedApiError ? err.error.message : "Failed to change role"
      );
    }
  }

  async function handleRemoveMember(memberId: string, email: string | null) {
    if (!business) return;
    if (!window.confirm(`Remove member ${email || memberId}?`)) return;
    try {
      await businesses.removeMember(business.id, memberId);
      setMembers(await businesses.listMembers(business.id));
    } catch (err) {
      setMemberError(
        err instanceof FieldedApiError ? err.error.message : "Failed to remove member"
      );
    }
  }

  if (!authed) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <p className="text-[var(--text-secondary)]">Please sign in to manage business settings.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-1/3 rounded bg-[var(--bg-elevated)]" />
          <div className="h-40 rounded-xl bg-[var(--bg-elevated)]" />
        </div>
      </div>
    );
  }

  const profile = business?.profile;
  const latestProvider = recentPayments.find((p) => p.provider)?.provider;

  return (
    <div className="mx-auto max-w-4xl px-4 py-12">
      <h1 className="text-2xl font-bold text-[var(--text-primary)]">Business Settings</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Identity, members, communications, payments, and security.
      </p>

      {error && (
        <div className="mt-4 rounded-md bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="mt-6 flex gap-1 border-b border-[var(--border-default)]">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.id
                ? "border-b-2 border-[var(--accent)] text-[var(--text-primary)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6 space-y-6">
        {/* --- Identity --- */}
        {tab === "identity" && business && (
          <>
            <Section title="Business Identity">
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-[var(--text-muted)]">Name</dt>
                  <dd className="text-[var(--text-primary)]">{business.name}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-[var(--text-muted)]">Slug</dt>
                  <dd className="font-mono text-[var(--text-primary)]">{business.slug}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-[var(--text-muted)]">Public visibility</dt>
                  <dd>
                    <span
                      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        profile?.public_status === "active"
                          ? "bg-emerald-500/15 text-emerald-400"
                          : "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
                      }`}
                    >
                      {profile?.public_status || "unknown"}
                    </span>
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-[var(--text-muted)]">Contact</dt>
                  <dd className="text-[var(--text-primary)]">
                    {profile?.email || "—"} · {profile?.phone || "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-[var(--text-muted)]">Rating</dt>
                  <dd className="text-[var(--text-primary)]">
                    {profile?.average_rating != null
                      ? `${Number(profile.average_rating).toFixed(1)} (${profile.review_count})`
                      : "No reviews yet"}
                  </dd>
                </div>
              </dl>
              <div className="mt-5 flex gap-3">
                <Link
                  href="/business/profile"
                  className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--accent-hover)]"
                >
                  Edit identity
                </Link>
                {profile?.public_status === "active" && (
                  <Link
                    href={`/business/${business.slug}`}
                    target="_blank"
                    className="rounded-lg border border-[var(--border-default)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
                  >
                    View public profile
                  </Link>
                )}
              </div>
            </Section>
            <p className="text-xs text-[var(--text-muted)]">
              Operational rules (pricing, availability, qualification, policies) are governed by
              your{" "}
              <Link href="/business/brain" className="text-[var(--accent)] hover:underline">
                Business Brain
              </Link>{" "}
              — settings do not duplicate them.
            </p>
          </>
        )}

        {/* --- Services --- */}
        {tab === "services" && business && (
          <Section title="Service Offers">
            <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
              Define the services your business provides. Each service offer can have its own pricing, delivery mode, and category.
            </p>
            <div className="mt-4 flex gap-3">
              <Link
                href="/business/services"
                className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-hover)] transition-colors"
              >
                Manage Services
              </Link>
            </div>
          </Section>
        )}

        {/* --- Business Brain --- */}
        {tab === "brain" && business && (
          <Section title="Business Brain">
            <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
              Your Business Brain governs how your business operates — pricing rules, availability, policies, and qualification criteria. Configure it through a conversational interface.
            </p>
            <div className="mt-4 flex gap-3">
              <Link
                href="/business/brain"
                className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-hover)] transition-colors"
              >
                Open Business Brain
              </Link>
            </div>
          </Section>
        )}

        {/* --- Members --- */}
        {tab === "members" && business && (
          <>
            <Section title="Members">
              {members.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">No members found.</p>
              ) : (
                <ul className="divide-y divide-[var(--border-subtle)]">
                  {members.map((m) => (
                    <li key={m.id} className="flex items-center justify-between py-3">
                      <div>
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {m.user_email || m.user_id}
                        </p>
                        <p className="text-xs text-[var(--text-muted)]">
                          Joined {new Date(m.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <select
                          value={m.role}
                          onChange={(e) => handleRoleChange(m.id, e.target.value)}
                          aria-label={`Role for ${m.user_email || m.user_id}`}
                          className="rounded-md border border-[var(--border-default)] bg-[var(--bg-surface)] px-2 py-1 text-xs capitalize text-[var(--text-secondary)] focus:border-[var(--accent)] focus:outline-none"
                        >
                          <option value="staff">Staff</option>
                          <option value="admin">Admin</option>
                          <option value="owner">Owner</option>
                        </select>
                        <button
                          onClick={() => handleRemoveMember(m.id, m.user_email)}
                          className="text-xs font-medium text-[var(--danger)] hover:underline"
                        >
                          Remove
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Pending Invitations">
              {invitations.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">No pending invitations.</p>
              ) : (
                <ul className="divide-y divide-[var(--border-subtle)]">
                  {invitations.map((inv) => (
                    <li key={inv.id} className="flex items-center justify-between py-3">
                      <div>
                        <p className="text-sm font-medium text-[var(--text-primary)]">{inv.email}</p>
                        <p className="text-xs text-[var(--text-muted)]">
                          Expires {new Date(inv.expires_at).toLocaleDateString()}
                        </p>
                      </div>
                      <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium capitalize text-amber-300">
                        {inv.role} · pending
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Invite Member">
              <p className="text-xs text-[var(--text-muted)]">
                Works whether or not the person has a FIELDed account. They accept the invitation
                from the email link after signing in with that email.
              </p>
              <form onSubmit={handleInviteMember} className="mt-3 flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[200px]">
                  <label htmlFor="memberEmail" className="block text-sm font-medium text-[var(--text-primary)]">
                    Email
                  </label>
                  <input
                    id="memberEmail"
                    type="email"
                    required
                    value={memberEmail}
                    onChange={(e) => setMemberEmail(e.target.value)}
                    className="mt-1 block w-full rounded-md border border-[var(--border-default)] px-3 py-2 focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                  />
                </div>
                <div>
                  <label htmlFor="memberRole" className="block text-sm font-medium text-[var(--text-primary)]">
                    Role
                  </label>
                  <select
                    id="memberRole"
                    value={memberRole}
                    onChange={(e) => setMemberRole(e.target.value)}
                    className="mt-1 block rounded-md border border-[var(--border-default)] px-3 py-2 focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                  >
                    <option value="staff">Staff</option>
                    <option value="admin">Admin</option>
                    <option value="owner">Owner</option>
                  </select>
                </div>
                <button
                  type="submit"
                  disabled={memberBusy}
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--accent-hover)] disabled:opacity-50"
                >
                  {memberBusy ? "Sending…" : "Send Invitation"}
                </button>
              </form>
              {memberMessage && (
                <p className="mt-3 text-sm text-emerald-400">{memberMessage}</p>
              )}
              {memberError && <p className="mt-3 text-sm text-[var(--danger)]">{memberError}</p>}
            </Section>
          </>
        )}

        {/* --- Communications --- */}
        {tab === "communications" && business && (
          <>
            <Section title="Channel Preferences">
              {channels.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">No channel configuration found.</p>
              ) : (
                <ul className="divide-y divide-[var(--border-subtle)]">
                  {channels.map((c) => (
                    <li key={c.id} className="flex items-center justify-between py-3">
                      <span className="text-sm font-medium capitalize text-[var(--text-primary)]">
                        {c.channel}
                      </span>
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          c.enabled
                            ? "bg-emerald-500/15 text-emerald-400"
                            : "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
                        }`}
                      >
                        {c.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title="Notification Purposes">
              {purposes.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">No purpose configuration found.</p>
              ) : (
                <ul className="divide-y divide-[var(--border-subtle)]">
                  {purposes.map((p) => (
                    <li key={p.id} className="flex items-center justify-between py-3">
                      <span className="text-sm capitalize text-[var(--text-primary)]">
                        {p.purpose.replace(/_/g, " ")}
                      </span>
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          p.enabled
                            ? "bg-emerald-500/15 text-emerald-400"
                            : "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
                        }`}
                      >
                        {p.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <p className="text-xs text-[var(--text-muted)]">
              Channel and purpose toggles are managed on the{" "}
              <Link href="/business/communications" className="text-[var(--accent)] hover:underline">
                communications page
              </Link>
              . Operational communication rules remain governed by your Business Brain.
            </p>
          </>
        )}

        {/* --- Payments --- */}
        {tab === "payments" && business && (
          <Section title="Payments">
            <div className="flex items-center justify-between text-sm">
              <span className="text-[var(--text-muted)]">Payment provider</span>
              <span className="font-medium capitalize text-[var(--text-primary)]">
                {latestProvider ? latestProvider : "No payments yet (default provider)"}
              </span>
            </div>
            <p className="mt-4 text-sm font-medium text-[var(--text-primary)]">Recent payments</p>
            {recentPayments.length === 0 ? (
              <p className="mt-2 text-sm text-[var(--text-muted)]">No payments recorded yet.</p>
            ) : (
              <ul className="mt-2 divide-y divide-[var(--border-subtle)]">
                {recentPayments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between py-2.5 text-sm">
                    <span className="text-[var(--text-primary)]">
                      {p.currency} {p.amount}
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="capitalize text-[var(--text-muted)]">
                        {new Date(p.created_at).toLocaleDateString()}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
                          p.status === "succeeded"
                            ? "bg-emerald-500/15 text-emerald-400"
                            : p.status === "failed"
                              ? "bg-red-500/15 text-red-300"
                              : "bg-amber-500/15 text-amber-300"
                        }`}
                      >
                        {p.status.replace(/_/g, " ")}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <Link
              href="/business/payments"
              className="mt-4 inline-block text-sm font-medium text-[var(--accent)] hover:underline"
            >
              View all payments &rarr;
            </Link>
          </Section>
        )}

        {/* --- Security --- */}
        {tab === "security" && (
          <Section title="Security">
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-[var(--text-muted)]">Account email</dt>
                <dd className="text-[var(--text-primary)]">{user?.email || "—"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[var(--text-muted)]">Password</dt>
                <dd className="text-[var(--text-secondary)]">
                  Reset available via the forgot-password flow on the{" "}
                  <Link href="/login" className="text-[var(--accent)] hover:underline">
                    sign-in page
                  </Link>
                </dd>
              </div>
            </dl>
          </Section>
        )}
      </div>
    </div>
  );
}
