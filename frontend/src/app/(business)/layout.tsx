import type { Metadata } from "next";
import BusinessNav from "./business-nav";

export const metadata: Metadata = {
  title: "Business Dashboard — FIELDed",
  description: "Manage your business operations, enquiries, quotes, and bookings.",
};

export default function BusinessLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <BusinessNav>{children}</BusinessNav>;
}
