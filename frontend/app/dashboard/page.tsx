"use client";

import * as React from "react";
import { Building2, DollarSign, FileStack, MapPin } from "lucide-react";

import { usePermitsSearch } from "@/lib/hooks/use-permits";
import { useJurisdictions } from "@/lib/hooks/use-jurisdictions";
import { bestCost, formatCurrency, formatNumber } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTiles } from "@/components/dashboard/stat-tiles";
import { PermitsOverTimeChart, type TimeSeriesPoint } from "@/components/dashboard/permits-over-time-chart";
import { BreakdownChart, type BreakdownPoint } from "@/components/dashboard/breakdown-chart";

const MONTH_FORMAT = new Intl.DateTimeFormat("en-US", { month: "short", year: "2-digit" });

function topNWithOther(counts: Map<string, number>, n: number): BreakdownPoint[] {
  const sorted = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  const top = sorted.slice(0, n).map(([label, count]) => ({ label, count }));
  const rest = sorted.slice(n).reduce((sum, [, count]) => sum + count, 0);
  if (rest > 0) top.push({ label: "Other", count: rest });
  return top;
}

export default function DashboardPage() {
  // No dedicated analytics endpoint exists on the backend yet (see
  // BLOCKERS.md) -- this pulls a large page of permits and aggregates
  // client-side. Fine for an MVP/demo; replace with a real
  // GET /analytics/* endpoint before this needs to scale past a few
  // thousand permits.
  const { data, isLoading } = usePermitsSearch({ page: 1, page_size: 200 });
  const { data: jurisdictions } = useJurisdictions();

  const items = React.useMemo(() => data?.items ?? [], [data]);

  const jurisdictionNames = React.useMemo(() => {
    const map = new Map<number, string>();
    (jurisdictions ?? []).forEach((j) => map.set(j.id, `${j.name}, ${j.state}`));
    return map;
  }, [jurisdictions]);

  const timeSeries: TimeSeriesPoint[] = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of items) {
      if (!p.issue_date) continue;
      const d = new Date(p.issue_date);
      const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, count]) => {
        const [year, month] = key.split("-").map(Number);
        return { month: MONTH_FORMAT.format(new Date(Date.UTC(year, month - 1, 1))), count };
      });
  }, [items]);

  const byType: BreakdownPoint[] = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of items) {
      const key = p.permit_type ?? "Unknown";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return topNWithOther(counts, 7);
  }, [items]);

  const byStatus: BreakdownPoint[] = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of items) {
      const key = p.status ?? "unknown";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return topNWithOther(counts, 8);
  }, [items]);

  const byJurisdiction: BreakdownPoint[] = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of items) {
      const key = jurisdictionNames.get(p.jurisdiction_id) ?? `Jurisdiction #${p.jurisdiction_id}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return topNWithOther(counts, 7);
  }, [items, jurisdictionNames]);

  const totalValue = React.useMemo(
    () => items.reduce((sum, p) => sum + (bestCost(p) ?? 0), 0),
    [items]
  );
  const avgValue = items.length > 0 ? totalValue / items.length : 0;
  const activeJurisdictions = new Set(items.map((p) => p.jurisdiction_id)).size;

  return (
    <div className="container space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">Analytics dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Aggregated from{" "}
          {data ? `the current ${formatNumber(items.length)} of ${formatNumber(data.total)} permits` : "permits"}
          {" "}matching no filters (sample view). Apply filters on the Search page for a scoped view later.
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <StatTiles
          tiles={[
            { label: "Permits (sampled)", value: formatNumber(items.length), icon: FileStack },
            { label: "Total value", value: formatCurrency(totalValue), icon: DollarSign },
            { label: "Avg. permit value", value: formatCurrency(avgValue), icon: Building2 },
            { label: "Active jurisdictions", value: formatNumber(activeJurisdictions), icon: MapPin },
          ]}
        />
      )}

      <Card>
        <CardHeader>
          <CardTitle>Permits over time</CardTitle>
          <CardDescription>Count of permits by issue month.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? <Skeleton className="h-64 w-full" /> : <PermitsOverTimeChart data={timeSeries} />}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>By permit type</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-48 w-full" /> : <BreakdownChart data={byType} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>By status</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-48 w-full" /> : <BreakdownChart data={byStatus} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>By jurisdiction</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-48 w-full" /> : <BreakdownChart data={byJurisdiction} />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
