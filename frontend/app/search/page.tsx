"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { Bell, Download, Save } from "lucide-react";

import type { PermitSearchParams } from "@/lib/types";
import { buildExportUrl } from "@/lib/api";
import { usePermitsSearch } from "@/lib/hooks/use-permits";
import { useCreateSavedSearch } from "@/lib/hooks/use-saved-searches";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FilterSidebar } from "@/components/search/filter-sidebar";
import { Pagination } from "@/components/search/pagination";
import { ResultsMap } from "@/components/search/results-map";
import { ResultsTable } from "@/components/search/results-table";
import { ViewToggle, type SearchView } from "@/components/search/view-toggle";

const DEFAULT_PARAMS: PermitSearchParams = { page: 1, page_size: 25 };

const STRING_KEYS = [
  "keyword", "city", "county", "zip", "contractor", "builder", "architect",
  "permit_type", "status", "property_type", "date_from", "date_to",
] as const;
const NUMBER_KEYS = ["radius_miles", "min_value", "max_value", "jurisdiction_id", "page", "page_size"] as const;

/** Parses a Saved Search / shared "Run search" link's querystring back into filters. */
function paramsFromSearchParams(sp: URLSearchParams): PermitSearchParams {
  const params: PermitSearchParams = { ...DEFAULT_PARAMS };
  for (const key of STRING_KEYS) {
    const v = sp.get(key);
    if (v) (params as Record<string, unknown>)[key] = v;
  }
  for (const key of NUMBER_KEYS) {
    const v = sp.get(key);
    if (v && !Number.isNaN(Number(v))) (params as Record<string, unknown>)[key] = Number(v);
  }
  const occupied = sp.get("owner_occupied");
  if (occupied === "yes" || occupied === "no" || occupied === "any") params.owner_occupied = occupied;
  return params;
}

function SearchPageInner() {
  const urlParams = useSearchParams();
  const [filters, setFilters] = React.useState<PermitSearchParams>(() =>
    paramsFromSearchParams(urlParams)
  );
  const [view, setView] = React.useState<SearchView>("list");
  const [saveDialogOpen, setSaveDialogOpen] = React.useState(false);
  const [saveName, setSaveName] = React.useState("");

  const { data, isLoading, isFetching, isError, error } = usePermitsSearch(filters);
  const createSavedSearch = useCreateSavedSearch();

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageSize = filters.page_size ?? 25;
  const page = filters.page ?? 1;

  function handleApply(next: PermitSearchParams) {
    setFilters(next);
  }

  function handleReset() {
    setFilters(DEFAULT_PARAMS);
  }

  function handlePageChange(nextPage: number) {
    setFilters((f) => ({ ...f, page: nextPage }));
  }

  async function handleSaveSearch() {
    if (!saveName.trim()) return;
    await createSavedSearch.mutateAsync({ name: saveName.trim(), params: filters });
    setSaveName("");
    setSaveDialogOpen(false);
  }

  return (
    <div className="container flex flex-col gap-6 py-8 lg:flex-row">
      <aside className="w-full shrink-0 lg:w-72">
        <Card className="p-4 lg:sticky lg:top-24">
          <h2 className="mb-4 font-semibold">Filters</h2>
          <FilterSidebar value={filters} onApply={handleApply} onReset={handleReset} />
        </Card>
      </aside>

      <div className="min-w-0 flex-1 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Permit search</h1>
            <p className="text-sm text-muted-foreground">
              {isFetching ? "Searching..." : `${total.toLocaleString()} permits found`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ViewToggle value={view} onChange={setView} />

            <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm">
                  <Save />
                  Save search
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Save this search</DialogTitle>
                  <DialogDescription>
                    Saved searches are stored locally in this browser (UI-only stub -- see
                    BLOCKERS.md). You can revisit them from the Saved Searches page.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-1.5">
                  <Label htmlFor="save-name">Name</Label>
                  <Input
                    id="save-name"
                    placeholder="e.g. New builds over $1M in Austin"
                    value={saveName}
                    onChange={(e) => setSaveName(e.target.value)}
                  />
                </div>
                <DialogFooter>
                  <Button onClick={handleSaveSearch} disabled={createSavedSearch.isPending}>
                    {createSavedSearch.isPending ? "Saving..." : "Save"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            <Button variant="outline" size="sm" asChild>
              <a href="/alerts">
                <Bell />
                Create alert
              </a>
            </Button>

            <Button variant="outline" size="sm" asChild>
              <a href={buildExportUrl(filters)} target="_blank" rel="noreferrer">
                <Download />
                Export CSV
              </a>
            </Button>
          </div>
        </div>

        {isError && (
          <Card className="border-destructive/50 p-4 text-sm text-destructive">
            Failed to load permits: {error instanceof Error ? error.message : "Unknown error"}
          </Card>
        )}

        <Card className="overflow-hidden p-0">
          {view === "list" ? (
            <>
              <ResultsTable items={items} isLoading={isLoading} />
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={handlePageChange} />
            </>
          ) : (
            <ResultsMap items={items} />
          )}
        </Card>
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <React.Suspense fallback={<div className="container py-8 text-sm text-muted-foreground">Loading search...</div>}>
      <SearchPageInner />
    </React.Suspense>
  );
}
