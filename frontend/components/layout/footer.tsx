import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-border">
      <div className="container flex flex-col items-center justify-between gap-2 py-6 text-sm text-muted-foreground md:flex-row">
        <p>&copy; {new Date().getFullYear()} Construction Intel. MVP scaffold -- not for production use yet.</p>
        <div className="flex gap-4">
          <Link href="/search" className="hover:text-foreground">
            Search
          </Link>
          <Link href="/dashboard" className="hover:text-foreground">
            Dashboard
          </Link>
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="hover:text-foreground"
          >
            Docs
          </a>
        </div>
      </div>
    </footer>
  );
}
