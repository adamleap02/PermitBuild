"use client";

import { useQuery } from "@tanstack/react-query";

import { getPermit } from "@/lib/api";

export function usePermit(id: number) {
  return useQuery({
    queryKey: ["permit", id],
    queryFn: () => getPermit(id),
    enabled: Number.isFinite(id),
  });
}
