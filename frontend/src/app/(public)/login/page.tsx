"use client";

import { useState, FormEvent, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/auth";
import { businesses, FieldedApiError } from "@/lib/api-client";

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [returnTo, setReturnTo] = useState<string | null>(null);

  useEffect(() => {
    const rt = searchParams.get("returnTo");
    if (rt) setReturnTo(rt);
  }, [searchParams]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(email, password);

      if (returnTo) {
        router.push(returnTo);
        return;
      }

      const preservedQuery = sessionStorage.getItem("fielded_query");
      if (preservedQuery) {
        router.push("/search");
        return;
      }

      try {
        const bizList = await businesses.list();
        router.push(bizList.length > 0 ? "/business/dashboard" : "/customer/dashboard");
      } catch {
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
              Secure Access
            </span>
          </div>

          <h1 className="text-xl font-bold text-[var(--text-primary)]">
            Sign In
          </h1>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            Enter your credentials to access your FIELDed account.
          </p>

          {error && (
            <div
              className="mt-4 rounded-lg border border-[var(--danger)]/20 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]"
              role="alert"
            >
              {error}
            </div>
          )}

          <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="email" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)]/40 focus:outline-none transition-colors"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5 text-sm text-[var(--text-primary)] focus:border-[var(--accent)]/40 focus:outline-none transition-colors"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>

          <div className="mt-4 pt-3 border-t border-white/[0.04] text-center">
            <p className="text-xs text-[var(--text-secondary)]">
              Don&apos;t have an account?{" "}
              <a href="/signup" className="text-[var(--accent)] font-medium hover:underline">
                Sign up
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
