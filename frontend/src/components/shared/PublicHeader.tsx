"use client";

import { useState, useEffect } from "react";
import { isAuthenticated } from "@/lib/auth";

export default function PublicHeader() {
  const [authed, setAuthed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 glass-subtle">
      <div className="mx-auto max-w-[1400px] px-6 h-12 flex items-center justify-between">
        <a href="/" className="flex items-center gap-2.5">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--accent)] text-[10px] font-bold text-white">
            F
          </div>
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            FIELDed
          </span>
        </a>

        {/* Desktop nav */}
        <nav className="hidden sm:flex items-center gap-1">
          <a
            href="/search"
            className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            Search
          </a>
          <a
            href="/network"
            className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            Network
          </a>
          <a
            href="/industries"
            className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            Industries
          </a>
          <span className="mx-1 h-3 w-px bg-[var(--border-default)]" aria-hidden="true" />
          {authed ? (
            <a
              href="/customer/dashboard"
              className="px-3 py-1.5 text-xs font-medium text-[var(--accent)] border border-[var(--accent)]/30 rounded-md hover:bg-[var(--accent)]/10 transition-colors"
            >
              Dashboard
            </a>
          ) : (
            <>
              <a
                href="/login"
                className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                Sign In
              </a>
              <a
                href="/signup"
                className="ml-1 px-3 py-1.5 text-xs font-medium text-[var(--accent)] border border-[var(--accent)]/30 rounded-md hover:bg-[var(--accent)]/10 transition-colors"
              >
                Get Started &rarr;
              </a>
            </>
          )}
        </nav>

        {/* Mobile hamburger */}
        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="sm:hidden flex items-center justify-center h-8 w-8 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          aria-label="Toggle navigation"
          aria-expanded={mobileOpen}
        >
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {mobileOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="sm:hidden border-t border-white/[0.04] bg-[var(--bg-primary)]/95 backdrop-blur-xl">
          <nav className="flex flex-col px-6 py-3 gap-1">
            <a href="/search" className="py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors" onClick={() => setMobileOpen(false)}>Search</a>
            <a href="/network" className="py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors" onClick={() => setMobileOpen(false)}>Network</a>
            <a href="/industries" className="py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors" onClick={() => setMobileOpen(false)}>Industries</a>
            <div className="my-1 h-px bg-[var(--border-subtle)]" />
            {authed ? (
              <a href="/customer/dashboard" className="py-2 text-sm font-medium text-[var(--accent)]" onClick={() => setMobileOpen(false)}>Dashboard</a>
            ) : (
              <>
                <a href="/login" className="py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors" onClick={() => setMobileOpen(false)}>Sign In</a>
                <a href="/signup" className="py-2 text-sm font-medium text-[var(--accent)]" onClick={() => setMobileOpen(false)}>Get Started &rarr;</a>
              </>
            )}
          </nav>
        </div>
      )}
    </header>
  );
}
