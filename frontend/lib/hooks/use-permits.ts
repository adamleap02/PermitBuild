"use client";

import { useQuery } from "@tanstack/react-query";

import { mapPermits, searchPermits } from "@/lib/api";
import type { PermitSearchParams } from "@/lib/types";

export function usePermitsSearch(params: PermitSearchParams) {
  return useQuery({
    queryKey: ["permits", params],
    queryFn: () => searchPermits(params),
    placeholderData: (previous) => previous,
  });
}

/**
 * Backs the map view specifically -- fetches up to `limit` geocoded points
 * matching the current filters (independent of the results table's small
 * page size), so the map reflects the real scale of the dataset rather
 * than just one page of ~25 results.
 */
export function usePermitsMap(params: PermitSearchParams, limit = 5000, enabled = true) {
  const { page: _page, page_size: _page_size, ...filters } = params;
  return useQuery({
    queryKey: ["permits-map", filters, limit],
    queryFn: () => mapPermits(filters, limit),
    placeholderData: (previous) => previous,
    enabled,
  });
}
