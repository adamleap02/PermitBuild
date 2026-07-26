import { History } from "lucide-react";

import type { PermitVersionOut } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

interface VersionTimelineProps {
  versions: PermitVersionOut[];
}

export function VersionTimeline({ versions }: VersionTimelineProps) {
  if (versions.length === 0) {
    return <p className="text-sm text-muted-foreground">No version history recorded yet.</p>;
  }

  return (
    <ol className="relative space-y-6 border-l border-border pl-6">
      {versions.map((version) => {
        const changedEntries = Object.entries(version.changed_fields ?? {});
        return (
          <li key={version.version_number} className="relative">
            <span className="absolute -left-[31px] flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
              <History className="h-3 w-3" />
            </span>
            <div className="flex flex-wrap items-baseline gap-2">
              <p className="font-medium">Version {version.version_number}</p>
              <p className="text-xs text-muted-foreground">{formatDateTime(version.recorded_at)}</p>
            </div>
            {changedEntries.length === 0 ? (
              <p className="mt-1 text-sm text-muted-foreground">Initial recorded snapshot.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {changedEntries.map(([field, change]) => (
                  <li key={field} className="rounded-md bg-muted/50 px-3 py-1.5">
                    <span className="font-medium capitalize">{field.replace(/_/g, " ")}:</span>{" "}
                    <span className="text-muted-foreground line-through">{String(change.old ?? "—")}</span>{" "}
                    <span aria-hidden>&rarr;</span> <span>{String(change.new ?? "—")}</span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}
