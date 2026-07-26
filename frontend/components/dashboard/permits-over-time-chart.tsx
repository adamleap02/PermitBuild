"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useChartPalette } from "@/lib/chart-colors";

export interface TimeSeriesPoint {
  month: string;
  count: number;
}

function ChartTooltip({
  active,
  payload,
  label,
  chrome,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
  chrome: ReturnType<typeof useChartPalette>["chrome"];
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-md border px-3 py-2 text-sm shadow-md"
      style={{ background: chrome.surface, borderColor: chrome.gridline, color: chrome.primaryInk }}
    >
      <p className="font-medium">{label}</p>
      <p style={{ color: chrome.secondaryInk }}>{payload[0].value.toLocaleString()} permits</p>
    </div>
  );
}

export function PermitsOverTimeChart({ data }: { data: TimeSeriesPoint[] }) {
  const { chrome, sequential } = useChartPalette();

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={chrome.gridline} />
        <XAxis
          dataKey="month"
          tick={{ fill: chrome.mutedInk, fontSize: 12 }}
          axisLine={{ stroke: chrome.baseline }}
          tickLine={false}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fill: chrome.mutedInk, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={32}
        />
        <Tooltip content={<ChartTooltip chrome={chrome} />} cursor={{ fill: chrome.gridline, opacity: 0.5 }} />
        <Bar dataKey="count" fill={sequential} radius={[4, 4, 0, 0]} maxBarSize={40} />
      </BarChart>
    </ResponsiveContainer>
  );
}
