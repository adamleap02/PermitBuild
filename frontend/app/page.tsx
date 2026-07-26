import Link from "next/link";
import {
  Building2,
  LineChart,
  MapPinned,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const AUDIENCES = [
  {
    title: "Contractors & suppliers",
    body: "See newly-filed and in-progress permits in your service area, scored by likely project size and value, so you can reach out before competitors do.",
  },
  {
    title: "Lenders & insurers",
    body: "Look up construction activity history at the property level to inform underwriting -- has this property had a permitted renovation in the last N years?",
  },
  {
    title: "Investors",
    body: "Screen for properties and areas with rising construction activity as a leading indicator for where to deploy capital next.",
  },
];

const FEATURES = [
  {
    icon: Search,
    title: "Deep, structured search",
    body: "Filter by city, county, zip, radius, contractor, builder, architect, permit type, value, ownership, property type, status, and date range.",
  },
  {
    icon: MapPinned,
    title: "Map & list views",
    body: "Plot results on an interactive map with clustering, or work through a sortable results table -- switch views without losing your filters.",
  },
  {
    icon: Sparkles,
    title: "Explainable lead scoring",
    body: "Every permit gets project-size, urgency, luxury, investment-likelihood, and lead scores -- each with a plain-English explanation of exactly why.",
  },
  {
    icon: LineChart,
    title: "Analytics dashboard",
    body: "Permits over time, breakdowns by type/status/jurisdiction, and portfolio-level stats to spot trends at a glance.",
  },
  {
    icon: Building2,
    title: "Full version history",
    body: "Permits change over time -- status updates, revised valuations. See the append-only history for every record, not just the latest snapshot.",
  },
  {
    icon: ShieldCheck,
    title: "Public-record data only",
    body: "Built entirely on public permit and assessor data. No fabricated contact info, no scraped personal data beyond what's already public record.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex flex-col">
      <section className="border-b border-border bg-gradient-to-b from-primary/5 to-transparent">
        <div className="container flex flex-col items-center gap-6 py-20 text-center">
          <span className="rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
            Early-access MVP -- see the roadmap in BLOCKERS.md
          </span>
          <h1 className="max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
            Find every home actively under construction in the US --
            <span className="text-primary"> before anyone else does.</span>
          </h1>
          <p className="max-w-2xl text-lg text-muted-foreground">
            Construction Intel continuously ingests building-permit and property records from
            thousands of US jurisdictions, normalizes and scores them, and makes the result
            searchable and alertable for contractors, suppliers, lenders, insurers, and investors.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button size="lg" asChild>
              <Link href="/search">Start searching permits</Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link href="/dashboard">View sample dashboard</Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="container py-16">
        <h2 className="text-center text-2xl font-semibold">Built for how you already work</h2>
        <div className="mt-8 grid gap-6 md:grid-cols-3">
          {AUDIENCES.map((a) => (
            <Card key={a.title}>
              <CardHeader>
                <CardTitle>{a.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <CardDescription className="text-base">{a.body}</CardDescription>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="border-t border-border bg-muted/30 py-16">
        <div className="container">
          <h2 className="text-center text-2xl font-semibold">What&apos;s in the product</h2>
          <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="rounded-lg border border-border bg-background p-6">
                <f.icon className="h-6 w-6 text-primary" />
                <h3 className="mt-3 font-semibold">{f.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="container py-16 text-center">
        <h2 className="text-2xl font-semibold">Ready to see what&apos;s being built near you?</h2>
        <p className="mx-auto mt-2 max-w-xl text-muted-foreground">
          The search page works today against sample data and will use live data automatically
          once the backend is running -- no setup required to try it.
        </p>
        <Button size="lg" className="mt-6" asChild>
          <Link href="/search">Open Search</Link>
        </Button>
      </section>
    </div>
  );
}
