"use client";

import { Trash2 } from "lucide-react";

import { useAlerts, useDeleteAlert } from "@/lib/hooks/use-alerts";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function AlertList() {
  const { data, isLoading } = useAlerts();
  const deleteAlert = useDeleteAlert();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No alerts yet. Create one below to get notified when new matching permits appear.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {data.map((alert) => (
        <Card key={alert.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{alert.name}</p>
                <Badge variant={alert.is_active ? "success" : "secondary"}>
                  {alert.is_active ? "Active" : "Paused"}
                </Badge>
                <Badge variant="outline" className="capitalize">
                  {alert.frequency}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Notifying {alert.email} &middot; created {formatDate(alert.created_at)}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => deleteAlert.mutate(alert.id)}
              disabled={deleteAlert.isPending}
            >
              <Trash2 className="text-destructive" />
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
