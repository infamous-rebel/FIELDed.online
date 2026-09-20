import React from "react";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "danger" | "info" | "muted";
  className?: string;
}

const variantClasses: Record<string, string> = {
  default: "bg-[var(--bg-elevated)] text-[var(--text-secondary)]",
  success: "bg-emerald-500/15 text-emerald-400",
  warning: "bg-amber-500/15 text-amber-400",
  danger: "bg-red-500/15 text-red-400",
  info: "bg-blue-500/15 text-blue-400",
  muted: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
};

/**
 * Map enquiry status strings to badge variants.
 */
export function statusBadgeVariant(
  status: string
): BadgeProps["variant"] {
  switch (status.toUpperCase()) {
    case "SUBMITTED":
    case "RECEIVED":
    case "ISSUED":
    case "REQUESTED":
      return "info";
    case "IN_REVIEW":
    case "NEEDS_INFORMATION":
    case "PROPOSED":
      return "warning";
    case "ACCEPTED":
    case "CONFIRMED":
    case "COMPLETED":
      return "success";
    case "CANCELLED":
    case "DECLINED":
    case "EXPIRED":
    case "NO_SHOW":
    case "VOID":
    case "OVERDUE":
      return "danger";
    case "DRAFT":
    case "UNPAID":
      return "muted";
    case "SCHEDULED":
    case "IN_PROGRESS":
    case "PARTIAL":
    case "ISSUED":
      return "info";
    case "PAID":
    case "REFUNDED":
    case "SUCCEEDED":
      return "success";
    case "PENDING":
    case "PROCESSING":
      return "info";
    case "FAILED":
    case "PARTIALLY_REFUNDED":
      return "danger";
    default:
      return "default";
  }
}

export function Badge({
  children,
  variant = "default",
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${variantClasses[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
