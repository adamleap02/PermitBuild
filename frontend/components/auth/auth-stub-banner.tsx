import { Info } from "lucide-react";

export function AuthStubBanner() {
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-200">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <p>
        This is a UI-only scaffold. There&apos;s no real backend auth yet -- submitting just simulates
        a logged-in state in this browser. See <code className="rounded bg-black/10 px-1 dark:bg-white/10">frontend/BLOCKERS.md</code>{" "}
        for the plan to wire up <strong>NextAuth.js</strong> (free/open-source, no paid service
        required) once the backend exposes a real <code className="rounded bg-black/10 px-1 dark:bg-white/10">/auth</code> API.
      </p>
    </div>
  );
}
