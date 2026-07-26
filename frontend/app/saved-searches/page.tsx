import { Info } from "lucide-react";

import { SavedSearchForm } from "@/components/saved-searches/saved-search-form";
import { SavedSearchList } from "@/components/saved-searches/saved-search-list";

export default function SavedSearchesPage() {
  return (
    <div className="container max-w-3xl space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">Saved searches</h1>
        <p className="text-sm text-muted-foreground">
          Re-run a previous set of filters any time, or save new ones with the full filter
          sidebar from the Search page.
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          UI-only stub: saved searches persist in this browser&apos;s local storage. The backend
          doesn&apos;t have a <code className="rounded bg-black/10 px-1 dark:bg-white/10">/saved-searches</code> endpoint
          yet -- see BLOCKERS.md. This will switch to real server-side persistence transparently
          once it does.
        </p>
      </div>

      <SavedSearchForm />
      <SavedSearchList />
    </div>
  );
}
