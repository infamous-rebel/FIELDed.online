"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  auth,
  enquiries,
  bookings,
  reviews,
  type UserResponse,
  type EnquiryData,
  type BookingData,
  type ReviewData,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { statusToTextColor } from "@/lib/status";

interface DashboardData {
  enquiries: EnquiryData[];
  bookings: BookingData[];
  reviews: ReviewData[];
}

export default function CustomerDashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }

    async function load() {
      try {
        const [u, enqs, bks, revs] = await Promise.all([
          auth.me(),
          enquiries.listMine({ limit: 5 }).catch(() => [] as EnquiryData[]),
          bookings.listMine().catch(() => [] as BookingData[]),
          reviews.listMine({ limit: 5 }).catch(() => [] as ReviewData[]),
        ]);
        setUser(u);
        setData({ enquiries: enqs, bookings: bks, reviews: revs });
      } catch (err) {
        if (err instanceof FieldedApiError && err.status === 401) {
          router.push("/login");
        }
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [router]);

  async function handleLogout() {
    const { logout } = await import("@/lib/auth");
    await logout();
    router.push("/login");
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8">
        <LoadingSkeleton lines={2} />
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <LoadingSkeleton key={i} variant="card" />
          ))}
        </div>
      </div>
    );
  }

  if (!user || !data) return null;

  const activeEnquiries = data.enquiries.filter((e) =>
    ["submitted", "received", "in_review", "quoted", "needs_information"].includes(e.status)
  );
  const upcomingBookings = data.bookings.filter((b) =>
    ["confirmed", "in_progress", "requested", "proposed", "accepted"].includes(b.status)
  );
  const completedServices = data.bookings.filter((b) => b.status === "completed");

  // Recent activity: combine enquiries and bookings, sort by date, take 3
  const recentItems = [
    ...data.enquiries.map((e) => ({
      type: "enquiry" as const,
      id: e.id,
      label: `Enquiry ${e.reference}`,
      status: e.status,
      date: e.created_at,
    })),
    ...data.bookings.map((b) => ({
      type: "booking" as const,
      id: b.id,
      label: `Booking ${b.reference}`,
      status: b.status,
      date: b.created_at,
    })),
  ]
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 3);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            Welcome, {user.customer_profile?.first_name || "Customer"}
          </h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{user.email}</p>
        </div>
        <button
          onClick={handleLogout}
          className="rounded-lg border border-[var(--border-default)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
        >
          Sign Out
        </button>
      </div>

      {/* Summary cards */}
      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
          <p className="text-sm text-[var(--text-muted)]">Active Enquiries</p>
          <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">{activeEnquiries.length}</p>
        </div>
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
          <p className="text-sm text-[var(--text-muted)]">Upcoming Bookings</p>
          <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">{upcomingBookings.length}</p>
        </div>
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
          <p className="text-sm text-[var(--text-muted)]">Completed</p>
          <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">{completedServices.length}</p>
        </div>
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
          <p className="text-sm text-[var(--text-muted)]">Reviews</p>
          <p className="mt-1 text-3xl font-bold text-[var(--text-primary)]">{data.reviews.length}</p>
        </div>
      </div>

      {/* Recent activity + Quick actions */}
      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent activity */}
        <div className="lg:col-span-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Recent Activity</h2>
          {recentItems.length === 0 ? (
            <p className="mt-4 text-sm text-[var(--text-muted)]">No activity yet. Browse the network to get started.</p>
          ) : (
            <ul className="mt-4 space-y-3">
              {recentItems.map((item) => (
                <li key={`${item.type}-${item.id}`} className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">{item.label}</p>
                    <p className="text-xs text-[var(--text-muted)]">
                      {new Date(item.date).toLocaleDateString()}
                    </p>
                  </div>
                  <span className={`text-xs font-medium capitalize ${statusToTextColor(item.status)}`}>
                    {item.status.replace(/_/g, " ")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Quick actions */}
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Quick Actions</h2>
          <div className="mt-4 space-y-3">
            <Link
              href="/search"
              className="block rounded-lg bg-[var(--accent)] px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-[var(--accent-hover)]"
            >
              Find a Service
            </Link>
            <Link
              href="/customer/enquiries"
              className="block rounded-lg border border-[var(--border-default)] px-4 py-2.5 text-center text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
            >
              My Enquiries
            </Link>
            <Link
              href="/customer/transactions"
              className="block rounded-lg border border-[var(--border-default)] px-4 py-2.5 text-center text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
            >
              Transaction History
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
