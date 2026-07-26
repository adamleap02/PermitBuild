"use client";

import * as React from "react";

import { useSavedSearches } from "@/lib/hooks/use-saved-searches";
import { useCreateAlert } from "@/lib/hooks/use-alerts";
import type { AlertFrequency } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const FREQUENCIES: { value: AlertFrequency; label: string }[] = [
  { value: "instant", label: "Instantly, as new matches come in" },
  { value: "daily", label: "Daily digest" },
  { value: "weekly", label: "Weekly digest" },
];

export function AlertForm() {
  const { data: savedSearches } = useSavedSearches();
  const createAlert = useCreateAlert();

  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [frequency, setFrequency] = React.useState<AlertFrequency>("daily");
  const [savedSearchId, setSavedSearchId] = React.useState<string>("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !email.trim()) return;
    const savedSearch = savedSearches?.find((s) => s.id === savedSearchId);
    await createAlert.mutateAsync({
      name: name.trim(),
      email: email.trim(),
      frequency,
      saved_search_id: savedSearchId || null,
      params: savedSearch?.params ?? {},
    });
    setName("");
    setEmail("");
    setFrequency("daily");
    setSavedSearchId("");
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-1.5">
        <Label htmlFor="alert-name">Alert name</Label>
        <Input id="alert-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="New luxury builds" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="alert-email">Notify email</Label>
        <Input
          id="alert-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="alert-frequency">Frequency</Label>
        <Select value={frequency} onValueChange={(v) => setFrequency(v as AlertFrequency)}>
          <SelectTrigger id="alert-frequency">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FREQUENCIES.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="alert-saved-search">Based on saved search</Label>
        <Select value={savedSearchId} onValueChange={setSavedSearchId}>
          <SelectTrigger id="alert-saved-search">
            <SelectValue placeholder="All permits (no filter)" />
          </SelectTrigger>
          <SelectContent>
            {(savedSearches ?? []).map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="sm:col-span-2">
        <Button type="submit" disabled={createAlert.isPending || !name.trim() || !email.trim()}>
          {createAlert.isPending ? "Creating..." : "Create alert"}
        </Button>
      </div>
    </form>
  );
}
