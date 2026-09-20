"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { businesses, FieldedApiError } from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";

/**
 * Member invitation acceptance.
 *
 * The invited person opens the link from their invitation email. If they
 * are not signed in yet, they sign in (or register) with the invited email
 * first, then reopen this link and accept.
 */
export default function AcceptInvitationPage() {
  const [token, setToken] = useState<string | null>(null);
  const [authed, setAuthed] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("token"));
    setAuthed(isAuthenticated());
  }, []);

  async function handleAccept() {
    if (!token) return;
    setAccepting(true);
    setError(null);
    try {
      await businesses.acceptInvitation(token);
      setAccepted(true);
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to accept invitation");
      }
    } finally {
      setAccepting(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-20">
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-8">
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          Business Invitation
        </h1>

        {!token && (
          <p className="mt-4 text-sm text-[var(--text-secondary)]">
            This link is missing its invitation token. Please use the exact link
            from your invitation email.
          </p>
        )}

        {token && accepted && (
          <div className="mt-4">
            <p className="text-sm text-emerald-400">
              Invitation accepted — you are now a member of the business.
            </p>
            <Link
              href="/business/dashboard"
              className="mt-4 inline-block rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--accent-hover)]"
            >
              Go to Business Dashboard
            </Link>
          </div>
        )}

        {token && !accepted && !authed && (
          <div className="mt-4">
            <p className="text-sm text-[var(--text-secondary)]">
              You need to be signed in with the invited email address to accept
              this invitation. If you don&apos;t have an account yet, register
              with that email first.
            </p>
            <div className="mt-4 flex gap-3">
              <Link
                href="/login"
                className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--accent-hover)]"
              >
                Sign In
              </Link>
              <Link
                href="/register"
                className="rounded-lg border border-[var(--border-default)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
              >
                Register
              </Link>
            </div>
            <p className="mt-4 text-xs text-[var(--text-muted)]">
              After signing in, reopen the invitation link from your email to
              accept.
            </p>
          </div>
        )}

        {token && !accepted && authed && (
          <div className="mt-4">
            <p className="text-sm text-[var(--text-secondary)]">
              You can accept this invitation with the account you are signed in
              as. It must match the invited email address.
            </p>
            <button
              onClick={handleAccept}
              disabled={accepting}
              className="mt-4 rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--accent-hover)] disabled:opacity-50"
            >
              {accepting ? "Accepting…" : "Accept Invitation"}
            </button>
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-md bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
