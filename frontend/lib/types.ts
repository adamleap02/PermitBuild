/**
 * Types mirroring backend/app/schemas.py exactly (Pydantic response models).
 * Keep this file in sync with the backend schemas -- it is the single
 * source of truth for what shape of data the frontend expects to receive.
 */

export interface ScoreOut {
  project_size_score: number;
  project_size_explanation: string;
  budget_tier: string;
  budget_tier_explanation: string;
  urgency_score: number;
  urgency_explanation: string;
  luxury_likelihood: number;
  luxury_explanation: string;
  remodel_vs_repair: string;
  remodel_vs_repair_explanation: string;
  investment_property_likelihood: number;
  investment_property_explanation: string;
  lead_score: number;
  lead_score_explanation: string;
  confidence_score: number;
  confidence_explanation: string;
  computed_at: string;
}

export interface PermitVersionOut {
  version_number: number;
  snapshot: Record<string, unknown>;
  changed_fields: Record<string, { old: unknown; new: unknown }>;
  recorded_at: string;
}

export interface PermitListItem {
  id: number;
  jurisdiction_id: number;
  permit_number: string;
  permit_type: string | null;
  status: string | null;
  issue_date: string | null;
  application_date: string | null;
  property_address: string | null;
  estimated_cost: number | null;
  valuation: number | null;
  work_category: string | null;
  latitude: number | null;
  longitude: number | null;
  source: string | null;
}

export interface PermitDetail extends PermitListItem {
  contractor: string | null;
  builder: string | null;
  architect: string | null;
  engineer: string | null;
  parcel_number: string | null;
  description: string | null;
  square_footage: number | null;
  units: number | null;
  completion_date: string | null;
  expiration_date: string | null;
  permit_url: string | null;
  property_id: number | null;
  created_at: string;
  updated_at: string;
  versions: PermitVersionOut[];
  latest_score: ScoreOut | null;
}

export interface PermitListResponse {
  total: number;
  page: number;
  page_size: number;
  items: PermitListItem[];
}

export interface PermitMapResponse {
  total_matching: number;
  total_geocoded: number;
  returned: number;
  items: PermitListItem[];
}

export interface OwnerOut {
  id: number;
  name: string | null;
  owner_type: string | null;
  mailing_address: string | null;
  is_owner_occupied: boolean | null;
}

export interface PropertyOut {
  id: number;
  address: string;
  normalized_address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  parcel_number: string | null;
  latitude: number | null;
  longitude: number | null;
  property_type: string | null;
  year_built: number | null;
  lot_size_sqft: number | null;
  building_size_sqft: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  stories: number | null;
  owners: OwnerOut[];
  permits: PermitListItem[];
}

export interface JurisdictionOut {
  id: number;
  name: string;
  state: string;
  level: string;
  source_system: string;
  source_config: Record<string, unknown>;
  is_active: boolean;
}

// ---------------------------------------------------------------------------
// Frontend-only types for features that are UI-only stubs against endpoints
// the backend does not implement yet (saved searches, alerts, auth). See
// BLOCKERS.md. These are intentionally simple / not backed by real schemas.
// ---------------------------------------------------------------------------

export interface PermitSearchParams {
  keyword?: string;
  city?: string;
  county?: string;
  zip?: string;
  radius_miles?: number;
  contractor?: string;
  builder?: string;
  architect?: string;
  permit_type?: string;
  status?: string;
  property_type?: string;
  owner_occupied?: "any" | "yes" | "no";
  min_value?: number;
  max_value?: number;
  date_from?: string;
  date_to?: string;
  jurisdiction_id?: number;
  page?: number;
  page_size?: number;
}

export interface SavedSearch {
  id: string;
  name: string;
  params: PermitSearchParams;
  created_at: string;
}

export type AlertFrequency = "instant" | "daily" | "weekly";

export interface AlertSubscription {
  id: string;
  name: string;
  email: string;
  frequency: AlertFrequency;
  saved_search_id: string | null;
  params: PermitSearchParams;
  created_at: string;
  is_active: boolean;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  organization_name: string | null;
}
