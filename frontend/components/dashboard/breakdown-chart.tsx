"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useChartPalette } from "@/lib/chart-colors";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export interface BreakdownPoint {
  label: string;
  count: number;
}

function ChartTooltip({
  active,
  payload,
  chrome,
}: {
  active?: boolean;
  payload?: { value: number; payload: BreakdownPoint }[];
  chrome: ReturnType<typeof useChartPalette>["chrome"];
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div
      className="rounded-md border px-3 py-2 text-sm shadow-md"
      style={{ background: chrome.surface, borderColor: chrome.gridline, color: chrome.primaryInk }}
    >
      <p className="font-medium">{point.label}</p>
      <p style={{ color: chrome.secondaryInk }}>{point.count.toLocaleString()} permits</p>
    </div>
  );
}

interface BreakdownChartProps {
  data: BreakdownPoint[];
  /** Render a "view as table" disclosure below the chart (accessibility fallback). */
  showTable?: boolean;
}

export function BreakdownChart({ data, showTable = true }: BreakdownChartProps) {
  const { categorical, chrome } = useChartPalette();
  const total = data.reduce((sum, d) => sum + d.count, 0);

  return (
    <div className="space-y-4">
      <ResponsiveContainer width="100%" height={Math.max(180, data.length * 36)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
          <CartesianGrid horizontal={false} stroke={chrome.gridline} />
          <XAxis type="number" allowDecimals={false} tick={{ fill: chrome.mutedInk, fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis
            type="category"
            dataKey="label"
            width={150}
            tick={{ fill: chrome.primaryInk, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<ChartTooltip chrome={chrome} />} cursor={{ fill: chrome.gridline, opacity: 0.5 }} />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22}>
            {data.map((_, i) => (
              <Cell key={i} fill={categorical[i % categorical.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {showTable && (
        <details className="text-sm">
          <summary className="cursor-pointer select-none text-muted-foreground hover:text-foreground">
            View as table
          </summary>
          <Table className="mt-2">
            <TableHeader>
              <TableRow>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">Permits</TableHead>
                <TableHead className="text-right">Share</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((d) => (
                <TableRow key={d.label}>
                  <TableCell>{d.label}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.count.toLocaleString()}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {total > 0 ? `${((d.count / total) * 100).toFixed(1)}%` : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </details>
      )}
    </div>
  );
}
