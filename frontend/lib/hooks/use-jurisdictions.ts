"use client";

import { useQuery } from "@tanstack/react-query";

import { listJurisdictions } from "@/lib/api";

export function useJurisdictions() {
  return useQuery({
    queryKey: ["jurisdictions"],
    queryFn: listJurisdictions,
    staleTime: 5 * 60_000,
  });
}
