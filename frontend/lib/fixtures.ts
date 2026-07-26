/**
 * Local sample/mock data used as a local-dev fallback when the backend
 * (backend/, FastAPI) isn't reachable, or when NEXT_PUBLIC_USE_MOCKS=true.
 * See lib/api.ts for how this is wired in, and BLOCKERS.md for the caveat
 * that this is illustrative sample data, not real permit records.
 *
 * Shapes mirror backend/app/schemas.py exactly (see lib/types.ts). Scores
 * are computed with the lib/scoring.ts port of the backend's rules engine
 * so the numbers/explanations shown in the UI are internally consistent.
 */
import { scorePermit } from "./scoring";
import type {
  AlertSubscription,
  JurisdictionOut,
  OwnerOut,
  PermitDetail,
  PermitListItem,
  PermitListResponse,
  PermitSearchParams,
  PermitVersionOut,
  PropertyOut,
  SavedSearch,
} from "./types";

// ---------------------------------------------------------------------------
// Jurisdictions
// ---------------------------------------------------------------------------

export const JURISDICTIONS: JurisdictionOut[] = [
  {
    id: 1,
    name: "Austin",
    state: "TX",
    level: "city",
    source_system: "socrata",
    source_config: { domain: "data.austintexas.gov", dataset_id: "3syk-w9eu" },
    is_active: true,
  },
  {
    id: 2,
    name: "Phoenix",
    state: "AZ",
    level: "city",
    source_system: "arcgis",
    source_config: { service_url: "https://services.phoenix.gov/arcgis/rest/services/permits" },
    is_active: true,
  },
  {
    id: 3,
    name: "Hillsborough County",
    state: "FL",
    level: "county",
    source_system: "socrata",
    source_config: { domain: "data.hillsboroughcounty.org", dataset_id: "perm-its1" },
    is_active: true,
  },
  {
    id: 4,
    name: "Denver",
    state: "CO",
    level: "city",
    source_system: "arcgis",
    source_config: { service_url: "https://services.denvergov.org/arcgis/rest/services/permits" },
    is_active: true,
  },
];

// ---------------------------------------------------------------------------
// Seed shape: raw fields for one permit + its linked property/owner. Kept
// internal to this file; converted to the public API shapes below.
// ---------------------------------------------------------------------------

interface Seed {
  id: number;
  jurisdiction_id: number;
  permit_number: string;
  permit_type: string;
  status: "applied" | "in review" | "issued" | "final" | "expired";
  application_date: string | null;
  issue_date: string | null;
  completion_date: string | null;
  expiration_date: string | null;
  contractor: string | null;
  builder: string | null;
  architect: string | null;
  engineer: string | null;
  estimated_cost: number | null;
  valuation: number | null;
  description: string;
  work_category: string;
  square_footage: number | null;
  units: number | null;
  permit_url: string;
  source: string;
  // property
  property_id: number;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  parcel_number: string;
  latitude: number;
  longitude: number;
  property_type: string;
  year_built: number | null;
  lot_size_sqft: number | null;
  building_size_sqft: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  stories: number | null;
  owner_name: string;
  owner_type: string;
  owner_occupied: boolean | null;
}

const SEEDS: Seed[] = [
  {
    id: 1001, jurisdiction_id: 1, permit_number: "AUS-2026-014422", permit_type: "New Single Family Dwelling",
    status: "issued", application_date: "2026-05-01T00:00:00Z", issue_date: "2026-07-10T00:00:00Z",
    completion_date: null, expiration_date: "2027-07-10T00:00:00Z",
    contractor: "Longhorn Custom Homes LLC", builder: "Longhorn Custom Homes LLC", architect: "Studio Elm Architects", engineer: "Pecan Street Engineering",
    estimated_cost: 1_800_000, valuation: 1_850_000,
    description: "New 4,200 sqft custom single-family home with pool, spa, wine cellar, and smart home automation.",
    work_category: "new construction", square_footage: 4200, units: 1,
    permit_url: "https://data.austintexas.gov/permits/AUS-2026-014422", source: "socrata:data.austintexas.gov",
    property_id: 2001, address: "4718 Bluff Springs Ridge", city: "Austin", state: "TX", zip_code: "78744",
    parcel_number: "TX-04-2210-0417", latitude: 30.2015, longitude: -97.7461,
    property_type: "single_family", year_built: 2026, lot_size_sqft: 12500, building_size_sqft: 4200,
    bedrooms: 5, bathrooms: 5.5, stories: 2,
    owner_name: "Robert & Elena Whitfield", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1002, jurisdiction_id: 1, permit_number: "AUS-2026-013310", permit_type: "Accessory Dwelling Unit",
    status: "issued", application_date: "2026-03-20T00:00:00Z", issue_date: "2026-05-02T00:00:00Z",
    completion_date: null, expiration_date: "2027-05-02T00:00:00Z",
    contractor: "Hill Country Builders", builder: "Hill Country Builders", architect: null, engineer: null,
    estimated_cost: 140_000, valuation: 145_000,
    description: "New 650 sqft detached ADU / accessory dwelling unit above existing garage.",
    work_category: "addition", square_footage: 650, units: 1,
    permit_url: "https://data.austintexas.gov/permits/AUS-2026-013310", source: "socrata:data.austintexas.gov",
    property_id: 2002, address: "1902 Southshore Blvd", city: "Austin", state: "TX", zip_code: "78741",
    parcel_number: "TX-04-1188-0902", latitude: 30.2354, longitude: -97.7212,
    property_type: "single_family", year_built: 1998, lot_size_sqft: 8200, building_size_sqft: 1850,
    bedrooms: 3, bathrooms: 2, stories: 1,
    owner_name: "Marisol Guerrero", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1003, jurisdiction_id: 1, permit_number: "AUS-2025-098871", permit_type: "Kitchen Remodel",
    status: "final", application_date: "2025-10-20T00:00:00Z", issue_date: "2025-11-14T00:00:00Z",
    completion_date: "2026-02-01T00:00:00Z", expiration_date: "2026-05-14T00:00:00Z",
    contractor: "Capital City Renovations", builder: null, architect: null, engineer: null,
    estimated_cost: 58_000, valuation: 62_000,
    description: "Full kitchen remodel: cabinets, countertops, appliances, plumbing relocation.",
    work_category: "remodel", square_footage: 320, units: null,
    permit_url: "https://data.austintexas.gov/permits/AUS-2025-098871", source: "socrata:data.austintexas.gov",
    property_id: 2003, address: "7710 Rain Creek Pkwy", city: "Austin", state: "TX", zip_code: "78759",
    parcel_number: "TX-04-0533-1177", latitude: 30.4025, longitude: -97.7534,
    property_type: "single_family", year_built: 1985, lot_size_sqft: 9600, building_size_sqft: 2400,
    bedrooms: 4, bathrooms: 2.5, stories: 1,
    owner_name: "David Kim", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1004, jurisdiction_id: 1, permit_number: "AUS-2026-015901", permit_type: "Reroof",
    status: "issued", application_date: "2026-07-19T00:00:00Z", issue_date: "2026-07-20T00:00:00Z",
    completion_date: null, expiration_date: "2026-10-20T00:00:00Z",
    contractor: "Texas Roof Repair Inc", builder: null, architect: null, engineer: null,
    estimated_cost: 17_500, valuation: 18_500,
    description: "Emergency reroof following storm damage from June hailstorm; full tear-off and replace.",
    work_category: "repair", square_footage: null, units: null,
    permit_url: "https://data.austintexas.gov/permits/AUS-2026-015901", source: "socrata:data.austintexas.gov",
    property_id: 2004, address: "2214 Rosewood Ave", city: "Austin", state: "TX", zip_code: "78702",
    parcel_number: "TX-04-0221-4409", latitude: 30.2733, longitude: -97.7146,
    property_type: "single_family", year_built: 1962, lot_size_sqft: 6100, building_size_sqft: 1400,
    bedrooms: 3, bathrooms: 1, stories: 1,
    owner_name: "Angela Ford", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1005, jurisdiction_id: 1, permit_number: "AUS-2026-015012", permit_type: "Commercial Tenant Improvement",
    status: "in review", application_date: "2026-07-01T00:00:00Z", issue_date: null,
    completion_date: null, expiration_date: null,
    contractor: "Longhorn Commercial Builders LLC", builder: null, architect: "Meridian Design Group", engineer: "Colorado River Structural",
    estimated_cost: 400_000, valuation: 420_000,
    description: "Office tenant improvement, 3rd floor, downtown high-rise. New partitions, MEP rework.",
    work_category: "tenant improvement", square_footage: 9800, units: null,
    permit_url: "https://data.austintexas.gov/permits/AUS-2026-015012", source: "socrata:data.austintexas.gov",
    property_id: 2005, address: "301 Congress Ave, Ste 300", city: "Austin", state: "TX", zip_code: "78701",
    parcel_number: "TX-04-0009-3010", latitude: 30.2661, longitude: -97.7438,
    property_type: "commercial", year_built: 2010, lot_size_sqft: null, building_size_sqft: 9800,
    bedrooms: null, bathrooms: null, stories: 1,
    owner_name: "Congress Ave Holdings LLC", owner_type: "llc", owner_occupied: false,
  },
  {
    id: 1006, jurisdiction_id: 2, permit_number: "PHX-2026-220145", permit_type: "New Multi-Family Dwelling",
    status: "issued", application_date: "2026-02-10T00:00:00Z", issue_date: "2026-06-15T00:00:00Z",
    completion_date: null, expiration_date: "2028-06-15T00:00:00Z",
    contractor: "Desert Sky Development LP", builder: "Desert Sky Development LP", architect: "Camelback Architecture", engineer: "Sonoran Structural Engineers",
    estimated_cost: 6_200_000, valuation: 6_400_000,
    description: "New 24-unit multifamily apartment complex with shared amenity building for rental income property.",
    work_category: "new construction", square_footage: 26_000, units: 24,
    permit_url: "https://services.phoenix.gov/permits/PHX-2026-220145", source: "arcgis:services.phoenix.gov",
    property_id: 2006, address: "9200 N 27th Ave", city: "Phoenix", state: "AZ", zip_code: "85051",
    parcel_number: "AZ-08-1102-0092", latitude: 33.5502, longitude: -112.0965,
    property_type: "multi_family", year_built: 2026, lot_size_sqft: 90_000, building_size_sqft: 26_000,
    bedrooms: null, bathrooms: null, stories: 3,
    owner_name: "Desert Sky Development LP", owner_type: "llc", owner_occupied: false,
  },
  {
    id: 1007, jurisdiction_id: 2, permit_number: "PHX-2026-221980", permit_type: "Pool & Spa",
    status: "issued", application_date: "2026-06-30T00:00:00Z", issue_date: "2026-07-18T00:00:00Z",
    completion_date: null, expiration_date: "2026-11-18T00:00:00Z",
    contractor: "Valley Pool Builders", builder: null, architect: null, engineer: null,
    estimated_cost: 90_000, valuation: 95_000,
    description: "New in-ground pool and spa with outdoor kitchen and rooftop deck pergola.",
    work_category: "addition", square_footage: null, units: null,
    permit_url: "https://services.phoenix.gov/permits/PHX-2026-221980", source: "arcgis:services.phoenix.gov",
    property_id: 2007, address: "5540 E Cactus Wren Rd", city: "Phoenix", state: "AZ", zip_code: "85018",
    parcel_number: "AZ-08-0044-1290", latitude: 33.5091, longitude: -111.9856,
    property_type: "single_family", year_built: 2005, lot_size_sqft: 14_000, building_size_sqft: 3600,
    bedrooms: 4, bathrooms: 3.5, stories: 1,
    owner_name: "Priya & Anand Rao", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1008, jurisdiction_id: 2, permit_number: "PHX-2025-199044", permit_type: "Bathroom Remodel",
    status: "final", application_date: "2025-08-15T00:00:00Z", issue_date: "2025-09-10T00:00:00Z",
    completion_date: "2025-11-01T00:00:00Z", expiration_date: "2026-03-10T00:00:00Z",
    contractor: "Sonoran Home Renovations", builder: null, architect: null, engineer: null,
    estimated_cost: 32_000, valuation: 34_000,
    description: "Primary bathroom remodel: new tile, fixtures, walk-in shower.",
    work_category: "remodel", square_footage: 180, units: null,
    permit_url: "https://services.phoenix.gov/permits/PHX-2025-199044", source: "arcgis:services.phoenix.gov",
    property_id: 2008, address: "1120 W Glendale Ave", city: "Phoenix", state: "AZ", zip_code: "85021",
    parcel_number: "AZ-08-0071-4402", latitude: 33.5389, longitude: -112.0839,
    property_type: "single_family", year_built: 1978, lot_size_sqft: 7400, building_size_sqft: 1650,
    bedrooms: 3, bathrooms: 2, stories: 1,
    owner_name: "Karen Alvarez", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1009, jurisdiction_id: 2, permit_number: "PHX-2026-222410", permit_type: "Electrical Service Upgrade",
    status: "issued", application_date: "2026-07-21T00:00:00Z", issue_date: "2026-07-22T00:00:00Z",
    completion_date: null, expiration_date: "2026-09-22T00:00:00Z",
    contractor: "Cactus Electric", builder: null, architect: null, engineer: null,
    estimated_cost: 9_200, valuation: 9_800,
    description: "Emergency electrical panel replacement due to unsafe/hazard wiring found during inspection.",
    work_category: "repair", square_footage: null, units: null,
    permit_url: "https://services.phoenix.gov/permits/PHX-2026-222410", source: "arcgis:services.phoenix.gov",
    property_id: 2009, address: "3315 W Missouri Ave", city: "Phoenix", state: "AZ", zip_code: "85017",
    parcel_number: "AZ-08-0092-3315", latitude: 33.5121, longitude: -112.1112,
    property_type: "single_family", year_built: 1965, lot_size_sqft: 6800, building_size_sqft: 1250,
    bedrooms: 3, bathrooms: 1, stories: 1,
    owner_name: "Thomas Nguyen", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1010, jurisdiction_id: 2, permit_number: "PHX-2026-210233", permit_type: "Solar Installation",
    status: "issued", application_date: "2026-03-28T00:00:00Z", issue_date: "2026-04-11T00:00:00Z",
    completion_date: null, expiration_date: "2026-10-11T00:00:00Z",
    contractor: "Bright Sun Solar Inc", builder: null, architect: null, engineer: "Bright Sun Solar Inc",
    estimated_cost: 26_500, valuation: 28_000,
    description: "Rooftop solar panel installation, 8.4kW system with battery storage.",
    work_category: "addition", square_footage: null, units: null,
    permit_url: "https://services.phoenix.gov/permits/PHX-2026-210233", source: "arcgis:services.phoenix.gov",
    property_id: 2010, address: "7788 E Sahuaro Dr", city: "Phoenix", state: "AZ", zip_code: "85054",
    parcel_number: "AZ-08-0133-7788", latitude: 33.6512, longitude: -111.9701,
    property_type: "single_family", year_built: 2015, lot_size_sqft: 8900, building_size_sqft: 2900,
    bedrooms: 4, bathrooms: 3, stories: 2,
    owner_name: "Michael Osei", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1011, jurisdiction_id: 3, permit_number: "HIL-2026-334120", permit_type: "New Single Family Dwelling",
    status: "issued", application_date: "2026-04-01T00:00:00Z", issue_date: "2026-06-28T00:00:00Z",
    completion_date: null, expiration_date: "2027-12-28T00:00:00Z",
    contractor: "Gulf Coast Custom Builders LLC", builder: "Gulf Coast Custom Builders LLC", architect: "Bayshore Design Studio", engineer: "Tampa Bay Structural Group",
    estimated_cost: 2_250_000, valuation: 2_350_000,
    description: "New 5,100 sqft waterfront custom home with elevator, home theater, and boat dock.",
    work_category: "new construction", square_footage: 5100, units: 1,
    permit_url: "https://data.hillsboroughcounty.org/permits/HIL-2026-334120", source: "socrata:data.hillsboroughcounty.org",
    property_id: 2011, address: "4410 Bayshore Blvd", city: "Tampa", state: "FL", zip_code: "33611",
    parcel_number: "FL-13-2299-4410", latitude: 27.9089, longitude: -82.4823,
    property_type: "single_family", year_built: 2026, lot_size_sqft: 15_800, building_size_sqft: 5100,
    bedrooms: 6, bathrooms: 6.5, stories: 3,
    owner_name: "Whitfield Family Trust", owner_type: "trust", owner_occupied: false,
  },
  {
    id: 1012, jurisdiction_id: 3, permit_number: "HIL-2026-320087", permit_type: "Residential Rehab",
    status: "issued", application_date: "2026-02-01T00:00:00Z", issue_date: "2026-03-05T00:00:00Z",
    completion_date: null, expiration_date: "2026-09-05T00:00:00Z",
    contractor: "Bay Area Rental Investments LLC", builder: null, architect: null, engineer: null,
    estimated_cost: 200_000, valuation: 210_000,
    description: "Full rehab of duplex rental property, 2 units, for continued tenant occupancy under landlord LLC.",
    work_category: "remodel", square_footage: 2100, units: 2,
    permit_url: "https://data.hillsboroughcounty.org/permits/HIL-2026-320087", source: "socrata:data.hillsboroughcounty.org",
    property_id: 2012, address: "812 E Crenshaw St", city: "Tampa", state: "FL", zip_code: "33604",
    parcel_number: "FL-13-1187-0812", latitude: 28.0089, longitude: -82.4534,
    property_type: "multi_family", year_built: 1955, lot_size_sqft: 6200, building_size_sqft: 2100,
    bedrooms: 4, bathrooms: 2, stories: 1,
    owner_name: "Bay Area Rental Investments LLC", owner_type: "llc", owner_occupied: false,
  },
  {
    id: 1013, jurisdiction_id: 3, permit_number: "HIL-2026-336655", permit_type: "Reroof",
    status: "issued", application_date: "2026-07-23T00:00:00Z", issue_date: "2026-07-24T00:00:00Z",
    completion_date: null, expiration_date: "2026-10-24T00:00:00Z",
    contractor: "Florida Roofing Pros", builder: null, architect: null, engineer: null,
    estimated_cost: 21_000, valuation: 22_000,
    description: "Emergency reroof after hurricane storm damage; tarps installed, full replacement scheduled.",
    work_category: "repair", square_footage: null, units: null,
    permit_url: "https://data.hillsboroughcounty.org/permits/HIL-2026-336655", source: "socrata:data.hillsboroughcounty.org",
    property_id: 2013, address: "6602 S Sherrill St", city: "Tampa", state: "FL", zip_code: "33616",
    parcel_number: "FL-13-0987-6602", latitude: 27.8912, longitude: -82.5122,
    property_type: "single_family", year_built: 1971, lot_size_sqft: 7100, building_size_sqft: 1550,
    bedrooms: 3, bathrooms: 2, stories: 1,
    owner_name: "Janet Olsen", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1014, jurisdiction_id: 3, permit_number: "HIL-2026-329944", permit_type: "Second Story Addition",
    status: "in review", application_date: "2026-06-20T00:00:00Z", issue_date: null,
    completion_date: null, expiration_date: null,
    contractor: "Sunset Bay Builders", builder: null, architect: "Bayshore Design Studio", engineer: null,
    estimated_cost: 168_000, valuation: 175_000,
    description: "Second story addition adding 3 bedrooms and 2 baths above existing single-story footprint.",
    work_category: "addition", square_footage: 1400, units: null,
    permit_url: "https://data.hillsboroughcounty.org/permits/HIL-2026-329944", source: "socrata:data.hillsboroughcounty.org",
    property_id: 2014, address: "3311 W San Miguel St", city: "Tampa", state: "FL", zip_code: "33629",
    parcel_number: "FL-13-0765-3311", latitude: 27.9345, longitude: -82.5089,
    property_type: "single_family", year_built: 1990, lot_size_sqft: 8400, building_size_sqft: 2200,
    bedrooms: 3, bathrooms: 2, stories: 1,
    owner_name: "Christopher Hale", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1015, jurisdiction_id: 3, permit_number: "HIL-2025-301122", permit_type: "Commercial Retail Buildout",
    status: "issued", application_date: "2025-10-15T00:00:00Z", issue_date: "2025-12-01T00:00:00Z",
    completion_date: null, expiration_date: "2026-08-15T00:00:00Z",
    contractor: "Coastal Commercial Group Inc", builder: null, architect: "Meridian Design Group", engineer: "Tampa Bay Structural Group",
    estimated_cost: 325_000, valuation: 340_000,
    description: "Retail shell buildout for new tenant space in strip commercial center.",
    work_category: "tenant improvement", square_footage: 4800, units: null,
    permit_url: "https://data.hillsboroughcounty.org/permits/HIL-2025-301122", source: "socrata:data.hillsboroughcounty.org",
    property_id: 2015, address: "9020 W Waters Ave", city: "Tampa", state: "FL", zip_code: "33615",
    parcel_number: "FL-13-1401-9020", latitude: 28.0223, longitude: -82.5967,
    property_type: "commercial", year_built: 1999, lot_size_sqft: 22_000, building_size_sqft: 4800,
    bedrooms: null, bathrooms: null, stories: 1,
    owner_name: "Waters Ave Retail Partners LLC", owner_type: "llc", owner_occupied: false,
  },
  {
    id: 1016, jurisdiction_id: 4, permit_number: "DEN-2026-441982", permit_type: "New Single Family Dwelling",
    status: "issued", application_date: "2026-03-15T00:00:00Z", issue_date: "2026-05-20T00:00:00Z",
    completion_date: null, expiration_date: "2027-11-20T00:00:00Z",
    contractor: "Mile High Custom Homes", builder: "Mile High Custom Homes", architect: "Front Range Architecture", engineer: "Rockies Structural Engineers",
    estimated_cost: 1_200_000, valuation: 1_250_000,
    description: "New 4,000 sqft custom home with rooftop deck and full smart home automation.",
    work_category: "new construction", square_footage: 4000, units: 1,
    permit_url: "https://services.denvergov.org/permits/DEN-2026-441982", source: "arcgis:services.denvergov.org",
    property_id: 2016, address: "2140 Vine St", city: "Denver", state: "CO", zip_code: "80205",
    parcel_number: "CO-16-0043-2140", latitude: 39.7534, longitude: -104.9622,
    property_type: "single_family", year_built: 2026, lot_size_sqft: 6300, building_size_sqft: 4000,
    bedrooms: 5, bathrooms: 4.5, stories: 3,
    owner_name: "Sarah & James Whitcombe", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1017, jurisdiction_id: 4, permit_number: "DEN-2025-419087", permit_type: "Furnace Replacement",
    status: "final", application_date: "2025-09-28T00:00:00Z", issue_date: "2025-10-02T00:00:00Z",
    completion_date: "2025-10-09T00:00:00Z", expiration_date: "2026-01-02T00:00:00Z",
    contractor: "Rocky Mountain HVAC", builder: null, architect: null, engineer: null,
    estimated_cost: 6_800, valuation: 7_200,
    description: "Replace failed furnace and ductwork before winter season.",
    work_category: "repair", square_footage: null, units: null,
    permit_url: "https://services.denvergov.org/permits/DEN-2025-419087", source: "arcgis:services.denvergov.org",
    property_id: 2017, address: "4455 W 32nd Ave", city: "Denver", state: "CO", zip_code: "80212",
    parcel_number: "CO-16-0091-4455", latitude: 39.7576, longitude: -105.0356,
    property_type: "single_family", year_built: 1948, lot_size_sqft: 5400, building_size_sqft: 1350,
    bedrooms: 2, bathrooms: 1, stories: 1,
    owner_name: "Linda Marsh", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1018, jurisdiction_id: 4, permit_number: "DEN-2026-430556", permit_type: "Commercial Tenant Improvement",
    status: "issued", application_date: "2025-12-20T00:00:00Z", issue_date: "2026-02-14T00:00:00Z",
    completion_date: null, expiration_date: "2026-08-14T00:00:00Z",
    contractor: "Denver Commercial Properties LLC", builder: null, architect: "LoDo Architecture Group", engineer: "Rockies Structural Engineers",
    estimated_cost: 560_000, valuation: 580_000,
    description: "Full-floor commercial office tenant improvement in LoDo high-rise for multi-tenant investment building.",
    work_category: "tenant improvement", square_footage: 12_500, units: null,
    permit_url: "https://services.denvergov.org/permits/DEN-2026-430556", source: "arcgis:services.denvergov.org",
    property_id: 2018, address: "1550 Wynkoop St", city: "Denver", state: "CO", zip_code: "80202",
    parcel_number: "CO-16-0007-1550", latitude: 39.7524, longitude: -105.0009,
    property_type: "commercial", year_built: 2001, lot_size_sqft: null, building_size_sqft: 12_500,
    bedrooms: null, bathrooms: null, stories: 1,
    owner_name: "Wynkoop Street Investors LLC", owner_type: "llc", owner_occupied: false,
  },
  {
    id: 1019, jurisdiction_id: 4, permit_number: "DEN-2025-405512", permit_type: "Basement Finish",
    status: "final", application_date: "2025-07-30T00:00:00Z", issue_date: "2025-08-19T00:00:00Z",
    completion_date: "2025-12-10T00:00:00Z", expiration_date: "2026-02-19T00:00:00Z",
    contractor: "Front Range Renovations", builder: null, architect: null, engineer: null,
    estimated_cost: 45_000, valuation: 48_000,
    description: "Basement rehab/finish adding a rec room, bedroom, and 3/4 bath.",
    work_category: "remodel", square_footage: 950, units: null,
    permit_url: "https://services.denvergov.org/permits/DEN-2025-405512", source: "arcgis:services.denvergov.org",
    property_id: 2019, address: "7710 E Iowa Ave", city: "Denver", state: "CO", zip_code: "80231",
    parcel_number: "CO-16-0122-7710", latitude: 39.6912, longitude: -104.9089,
    property_type: "single_family", year_built: 1988, lot_size_sqft: 7800, building_size_sqft: 2050,
    bedrooms: 4, bathrooms: 2.5, stories: 2,
    owner_name: "Patricia Boyd", owner_type: "individual", owner_occupied: true,
  },
  {
    id: 1020, jurisdiction_id: 4, permit_number: "DEN-2026-407221", permit_type: "Accessory Dwelling Unit",
    status: "issued", application_date: "2025-12-05T00:00:00Z", issue_date: "2026-01-10T00:00:00Z",
    completion_date: null, expiration_date: "2026-09-01T00:00:00Z",
    contractor: "Mile High Custom Homes", builder: "Mile High Custom Homes", architect: "Front Range Architecture", engineer: null,
    estimated_cost: 200_000, valuation: 210_000,
    description: "New detached guest house / ADU with casita-style finishes on the same lot as the primary residence.",
    work_category: "addition", square_footage: 900, units: 1,
    permit_url: "https://services.denvergov.org/permits/DEN-2026-407221", source: "arcgis:services.denvergov.org",
    property_id: 2016, address: "2140 Vine St", city: "Denver", state: "CO", zip_code: "80205",
    parcel_number: "CO-16-0043-2140", latitude: 39.7534, longitude: -104.9622,
    property_type: "single_family", year_built: 2026, lot_size_sqft: 6300, building_size_sqft: 4000,
    bedrooms: 5, bathrooms: 4.5, stories: 3,
    owner_name: "Sarah & James Whitcombe", owner_type: "individual", owner_occupied: true,
  },
];

// ---------------------------------------------------------------------------
// Derived: PermitDetail[] (with computed score + synthesized version history)
// ---------------------------------------------------------------------------

function buildVersions(seed: Seed): PermitVersionOut[] {
  const versions: PermitVersionOut[] = [];
  const baseSnapshot = {
    permit_number: seed.permit_number,
    permit_type: seed.permit_type,
    contractor: seed.contractor,
    valuation: seed.valuation,
    property_address: seed.address,
  };

  const appliedAt = seed.application_date ?? seed.issue_date ?? seed.completion_date ?? "2025-01-01T00:00:00Z";
  versions.push({
    version_number: 1,
    snapshot: { ...baseSnapshot, status: "applied" },
    changed_fields: {},
    recorded_at: appliedAt,
  });

  if (seed.issue_date) {
    versions.push({
      version_number: 2,
      snapshot: { ...baseSnapshot, status: "issued" },
      changed_fields: { status: { old: "applied", new: "issued" } },
      recorded_at: seed.issue_date,
    });
  }

  if (seed.status === "final" && seed.completion_date) {
    versions.push({
      version_number: versions.length + 1,
      snapshot: { ...baseSnapshot, status: "final" },
      changed_fields: { status: { old: "issued", new: "final" } },
      recorded_at: seed.completion_date,
    });
  }

  return versions;
}

function toListItem(seed: Seed): PermitListItem {
  return {
    id: seed.id,
    jurisdiction_id: seed.jurisdiction_id,
    permit_number: seed.permit_number,
    permit_type: seed.permit_type,
    status: seed.status,
    issue_date: seed.issue_date,
    application_date: seed.application_date,
    property_address: `${seed.address}, ${seed.city}, ${seed.state} ${seed.zip_code}`,
    estimated_cost: seed.estimated_cost,
    valuation: seed.valuation,
    work_category: seed.work_category,
    latitude: seed.latitude,
    longitude: seed.longitude,
    source: seed.source,
  };
}

function toDetail(seed: Seed): PermitDetail {
  const listItem = toListItem(seed);
  const score = scorePermit(seed);
  return {
    ...listItem,
    contractor: seed.contractor,
    builder: seed.builder,
    architect: seed.architect,
    engineer: seed.engineer,
    parcel_number: seed.parcel_number,
    description: seed.description,
    square_footage: seed.square_footage,
    units: seed.units,
    completion_date: seed.completion_date,
    expiration_date: seed.expiration_date,
    permit_url: seed.permit_url,
    property_id: seed.property_id,
    created_at: seed.application_date ?? seed.issue_date ?? "2025-01-01T00:00:00Z",
    updated_at: seed.completion_date ?? seed.issue_date ?? seed.application_date ?? "2025-01-01T00:00:00Z",
    versions: buildVersions(seed),
    latest_score: { ...score, computed_at: new Date().toISOString() },
  };
}

export const PERMITS: PermitDetail[] = SEEDS.map(toDetail);

const SEEDS_BY_ID = new Map(SEEDS.map((s) => [s.id, s]));
const PERMITS_BY_ID = new Map(PERMITS.map((p) => [p.id, p]));

// ---------------------------------------------------------------------------
// Properties (derived from seeds; a property can have >1 linked permit, e.g.
// property_id 2016 has both the primary residence and its ADU permit)
// ---------------------------------------------------------------------------

function ownerFor(seed: Seed): OwnerOut {
  return {
    id: seed.property_id,
    name: seed.owner_name,
    owner_type: seed.owner_type,
    mailing_address: `${seed.address}, ${seed.city}, ${seed.state} ${seed.zip_code}`,
    is_owner_occupied: seed.owner_occupied,
  };
}

export function getPropertyMock(propertyId: number): PropertyOut | undefined {
  const seed = SEEDS.find((s) => s.property_id === propertyId);
  if (!seed) return undefined;
  const linkedPermits = SEEDS.filter((s) => s.property_id === propertyId).map((s) =>
    toListItem(s)
  );
  return {
    id: seed.property_id,
    address: seed.address,
    normalized_address: seed.address.toUpperCase(),
    city: seed.city,
    state: seed.state,
    zip_code: seed.zip_code,
    parcel_number: seed.parcel_number,
    latitude: seed.latitude,
    longitude: seed.longitude,
    property_type: seed.property_type,
    year_built: seed.year_built,
    lot_size_sqft: seed.lot_size_sqft,
    building_size_sqft: seed.building_size_sqft,
    bedrooms: seed.bedrooms,
    bathrooms: seed.bathrooms,
    stories: seed.stories,
    owners: [ownerFor(seed)],
    permits: linkedPermits,
  };
}

// ---------------------------------------------------------------------------
// Search / filter over the mock permit list, mirroring the semantics of
// backend/app/routers/permits.py `apply_filters` (plus a few extra fields --
// city/county/zip/radius/owner_occupied/property_type/builder/architect --
// that the API contract calls for but the backend doesn't filter on yet;
// see BLOCKERS.md).
// ---------------------------------------------------------------------------

function bestCost(seed: Seed): number | null {
  return seed.valuation ?? seed.estimated_cost ?? null;
}

export function searchPermitsMock(params: PermitSearchParams): PermitListResponse {
  const page = params.page ?? 1;
  const pageSize = params.page_size ?? 25;

  let results = SEEDS.slice();

  if (params.jurisdiction_id) {
    results = results.filter((s) => s.jurisdiction_id === params.jurisdiction_id);
  }
  if (params.permit_type) {
    const q = params.permit_type.toLowerCase();
    results = results.filter((s) => s.permit_type.toLowerCase().includes(q));
  }
  if (params.status) {
    const q = params.status.toLowerCase();
    results = results.filter((s) => s.status.toLowerCase().includes(q));
  }
  if (params.city) {
    const q = params.city.toLowerCase();
    results = results.filter((s) => s.city.toLowerCase().includes(q));
  }
  if (params.county) {
    const q = params.county.toLowerCase();
    results = results.filter((s) =>
      JURISDICTIONS.find((j) => j.id === s.jurisdiction_id)?.name.toLowerCase().includes(q)
    );
  }
  if (params.zip) {
    results = results.filter((s) => s.zip_code === params.zip);
  }
  if (params.contractor) {
    const q = params.contractor.toLowerCase();
    results = results.filter((s) => (s.contractor ?? "").toLowerCase().includes(q));
  }
  if (params.builder) {
    const q = params.builder.toLowerCase();
    results = results.filter((s) => (s.builder ?? "").toLowerCase().includes(q));
  }
  if (params.architect) {
    const q = params.architect.toLowerCase();
    results = results.filter((s) => (s.architect ?? "").toLowerCase().includes(q));
  }
  if (params.property_type) {
    results = results.filter((s) => s.property_type === params.property_type);
  }
  if (params.owner_occupied && params.owner_occupied !== "any") {
    const want = params.owner_occupied === "yes";
    results = results.filter((s) => s.owner_occupied === want);
  }
  if (params.min_value !== undefined) {
    results = results.filter((s) => {
      const c = bestCost(s);
      return c !== null && c >= params.min_value!;
    });
  }
  if (params.max_value !== undefined) {
    results = results.filter((s) => {
      const c = bestCost(s);
      return c !== null && c <= params.max_value!;
    });
  }
  if (params.date_from) {
    results = results.filter((s) => s.issue_date && s.issue_date >= params.date_from!);
  }
  if (params.date_to) {
    results = results.filter((s) => s.issue_date && s.issue_date <= params.date_to!);
  }
  if (params.keyword) {
    const q = params.keyword.toLowerCase();
    results = results.filter(
      (s) =>
        s.description.toLowerCase().includes(q) ||
        s.address.toLowerCase().includes(q) ||
        s.permit_number.toLowerCase().includes(q) ||
        (s.contractor ?? "").toLowerCase().includes(q)
    );
  }

  results.sort((a, b) => {
    if (!a.issue_date && !b.issue_date) return 0;
    if (!a.issue_date) return 1;
    if (!b.issue_date) return -1;
    return b.issue_date.localeCompare(a.issue_date);
  });

  const total = results.length;
  const start = (page - 1) * pageSize;
  const items = results.slice(start, start + pageSize).map(toListItem);

  return { total, page, page_size: pageSize, items };
}

export function getPermitMock(id: number): PermitDetail | undefined {
  return PERMITS_BY_ID.get(id);
}

export function listJurisdictionsMock(): JurisdictionOut[] {
  return JURISDICTIONS;
}

/** All permits, unpaginated -- used by the dashboard to compute aggregates client-side. */
export function allPermitsMock(): PermitListItem[] {
  return SEEDS.map(toListItem);
}

// ---------------------------------------------------------------------------
// Saved searches / alerts: seed a couple of examples so those pages aren't
// empty on first load. These are UI-only stubs (see BLOCKERS.md) -- real
// persistence is localStorage-backed, see lib/api.ts.
// ---------------------------------------------------------------------------

export const SEED_SAVED_SEARCHES: SavedSearch[] = [
  {
    id: "seed-1",
    name: "New construction over $1M, Austin/Denver",
    params: { permit_type: "New Single Family", min_value: 1_000_000 },
    created_at: "2026-06-01T00:00:00Z",
  },
  {
    id: "seed-2",
    name: "Fresh reroof leads (storm damage)",
    params: { keyword: "storm damage", status: "issued" },
    created_at: "2026-07-01T00:00:00Z",
  },
];

export const SEED_ALERTS: AlertSubscription[] = [
  {
    id: "alert-seed-1",
    name: "Daily digest: new luxury builds",
    email: "adamleap02@gmail.com",
    frequency: "daily",
    saved_search_id: "seed-1",
    params: { permit_type: "New Single Family", min_value: 1_000_000 },
    created_at: "2026-06-01T00:00:00Z",
    is_active: true,
  },
];
