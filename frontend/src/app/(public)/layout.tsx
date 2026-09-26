import type { Metadata } from "next";
import PublicHeader from "@/components/shared/PublicHeader";
import PublicFooter from "@/components/shared/PublicFooter";

export const metadata: Metadata = {
  title: {
    default: "FIELDed — Find Services, Connect with Businesses",
    template: "%s — FIELDed",
  },
  description:
    "Describe what you need in plain language. FIELDed matches you with qualified businesses instantly.",
};

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col">
      <PublicHeader />
      <main className="flex-1 pt-12">
        {children}
      </main>
      <PublicFooter />
    </div>
  );
}
