import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FIELDed — Find Services, Connect with Businesses",
  description:
    "Customer-to-business service network. Describe what you need, discover businesses, get quotes, and book services.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
