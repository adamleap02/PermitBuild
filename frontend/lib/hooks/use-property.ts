"use client";

import { useQuery } from "@tanstack/react-query";

import { getProperty } from "@/lib/api";

export function useProperty(id: number | null | undefined) {
  return useQuery({
    queryKey: ["property", id],
    queryFn: () => getProperty(id as number),
    enabled: typeof id === "number" && Number.isFinite(id),
  });
}
