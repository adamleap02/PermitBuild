"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createSavedSearch, deleteSavedSearch, listSavedSearches } from "@/lib/api";
import type { PermitSearchParams } from "@/lib/types";

export function useSavedSearches() {
  return useQuery({
    queryKey: ["saved-searches"],
    queryFn: listSavedSearches,
  });
}

export function useCreateSavedSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, params }: { name: string; params: PermitSearchParams }) =>
      createSavedSearch(name, params),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-searches"] }),
  });
}

export function useDeleteSavedSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSavedSearch(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-searches"] }),
  });
}
