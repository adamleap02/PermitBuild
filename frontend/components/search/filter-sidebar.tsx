"use client";

import * as React from "react";
import { RotateCcw, Search as SearchIcon } from "lucide-react";

import type { PermitSearchParams } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const PERMIT_TYPES = [
  "New Single Family Dwelling",
  "New Multi-Family Dwelling",
  "Accessory Dwelling Unit",
  "Kitchen Remodel",
  "Bathroom Remodel",
  "Second Story Addition",
  "Reroof",
  "Pool & Spa",
  "Electrical Service Upgrade",
  "Solar Installation",
  "Commercial Tenant Improvement",
  "Commercial Retail Buildout",
  "Residential Rehab",
  "Furnace Replacement",
  "Basement Finish",
];

const STATUSES = ["applied", "in review", "issued", "final", "expired"];

const PROPERTY_TYPES = ["single_family", "multi_family", "condo", "townhome", "commercial"];

const RADIUS_OPTIONS = [1, 5, 10, 25, 50];

interface FilterSidebarProps {
  value: PermitSearchParams;
  onApply: (params: PermitSearchParams) => void;
  onReset: () => void;
}

export function FilterSidebar({ value, onApply, onReset }: FilterSidebarProps) {
  const [draft, setDraft] = React.useState<PermitSearchParams>(value);

  React.useEffect(() => setDraft(value), [value]);

  function set<K extends keyof PermitSearchParams>(key: K, val: PermitSearchParams[K]) {
    setDraft((d) => ({ ...d, [key]: val }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onApply({ ...draft, page: 1 });
  }

  function handleReset() {
    setDraft({});
    onReset();
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <div className="space-y-1.5">
        <Label htmlFor="keyword">Keyword</Label>
        <Input
          id="keyword"
          placeholder="description, address, permit #, contractor..."
          value={draft.keyword ?? ""}
          onChange={(e) => set("keyword", e.target.value || undefined)}
        />
      </div>

      <Separator />

      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Location</p>
        <div className="space-y-1.5">
          <Label htmlFor="city">City</Label>
          <Input id="city" placeholder="Austin" value={draft.city ?? ""} onChange={(e) => set("city", e.target.value || undefined)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="county">County</Label>
          <Input
            id="county"
            placeholder="Hillsborough County"
            value={draft.county ?? ""}
            onChange={(e) => set("county", e.target.value || undefined)}
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="zip">ZIP code</Label>
            <Input id="zip" placeholder="78701" value={draft.zip ?? ""} onChange={(e) => set("zip", e.target.value || undefined)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="radius">Radius (mi)</Label>
            <Select
              value={draft.radius_miles ? String(draft.radius_miles) : undefined}
              onValueChange={(v) => set("radius_miles", Number(v))}
            >
              <SelectTrigger id="radius">
                <SelectValue placeholder="Any" />
              </SelectTrigger>
              <SelectContent>
                {RADIUS_OPTIONS.map((r) => (
                  <SelectItem key={r} value={String(r)}>
                    {r} mi
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Radius search requires a city/zip center point and is not yet implemented server-side
          (see BLOCKERS.md) -- sent to the API for forward-compatibility.
        </p>
      </div>

      <Separator />

      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Permit details
        </p>
        <div className="space-y-1.5">
          <Label htmlFor="permit_type">Permit type</Label>
          <Select value={draft.permit_type ?? ""} onValueChange={(v) => set("permit_type", v || undefined)}>
            <SelectTrigger id="permit_type">
              <SelectValue placeholder="Any type" />
            </SelectTrigger>
            <SelectContent>
              {PERMIT_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="status">Status</Label>
          <Select value={draft.status ?? ""} onValueChange={(v) => set("status", v || undefined)}>
            <SelectTrigger id="status">
              <SelectValue placeholder="Any status" />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="date_from">Issued after</Label>
            <Input
              id="date_from"
              type="date"
              value={draft.date_from?.slice(0, 10) ?? ""}
              onChange={(e) => set("date_from", e.target.value || undefined)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="date_to">Issued before</Label>
            <Input
              id="date_to"
              type="date"
              value={draft.date_to?.slice(0, 10) ?? ""}
              onChange={(e) => set("date_to", e.target.value || undefined)}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="min_value">Min value ($)</Label>
            <Input
              id="min_value"
              type="number"
              min={0}
              placeholder="0"
              value={draft.min_value ?? ""}
              onChange={(e) => set("min_value", e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="max_value">Max value ($)</Label>
            <Input
              id="max_value"
              type="number"
              min={0}
              placeholder="No limit"
              value={draft.max_value ?? ""}
              onChange={(e) => set("max_value", e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
        </div>
      </div>

      <Separator />

      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          People & entities
        </p>
        <div className="space-y-1.5">
          <Label htmlFor="contractor">Contractor</Label>
          <Input
            id="contractor"
            placeholder="Longhorn Custom Homes"
            value={draft.contractor ?? ""}
            onChange={(e) => set("contractor", e.target.value || undefined)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="builder">Builder</Label>
          <Input
            id="builder"
            placeholder="Mile High Custom Homes"
            value={draft.builder ?? ""}
            onChange={(e) => set("builder", e.target.value || undefined)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="architect">Architect</Label>
          <Input
            id="architect"
            placeholder="Studio Elm Architects"
            value={draft.architect ?? ""}
            onChange={(e) => set("architect", e.target.value || undefined)}
          />
        </div>
      </div>

      <Separator />

      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Property
        </p>
        <div className="space-y-1.5">
          <Label htmlFor="property_type">Property type</Label>
          <Select value={draft.property_type ?? ""} onValueChange={(v) => set("property_type", v || undefined)}>
            <SelectTrigger id="property_type">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              {PROPERTY_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {t.replace("_", " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="owner_occupied">Owner occupied</Label>
          <Select
            value={draft.owner_occupied ?? "any"}
            onValueChange={(v) => set("owner_occupied", v as PermitSearchParams["owner_occupied"])}
          >
            <SelectTrigger id="owner_occupied">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any</SelectItem>
              <SelectItem value="yes">Owner-occupied</SelectItem>
              <SelectItem value="no">Investor / non-owner-occupied</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="sticky bottom-0 flex gap-2 border-t border-border bg-background pt-4">
        <Button type="submit" className="flex-1">
          <SearchIcon />
          Search
        </Button>
        <Button type="button" variant="outline" onClick={handleReset}>
          <RotateCcw />
          Reset
        </Button>
      </div>
    </form>
  );
}
