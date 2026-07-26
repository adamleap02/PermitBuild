"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft, ExternalLink, MapPin } from "lucide-react";

import { usePermit } from "@/lib/hooks/use-permit";
import { useProperty } from "@/lib/hooks/use-property";
import { bestCost, formatCurrency, formatDate, formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScoreExplanation } from "@/components/permits/score-explanation";
import { VersionTimeline } from "@/components/permits/version-timeline";

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{value ?? "—"}</dd>
    </div>
  );
}

export function PermitDetailClient({ id }: { id: number }) {
  const { data: permit, isLoading, isError, error } = usePermit(id);
  const { data: property, isLoading: propertyLoading } = useProperty(permit?.property_id ?? null);

  if (isLoading) {
    return (
      <div className="container space-y-4 py-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (isError || !permit) {
    return (
      <div className="container py-16 text-center">
        <p className="text-lg font-medium">Permit not found</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {error instanceof Error ? error.message : "This permit doesn't exist or couldn't be loaded."}
        </p>
        <Button className="mt-4" variant="outline" asChild>
          <Link href="/search">
            <ArrowLeft />
            Back to search
          </Link>
        </Button>
      </div>
    );
  }

  const score = permit.latest_score;

  return (
    <div className="container space-y-6 py-8">
      <div>
        <Link href="/search" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          Back to search
        </Link>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold">{permit.permit_type ?? "Permit"}</h1>
            <Badge className="capitalize">{permit.status ?? "unknown"}</Badge>
            {score && (
              <Badge variant="secondary">Lead score {score.lead_score.toFixed(0)}/100</Badge>
            )}
          </div>
          <p className="mt-1 text-muted-foreground">
            {permit.permit_number} &middot; {permit.property_address}
          </p>
        </div>
        {permit.permit_url && (
          <Button variant="outline" asChild>
            <a href={permit.permit_url} target="_blank" rel="noreferrer">
              View source record
              <ExternalLink />
            </a>
          </Button>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs font-medium uppercase text-muted-foreground">Valuation</p>
            <p className="mt-1 text-xl font-semibold">{formatCurrency(bestCost(permit))}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs font-medium uppercase text-muted-foreground">Issued</p>
            <p className="mt-1 text-xl font-semibold">{formatDate(permit.issue_date)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs font-medium uppercase text-muted-foreground">Square footage</p>
            <p className="mt-1 text-xl font-semibold">
              {permit.square_footage ? `${formatNumber(permit.square_footage)} sqft` : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs font-medium uppercase text-muted-foreground">Budget tier</p>
            <p className="mt-1 text-xl font-semibold capitalize">{score?.budget_tier ?? "—"}</p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="property">Property</TabsTrigger>
          <TabsTrigger value="history">Version history</TabsTrigger>
          <TabsTrigger value="scores">Scores &amp; why</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <Card>
            <CardHeader>
              <CardTitle>Permit details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="Permit number" value={permit.permit_number} />
                <Field label="Work category" value={permit.work_category} />
                <Field label="Contractor" value={permit.contractor} />
                <Field label="Builder" value={permit.builder} />
                <Field label="Architect" value={permit.architect} />
                <Field label="Engineer" value={permit.engineer} />
                <Field label="Application date" value={formatDate(permit.application_date)} />
                <Field label="Issue date" value={formatDate(permit.issue_date)} />
                <Field label="Completion date" value={formatDate(permit.completion_date)} />
                <Field label="Expiration date" value={formatDate(permit.expiration_date)} />
                <Field label="Units" value={permit.units} />
                <Field label="Parcel / APN" value={permit.parcel_number} />
                <Field label="Estimated cost" value={formatCurrency(permit.estimated_cost)} />
                <Field label="Valuation" value={formatCurrency(permit.valuation)} />
                <Field label="Data source" value={permit.source} />
              </dl>
              {permit.description && (
                <div className="mt-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Description</p>
                  <p className="mt-1 text-sm">{permit.description}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="property">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MapPin className="h-4 w-4" />
                Property information
              </CardTitle>
            </CardHeader>
            <CardContent>
              {propertyLoading ? (
                <Skeleton className="h-40 w-full" />
              ) : property ? (
                <div className="space-y-6">
                  <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <Field label="Address" value={property.address} />
                    <Field label="City / State / ZIP" value={`${property.city ?? "—"}, ${property.state ?? "—"} ${property.zip_code ?? ""}`} />
                    <Field label="Property type" value={property.property_type?.replace("_", " ")} />
                    <Field label="Year built" value={property.year_built} />
                    <Field label="Building size" value={property.building_size_sqft ? `${formatNumber(property.building_size_sqft)} sqft` : "—"} />
                    <Field label="Lot size" value={property.lot_size_sqft ? `${formatNumber(property.lot_size_sqft)} sqft` : "—"} />
                    <Field label="Bedrooms" value={property.bedrooms} />
                    <Field label="Bathrooms" value={property.bathrooms} />
                    <Field label="Stories" value={property.stories} />
                    <Field label="Parcel number" value={property.parcel_number} />
                  </dl>

                  {property.owners.length > 0 && (
                    <div>
                      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Ownership (public record)
                      </p>
                      <div className="space-y-2">
                        {property.owners.map((owner) => (
                          <div key={owner.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border p-3 text-sm">
                            <span className="font-medium">{owner.name ?? "Unknown owner"}</span>
                            {owner.owner_type && <Badge variant="outline" className="capitalize">{owner.owner_type}</Badge>}
                            {owner.is_owner_occupied !== null && (
                              <Badge variant={owner.is_owner_occupied ? "success" : "secondary"}>
                                {owner.is_owner_occupied ? "Owner-occupied" : "Non-owner-occupied"}
                              </Badge>
                            )}
                            {owner.mailing_address && (
                              <span className="text-xs text-muted-foreground">{owner.mailing_address}</span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {property.permits.length > 1 && (
                    <div>
                      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Other permits at this property
                      </p>
                      <ul className="space-y-1 text-sm">
                        {property.permits
                          .filter((p) => p.id !== permit.id)
                          .map((p) => (
                            <li key={p.id}>
                              <Link href={`/permits/${p.id}`} className="text-primary hover:underline">
                                {p.permit_number} &middot; {p.permit_type}
                              </Link>
                            </li>
                          ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No linked property record.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle>Version history</CardTitle>
            </CardHeader>
            <CardContent>
              <VersionTimeline versions={permit.versions} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="scores">
          {score ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Scores are computed by a rules-based, fully explainable engine -- never a black-box
                model. Every number below comes with the exact reasoning that produced it.
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                <ScoreExplanation title="Lead score" value={score.lead_score} explanation={score.lead_score_explanation} />
                <ScoreExplanation title="Project size" value={score.project_size_score} explanation={score.project_size_explanation} />
                <ScoreExplanation title="Urgency" value={score.urgency_score} explanation={score.urgency_explanation} />
                <ScoreExplanation title="Luxury likelihood" value={score.luxury_likelihood} explanation={score.luxury_explanation} />
                <ScoreExplanation
                  title="Investment property likelihood"
                  value={score.investment_property_likelihood}
                  explanation={score.investment_property_explanation}
                />
                <ScoreExplanation title="Data confidence" value={score.confidence_score} explanation={score.confidence_explanation} />
                <ScoreExplanation
                  title="Budget tier"
                  value={score.budget_tier}
                  numeric={false}
                  explanation={score.budget_tier_explanation}
                />
                <ScoreExplanation
                  title="Remodel vs. repair vs. new"
                  value={score.remodel_vs_repair.replace(/_/g, " ")}
                  numeric={false}
                  explanation={score.remodel_vs_repair_explanation}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Computed at {formatDate(score.computed_at)}.
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No score computed for this permit yet.</p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
