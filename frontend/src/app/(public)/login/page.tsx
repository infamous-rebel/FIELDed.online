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

      // Return to the page the user was trying to reach
      if (returnTo) {
        router.push(returnTo);
        return;
      }

      // Check for preserved enquiry context
      const preservedQuery = sessionStorage.getItem("fielded_query");
      if (preservedQuery) {
        router.push("/search");
        return;
      }

      // Default redirect: business members land on their business dashboard
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
    <div className="flex min-h-[calc(100vh-65px)]">
      {/* Left panel — light */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-[var(--auth-light-bg)] p-12">
        <div>
          <a href="/" className="text-2xl font-bold text-gray-900">
            FIELDed
          </a>
        </div>
        <div>
          <h2 className="text-3xl font-bold text-gray-900">
            Turn your need into a service.
          </h2>
          <ul className="mt-8 space-y-4">
            {[
              {
                title: "Intelligent Matching",
                description:
                  "Describe what you need — FIELDed interprets your intent and finds qualified businesses.",
              },
              {
                title: "Governed Execution",
                description:
                  "Every business operates through governed rules for pricing, availability, and policies.",
              },
            ].map((item) => (
              <li key={item.title} className="flex gap-3">
                <span
                  className="mt-2 h-2 w-2 rounded-full bg-emerald-500 flex-shrink-0"
                  aria-hidden="true"
                />
                <div>
                  <p className="font-medium text-gray-900">{item.title}</p>
                  <p className="mt-1 text-sm text-gray-600">
                    {item.description}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-gray-500">&copy; 2026 FIELDed Platform</p>
      </div>

      {/* Right panel — dark */}
      <div className="flex flex-1 items-center justify-center bg-[var(--bg-primary)] px-4 py-12">
        <div className="w-full max-w-md">
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            Sign In
          </h1>
          <p className="mt-2 text-[var(--text-secondary)]">
            Sign in to your FIELDed account.
          </p>

          {error && (
            <div
              className="mt-4 rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]"
              role="alert"
            >
              {error}
            </div>
          )}

          <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-[var(--text-primary)]"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-[var(--text-primary)]"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-[var(--accent)] px-4 py-3 text-white font-medium hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>
          <p className="mt-4 text-center text-sm text-[var(--text-secondary)]">
            Don&apos;t have an account?{" "}
            <a
              href="/signup"
              className="text-[var(--accent)] font-medium hover:underline"
            >
              Sign up
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
