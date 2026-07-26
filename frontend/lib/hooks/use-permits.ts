"use client";

import { useQuery } from "@tanstack/react-query";

import { searchPermits } from "@/lib/api";
import type { PermitSearchParams } from "@/lib/types";

export function usePermitsSearch(params: PermitSearchParams) {
  return useQuery({
    queryKey: ["permits", params],
    queryFn: () => searchPermits(params),
    placeholderData: (previous) => previous,
  });
}
