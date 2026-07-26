import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export interface StatTile {
  label: string;
  value: string;
  icon: LucideIcon;
}

export function StatTiles({ tiles }: { tiles: StatTile[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {tiles.map((tile) => (
        <Card key={tile.label}>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="rounded-full bg-primary/10 p-2.5 text-primary">
              <tile.icon className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{tile.label}</p>
              <p className="text-xl font-semibold tabular-nums">{tile.value}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
