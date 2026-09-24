import type { Metadata } from "next";
import CustomerNav from "./customer-nav";

export const metadata: Metadata = {
  title: "My Account — FIELDed",
  description: "Manage your enquiries, bookings, payments, and profile.",
};

export default function CustomerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <CustomerNav>{children}</CustomerNav>;
}
