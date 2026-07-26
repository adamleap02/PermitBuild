"use client";

import { List, Map as MapIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export type SearchView = "list" | "map";

interface ViewToggleProps {
  value: SearchView;
  onChange: (view: SearchView) => void;
}

export function ViewToggle({ value, onChange }: ViewToggleProps) {
  return (
    <div className="inline-flex rounded-md border border-border p-1">
      <button
        type="button"
        onClick={() => onChange("list")}
        className={cn(
          "flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
          value === "list" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent"
        )}
      >
        <List className="h-4 w-4" />
        List
      </button>
      <button
        type="button"
        onClick={() => onChange("map")}
        className={cn(
          "flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
          value === "map" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent"
        )}
      >
        <MapIcon className="h-4 w-4" />
        Map
      </button>
    </div>
  );
}
