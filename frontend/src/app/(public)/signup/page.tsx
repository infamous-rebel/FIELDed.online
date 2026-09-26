"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { register } from "@/lib/auth";
import { FieldedApiError } from "@/lib/api-client";

export default function SignupPage() {
  const router = useRouter();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"customer" | "business">("customer");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!termsAccepted) {
      setError("You must accept the Terms of Service and Privacy Policy.");
      return;
    }
    setError(null);
    setLoading(true);

    try {
      await register(email, password, firstName, lastName);

      const preservedQuery = sessionStorage.getItem("fielded_query");
      if (preservedQuery) {
        router.push("/search");
        return;
      }

      if (role === "business") {
        router.push("/business/dashboard");
      } else {
        router.push("/customer/dashboard");
      }
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-[calc(100vh-120px)] flex items-center justify-center px-4 py-12">
      {/* Background */}
      <div className="absolute inset-0 grid-bg opacity-30" aria-hidden="true" />
      <div
        className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[300px]"
        style={{
          background: "radial-gradient(ellipse at 50% 0%, var(--accent) 0%, transparent 65%)",
          opacity: 0.04,
        }}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-sm">
        {/* Glass card */}
        <div className="glass rounded-xl p-6">
          {/* Status indicator */}
          <div className="flex items-center gap-2 mb-4">
            <span
              className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
              style={{ animation: "status-blink 2.5s ease-in-out infinite" }}
            />
            <span className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Create Account
            </span>
          </div>

          <h1 className="text-xl font-bold text-[var(--text-primary)]">
            Get Started
          </h1>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            Join FIELDed to discover services or grow your business.
          </p>

          {error && (
            <div
              className="mt-4 rounded-lg border border-[var(--danger)]/20 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]"
              role="alert"
            >
              {error}
            </div>
          )}

          {/* Role selector */}
          <div className="mt-4 flex rounded-lg border border-white/[0.06] overflow-hidden">
            <button
              type="button"
              onClick={() => setRole("customer")}
              className={`flex-1 py-2 text-xs font-medium transition-colors ${
                role === "customer"
                  ? "bg-[var(--accent)]/15 text-[var(--accent)] border-r border-[var(--accent)]/20"
                  : "bg-white/[0.02] text-[var(--text-secondary)] hover:text-[var(--text-primary)] border-r border-white/[0.06]"
              }`}
            >
              I&apos;m a Customer
            </button>
            <button
              type="button"
              onClick={() => setRole("business")}
              className={`flex-1 py-2 text-xs font-medium transition-colors ${
                role === "business"
                  ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                  : "bg-white/[0.02] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              I&apos;m a Business
            </button>
          </div>

          <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="firstName" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                  First Name
                </label>
                <input
                  id="firstName"
                  type="text"
                  required
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="w-full rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)]/40 focus:outline-none transition-colors"
                />
              </div>
              <div>
                <label htmlFor="lastName" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                  Last Name
                </label>
                <input
                  id="lastName"
                  type="text"
                  required
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="w-full rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)]/40 focus:outline-none transition-colors"
                />
              </div>
            </div>
            <div>
              <label htmlFor="signup-email" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                Email
              </label>
              <input
                id="signup-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)]/40 focus:outline-none transition-colors"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label htmlFor="signup-password" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                Password
              </label>
              <input
                id="signup-password"
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5 text-sm text-[var(--text-primary)] focus:border-[var(--accent)]/40 focus:outline-none transition-colors"
              />
              <p className="mt-1 text-[10px] text-[var(--text-muted)]">
                Minimum 8 characters
              </p>
            </div>

            {/* Terms checkbox */}
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={termsAccepted}
                onChange={(e) => setTermsAccepted(e.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 rounded border-[var(--border-default)] bg-transparent text-[var(--accent)] focus:ring-[var(--accent)]"
              />
              <span className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
                I agree to the{" "}
                <span className="text-[var(--accent)]">Terms of Service</span>{" "}
                and{" "}
                <span className="text-[var(--accent)]">Privacy Policy</span>
              </span>
            </label>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <div className="mt-4 pt-3 border-t border-white/[0.04] text-center">
            <p className="text-xs text-[var(--text-secondary)]">
              Already have an account?{" "}
              <a href="/login" className="text-[var(--accent)] font-medium hover:underline">
                Sign in
              </a>
            </p>
          </div>
        </div>

        {/* Bottom trust indicator */}
        <div className="mt-3 flex items-center justify-center gap-3">
          {[
            { label: "Encrypted", icon: "M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" },
            { label: "Tenant Isolated", icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" },
          ].map((item) => (
            <div key={item.label} className="flex items-center gap-1">
              <svg className="h-3 w-3 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={item.icon} />
              </svg>
              <span className="text-[10px] text-[var(--text-muted)]">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
