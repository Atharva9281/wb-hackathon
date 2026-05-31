import { Link } from "@tanstack/react-router";

export function Navbar() {
  return (
    <header className="sticky top-0 z-30 w-full border-b border-border bg-white">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <Link to="/" className="text-[15px] font-semibold tracking-tight text-charcoal">
          QueryMind
        </Link>
        <nav className="flex items-center gap-1">
          <Link
            to="/dashboard"
            className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition hover:text-charcoal"
            activeProps={{ className: "rounded-md px-3 py-1.5 text-sm text-charcoal font-medium" }}
          >
            Dashboard
          </Link>
          <Link
            to="/economics"
            className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition hover:text-charcoal"
            activeProps={{ className: "rounded-md px-3 py-1.5 text-sm text-charcoal font-medium" }}
          >
            Economics
          </Link>
          <Link
            to="/dashboard"
            className="ml-2 rounded-full bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-[#1d4ed8]"
          >
            Try it →
          </Link>
        </nav>
      </div>
    </header>
  );
}
