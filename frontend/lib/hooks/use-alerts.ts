"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createAlert, deleteAlert, listAlerts } from "@/lib/api";
import type { AlertSubscription } from "@/lib/types";

export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: listAlerts,
  });
}

export function useCreateAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Omit<AlertSubscription, "id" | "created_at" | "is_active">) =>
      createAlert(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

export function useDeleteAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAlert(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
}
