/**
 * Shared status-to-visual mappings for the FIELDed application.
 *
 * Provides a single source of truth for status colours used by
 * Badge components and inline text status indicators.
 */

import { type BadgeProps } from "@/components/ui/badge";

/**
 * Map a domain status string to a Badge variant.
 *
 * Covers enquiry, quote, booking, service-execution, invoice,
 * payment, and review statuses.
 */
export function statusToBadgeVariant(
  status: string,
): BadgeProps["variant"] {
  switch (status.toLowerCase()) {
    // Enquiry / general flow
    case "submitted":
    case "received":
    case "issued":
    case "requested":
    case "pending":
    case "processing":
      return "info";
    case "in_review":
    case "needs_information":
    case "proposed":
    case "in_progress":
    case "scheduled":
    case "partial":
      return "warning";
    case "accepted":
    case "confirmed":
    case "completed":
    case "customer_accepted":
    case "booked":
    case "paid":
    case "refunded":
    case "succeeded":
      return "success";
    case "cancelled":
    case "declined":
    case "expired":
    case "no_show":
    case "void":
    case "overdue":
    case "failed":
    case "partially_refunded":
    case "rejected":
      return "danger";
    case "draft":
    case "unpaid":
      return "muted";
    default:
      return "default";
  }
}

/**
 * Map a domain status string to Tailwind text-colour classes.
 *
 * Use when a Badge component is not appropriate (e.g. inline text
 * in a list row).
 */
export function statusToTextColor(status: string): string {
  switch (status.toLowerCase()) {
    case "draft":
    case "cancelled":
    case "expired":
      return "text-[var(--text-muted)]";
    case "submitted":
    case "received":
    case "in_review":
    case "requested":
    case "pending":
    case "processing":
      return "text-blue-400";
    case "needs_information":
    case "proposed":
    case "quoted":
    case "booking_proposed":
    case "in_progress":
    case "scheduled":
    case "partial":
      return "text-amber-400";
    case "accepted":
    case "confirmed":
    case "completed":
    case "customer_accepted":
    case "booked":
    case "paid":
    case "refunded":
    case "succeeded":
      return "text-emerald-400";
    case "declined":
    case "rejected":
    case "failed":
    case "no_show":
    case "void":
    case "overdue":
    case "partially_refunded":
      return "text-[var(--danger)]";
    default:
      return "text-[var(--text-secondary)]";
  }
}
