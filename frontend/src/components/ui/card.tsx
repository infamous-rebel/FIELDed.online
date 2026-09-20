import React from "react";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: "sm" | "md" | "lg";
  hover?: boolean;
}

const paddingClasses: Record<string, string> = {
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
};

export function Card({
  children,
  className = "",
  padding = "md",
  hover = false,
}: CardProps) {
  return (
    <div
      className={`rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] ${paddingClasses[padding]} ${
        hover ? "transition-colors hover:border-[var(--border-default)]" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}
