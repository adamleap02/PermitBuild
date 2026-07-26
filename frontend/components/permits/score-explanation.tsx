import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ScoreExplanationProps {
  title: string;
  /** 0-100 numeric score, or a categorical label (e.g. budget tier / classification) when `numeric` is false. */
  value: number | string;
  numeric?: boolean;
  explanation: string;
}

export function ScoreExplanation({ title, value, numeric = true, explanation }: ScoreExplanationProps) {
  const pct = numeric && typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">{title}</CardTitle>
          <span className={cn("text-2xl font-bold tabular-nums", pct !== null && barColorText(pct))}>
            {typeof value === "number" ? value.toFixed(1) : value}
            {pct !== null && <span className="text-sm font-normal text-muted-foreground">/100</span>}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        {pct !== null && (
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={cn("h-full rounded-full transition-all", barColorBg(pct))}
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
        <p className="text-sm text-muted-foreground">{explanation}</p>
      </CardContent>
    </Card>
  );
}

function barColorBg(pct: number): string {
  if (pct >= 70) return "bg-primary";
  if (pct >= 40) return "bg-amber-500";
  return "bg-muted-foreground/40";
}

function barColorText(pct: number): string {
  if (pct >= 70) return "text-primary";
  if (pct >= 40) return "text-amber-600 dark:text-amber-400";
  return "text-muted-foreground";
}
