"use client";

import * as React from "react";

import { useCreateSavedSearch } from "@/lib/hooks/use-saved-searches";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SavedSearchForm() {
  const [name, setName] = React.useState("");
  const [keyword, setKeyword] = React.useState("");
  const createSavedSearch = useCreateSavedSearch();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    await createSavedSearch.mutateAsync({ name: name.trim(), params: { keyword: keyword.trim() || undefined } });
    setName("");
    setKeyword("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <div className="flex-1 space-y-1.5">
        <Label htmlFor="new-search-name">Name</Label>
        <Input
          id="new-search-name"
          placeholder="e.g. Roofing leads in Tampa"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="flex-1 space-y-1.5">
        <Label htmlFor="new-search-keyword">Keyword filter (optional)</Label>
        <Input
          id="new-search-keyword"
          placeholder="reroof"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
      </div>
      <Button type="submit" disabled={createSavedSearch.isPending || !name.trim()}>
        {createSavedSearch.isPending ? "Saving..." : "Save search"}
      </Button>
    </form>
  );
}
