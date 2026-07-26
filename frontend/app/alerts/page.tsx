import { Info } from "lucide-react";

import { AlertForm } from "@/components/alerts/alert-form";
import { AlertList } from "@/components/alerts/alert-list";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AlertsPage() {
  return (
    <div className="container max-w-3xl space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">Alerts</h1>
        <p className="text-sm text-muted-foreground">
          Get notified by email when new permits match a saved search.
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          UI-only stub: alerts are saved locally and no email is actually sent yet. The backend
          doesn&apos;t have an <code className="rounded bg-black/10 px-1 dark:bg-white/10">/alerts</code> endpoint
          or a transactional email provider wired up -- see BLOCKERS.md for what a real
          implementation needs (a scheduled job comparing new permits to saved searches, plus a
          provider like Postmark/SES/Resend for delivery).
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Create alert</CardTitle>
        </CardHeader>
        <CardContent>
          <AlertForm />
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Your alerts</h2>
        <AlertList />
      </div>
    </div>
  );
}
