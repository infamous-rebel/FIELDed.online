import React from "react";

interface LoadingSkeletonProps {
  className?: string;
  lines?: number;
  variant?: "card" | "list" | "text";
}

function PulseBlock({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-[var(--bg-elevated)] ${className}`}
    />
  );
}

export function LoadingSkeleton({
  className = "",
  lines = 3,
  variant = "text",
}: LoadingSkeletonProps) {
  if (variant === "card") {
    return (
      <div
        className={`rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 space-y-4 ${className}`}
        aria-busy="true"
        aria-label="Loading"
      >
        <PulseBlock className="h-4 w-1/3" />
        <PulseBlock className="h-3 w-2/3" />
        <PulseBlock className="h-3 w-1/2" />
        <div className="flex gap-2 pt-2">
          <PulseBlock className="h-8 w-20" />
          <PulseBlock className="h-8 w-20" />
        </div>
      </div>
    );
  }

  if (variant === "list") {
    return (
      <div
        className={`space-y-3 ${className}`}
        aria-busy="true"
        aria-label="Loading"
      >
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 flex gap-4"
          >
            <PulseBlock className="h-4 w-4 rounded-full flex-shrink-0" />
            <div className="flex-1 space-y-2">
              <PulseBlock className="h-4 w-1/3" />
              <PulseBlock className="h-3 w-2/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  // text variant
  return (
    <div
      className={`space-y-2 ${className}`}
      aria-busy="true"
      aria-label="Loading"
    >
      {Array.from({ length: lines }).map((_, i) => (
        <PulseBlock
          key={i}
          className={`h-4 ${i === lines - 1 ? "w-1/2" : "w-full"}`}
        />
      ))}
    </div>
  );
}
