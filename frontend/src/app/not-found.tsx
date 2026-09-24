import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold tracking-tight">Page not found</h1>
        <p className="mt-4 text-lg opacity-70">
          The page you are looking for does not exist or has been moved.
        </p>
        <Link
          href="/"
          className="mt-8 inline-block rounded-lg bg-[var(--brand)] px-6 py-3 font-semibold text-white transition hover:opacity-90"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}
