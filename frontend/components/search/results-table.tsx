"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";

import type { PermitListItem } from "@/lib/types";
import { bestCost, formatCurrency, formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";

function statusVariant(status: string | null): "default" | "secondary" | "outline" | "destructive" {
  switch (status) {
    case "issued":
      return "default";
    case "final":
      return "secondary";
    case "expired":
      return "destructive";
    default:
      return "outline";
  }
}

interface ResultsTableProps {
  items: PermitListItem[];
  isLoading: boolean;
}

export function ResultsTable({ items, isLoading }: ResultsTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-1 py-16 text-center">
        <p className="font-medium">No permits match these filters</p>
        <p className="text-sm text-muted-foreground">Try widening your date range or clearing a filter.</p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Permit #</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Address</TableHead>
          <TableHead className="text-right">Value</TableHead>
          <TableHead>Issued</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((permit) => (
          <TableRow key={permit.id} className="cursor-pointer">
            <TableCell className="font-medium">
              <Link href={`/permits/${permit.id}`} className="hover:underline">
                {permit.permit_number}
              </Link>
            </TableCell>
            <TableCell className="max-w-[220px] truncate" title={permit.permit_type ?? undefined}>
              {permit.permit_type ?? "—"}
            </TableCell>
            <TableCell>
              <Badge variant={statusVariant(permit.status)} className="capitalize">
                {permit.status ?? "unknown"}
              </Badge>
            </TableCell>
            <TableCell className="max-w-[280px] truncate" title={permit.property_address ?? undefined}>
              {permit.property_address ?? "—"}
            </TableCell>
            <TableCell className="text-right tabular-nums">{formatCurrency(bestCost(permit))}</TableCell>
            <TableCell className="whitespace-nowrap">{formatDate(permit.issue_date)}</TableCell>
            <TableCell>
              <Link href={`/permits/${permit.id}`} aria-label="View permit details">
                <ExternalLink className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              </Link>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
