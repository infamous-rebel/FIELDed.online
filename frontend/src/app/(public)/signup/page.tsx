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

      // Check for preserved enquiry context
      const preservedQuery = sessionStorage.getItem("fielded_query");
      if (preservedQuery) {
        router.push("/search");
        return;
      }

      // Role-based redirect
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
            Create Account
          </h1>
          <p className="mt-2 text-[var(--text-secondary)]">
            Join FIELDed to find and book services.
          </p>

          {error && (
            <div
              className="mt-4 rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]"
              role="alert"
            >
              {error}
            </div>
          )}

          {/* Role selector */}
          <div className="mt-6 flex rounded-lg border border-[var(--border-default)] overflow-hidden">
            <button
              type="button"
              onClick={() => setRole("customer")}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                role === "customer"
                  ? "bg-[var(--accent)] text-white"
                  : "bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              I&apos;m a Customer
            </button>
            <button
              type="button"
              onClick={() => setRole("business")}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                role === "business"
                  ? "bg-[var(--accent)] text-white"
                  : "bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              I&apos;m a Business
            </button>
          </div>

          <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="firstName"
                  className="block text-sm font-medium text-[var(--text-primary)]"
                >
                  First Name
                </label>
                <input
                  id="firstName"
                  type="text"
                  required
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                />
              </div>
              <div>
                <label
                  htmlFor="lastName"
                  className="block text-sm font-medium text-[var(--text-primary)]"
                >
                  Last Name
                </label>
                <input
                  id="lastName"
                  type="text"
                  required
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                />
              </div>
            </div>
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
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
              />
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Minimum 8 characters
              </p>
            </div>

            {/* Terms checkbox */}
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={termsAccepted}
                onChange={(e) => setTermsAccepted(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--accent)] focus:ring-[var(--accent)]"
              />
              <span className="text-sm text-[var(--text-secondary)]">
                I agree to the{" "}
                <span className="text-[var(--accent)]">Terms of Service</span>{" "}
                and{" "}
                <span className="text-[var(--accent)]">Privacy Policy</span>
              </span>
            </label>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-[var(--accent)] px-4 py-3 text-white font-medium hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>
          <p className="mt-4 text-center text-sm text-[var(--text-secondary)]">
            Already have an account?{" "}
            <a
              href="/login"
              className="text-[var(--accent)] font-medium hover:underline"
            >
              Sign in
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
