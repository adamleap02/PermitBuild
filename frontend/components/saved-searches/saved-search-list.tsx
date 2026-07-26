"use client";

import Link from "next/link";
import { Play, Trash2 } from "lucide-react";

import { useDeleteSavedSearch, useSavedSearches } from "@/lib/hooks/use-saved-searches";
import type { PermitSearchParams } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function paramsToQueryString(params: PermitSearchParams): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    qs.set(key, String(value));
  });
  return qs.toString();
}

function summarize(params: PermitSearchParams): string[] {
  const parts: string[] = [];
  if (params.keyword) parts.push(`"${params.keyword}"`);
  if (params.permit_type) parts.push(params.permit_type);
  if (params.city) parts.push(params.city);
  if (params.status) parts.push(`status: ${params.status}`);
  if (params.min_value) parts.push(`min $${params.min_value.toLocaleString()}`);
  if (params.max_value) parts.push(`max $${params.max_value.toLocaleString()}`);
  return parts.length > 0 ? parts : ["No filters (all permits)"];
}

export function SavedSearchList() {
  const { data, isLoading } = useSavedSearches();
  const deleteSavedSearch = useDeleteSavedSearch();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No saved searches yet. Create one below, or save filters from the{" "}
          <Link href="/search" className="text-primary hover:underline">
            Search page
          </Link>
          .
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {data.map((search) => (
        <Card key={search.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <p className="font-medium">{search.name}</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {summarize(search.params).map((s) => (
                  <Badge key={s} variant="outline">
                    {s}
                  </Badge>
                ))}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">Saved {formatDate(search.created_at)}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" asChild>
                <Link href={`/search?${paramsToQueryString(search.params)}`}>
                  <Play />
                  Run
                </Link>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => deleteSavedSearch.mutate(search.id)}
                disabled={deleteSavedSearch.isPending}
              >
                <Trash2 className="text-destructive" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
