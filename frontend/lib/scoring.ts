/**
 * TypeScript port of backend/app/scoring/engine.py, used ONLY to compute
 * realistic, internally-consistent scores for the local fixtures in
 * lib/fixtures.ts (so the UI is demonstrable before the backend is running).
 *
 * In real usage the API returns `latest_score` already computed server-side
 * (see ScoreOut in lib/types.ts) -- this file is never used against live API
 * data, only against the mock fixtures. Keep the logic mirrored to the
 * Python original if that file changes.
 */

export interface ScoringInput {
  permit_type?: string | null;
  status?: string | null;
  description?: string | null;
  work_category?: string | null;
  contractor?: string | null;
  builder?: string | null;
  estimated_cost?: number | null;
  valuation?: number | null;
  square_footage?: number | null;
  units?: number | null;
  issue_date?: string | null;
  expiration_date?: string | null;
  property_address?: string | null;
}

export interface ScoreComputed {
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
}

const BUDGET_TIERS: [number, string][] = [
  [5_000, "micro"],
  [25_000, "small"],
  [100_000, "medium"],
  [500_000, "large"],
  [Infinity, "major"],
];

function cost(p: ScoringInput): number | null {
  if (p.valuation) return p.valuation;
  if (p.estimated_cost) return p.estimated_cost;
  return null;
}

function textBlob(p: ScoringInput): string {
  return [p.description ?? "", p.permit_type ?? "", p.work_category ?? ""]
    .join(" ")
    .toLowerCase();
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

function scoreProjectSize(p: ScoringInput): [number, string] {
  const c = cost(p);
  const sqft = p.square_footage;
  const units = p.units;
  const signals: number[] = [];
  const reasons: string[] = [];

  if (c !== null) {
    const costScore = Math.min(100, Math.max(0, c ** 0.35 / 6.0));
    signals.push(costScore);
    reasons.push(`valuation $${c.toLocaleString("en-US")}`);
  }
  if (sqft && sqft > 0) {
    const sqftScore = Math.min(100, (sqft / 5000) * 100);
    signals.push(sqftScore);
    reasons.push(`${sqft.toLocaleString("en-US")} sqft`);
  }
  if (units && units > 0) {
    const unitScore = Math.min(100, (units / 20) * 100);
    signals.push(unitScore);
    reasons.push(`${units} unit(s)`);
  }
  if (signals.length === 0) {
    return [0, "No cost, square footage, or unit data available -- defaulting to 0."];
  }
  const score = round1(Math.max(...signals));
  return [score, `Project size score based on: ${reasons.join(", ")} -> ${score}/100.`];
}

function scoreBudgetTier(p: ScoringInput): [string, string] {
  const c = cost(p);
  if (c === null) return ["unknown", "No estimated_cost or valuation present on the permit."];
  for (const [threshold, tier] of BUDGET_TIERS) {
    if (c < threshold) {
      const explanation =
        threshold !== Infinity
          ? `$${c.toLocaleString("en-US")} falls in the '${tier}' tier (< $${threshold.toLocaleString("en-US")}).`
          : `$${c.toLocaleString("en-US")} falls in the '${tier}' tier.`;
      return [tier, explanation];
    }
  }
  return ["major", `$${c.toLocaleString("en-US")} falls in the 'major' tier.`];
}

const URGENCY_KEYWORDS = [
  "emergency",
  "urgent",
  "unsafe",
  "hazard",
  "condemn",
  "fire damage",
  "storm damage",
  "collapse",
];

function scoreUrgency(p: ScoringInput, now: Date): [number, string] {
  let score = 0;
  const reasons: string[] = [];

  if (p.issue_date) {
    const issue = new Date(p.issue_date);
    let daysSinceIssue = Math.floor((now.getTime() - issue.getTime()) / 86_400_000);
    if (daysSinceIssue < 0) daysSinceIssue = 0;
    if (daysSinceIssue <= 30) {
      const freshness = 60 * (1 - daysSinceIssue / 30);
      score += freshness;
      reasons.push(`issued ${daysSinceIssue} day(s) ago (fresh)`);
    } else {
      reasons.push(`issued ${daysSinceIssue} day(s) ago (not fresh)`);
    }
  }

  if (p.expiration_date) {
    const expiry = new Date(p.expiration_date);
    const daysToExpiry = Math.floor((expiry.getTime() - now.getTime()) / 86_400_000);
    if (daysToExpiry >= 0 && daysToExpiry <= 60) {
      const expiryBoost = 40 * (1 - daysToExpiry / 60);
      score += expiryBoost;
      reasons.push(`expires in ${daysToExpiry} day(s)`);
    } else if (daysToExpiry < 0) {
      reasons.push("permit already expired");
    }
  }

  const text = textBlob(p);
  const hitKeywords = URGENCY_KEYWORDS.filter((kw) => text.includes(kw));
  if (hitKeywords.length > 0) {
    score += 25;
    reasons.push(`urgency keywords found: ${hitKeywords.join(", ")}`);
  }

  score = round1(Math.min(100, score));
  if (reasons.length === 0) {
    return [0, "No issue/expiration dates or urgency keywords found -- defaulting to 0."];
  }
  return [score, `Urgency score based on: ${reasons.join("; ")} -> ${score}/100.`];
}

const LUXURY_KEYWORDS = [
  "pool",
  "spa",
  "wine cellar",
  "custom home",
  "high-end",
  "high end",
  "luxury",
  "elevator",
  "home theater",
  "guest house",
  "casita",
  "outdoor kitchen",
  "smart home",
  "solar",
  "rooftop deck",
  "penthouse",
];

function scoreLuxuryLikelihood(p: ScoringInput): [number, string] {
  let score = 0;
  const reasons: string[] = [];
  const c = cost(p);
  const sqft = p.square_footage;

  if (c && sqft && sqft > 0) {
    const costPerSqft = c / sqft;
    if (costPerSqft >= 600) score += 70;
    else if (costPerSqft >= 300) score += 40;
    else if (costPerSqft >= 150) score += 15;
    reasons.push(`$${costPerSqft.toLocaleString("en-US", { maximumFractionDigits: 0 })}/sqft`);
  }

  const text = textBlob(p);
  const hits = LUXURY_KEYWORDS.filter((kw) => text.includes(kw));
  if (hits.length > 0) {
    score += Math.min(50, 15 * hits.length);
    reasons.push(`luxury keywords: ${hits.join(", ")}`);
  }

  score = round1(Math.min(100, score));
  if (reasons.length === 0) {
    return [0, "No cost-per-sqft or luxury keywords detected -- defaulting to 0."];
  }
  return [score, `Luxury likelihood based on: ${reasons.join("; ")} -> ${score}/100.`];
}

const NEW_CONSTRUCTION_KEYWORDS = ["new construction", "new single family", "new sfd", "new dwelling", "ground up", "new building"];
const ADDITION_KEYWORDS = ["addition", "add ", "adu", "accessory dwelling", "second story", "expand"];
const REMODEL_KEYWORDS = ["remodel", "renovation", "renovate", "kitchen", "bathroom", "alteration", "alter", "finish basement", "rehab"];
const REPAIR_KEYWORDS = ["repair", "replace", "reroof", "re-roof", "water heater", "furnace", "patch", "fix", "maintenance"];

function classifyRemodelVsRepair(p: ScoringInput): [string, string] {
  const text = textBlob(p);
  const hits = (kws: string[]) => kws.filter((kw) => text.includes(kw));

  const newHits = hits(NEW_CONSTRUCTION_KEYWORDS);
  if (newHits.length > 0) {
    return ["new_construction", `Classified as new_construction due to keyword(s): ${newHits.join(", ")}.`];
  }
  const additionHits = hits(ADDITION_KEYWORDS);
  if (additionHits.length > 0) {
    return ["addition", `Classified as addition due to keyword(s): ${additionHits.join(", ")}.`];
  }
  const remodelHits = hits(REMODEL_KEYWORDS);
  const repairHits = hits(REPAIR_KEYWORDS);
  if (remodelHits.length > 0 && (repairHits.length === 0 || remodelHits.length >= repairHits.length)) {
    return ["remodel", `Classified as remodel due to keyword(s): ${remodelHits.join(", ")}.`];
  }
  if (repairHits.length > 0) {
    return ["repair", `Classified as repair due to keyword(s): ${repairHits.join(", ")}.`];
  }
  return ["other", "No new-construction/addition/remodel/repair keywords matched permit_type, work_category, or description."];
}

const INVESTMENT_KEYWORDS = [
  "rental",
  "tenant improvement",
  "ti permit",
  "multi-family",
  "multifamily",
  "apartment",
  "commercial",
  "landlord",
  "llc",
  "lp",
  "investors",
  "investment",
];

function scoreInvestmentPropertyLikelihood(p: ScoringInput): [number, string] {
  let score = 0;
  const reasons: string[] = [];
  const units = p.units;

  if (units && units >= 2) {
    const boost = Math.min(60, 15 * units);
    score += boost;
    reasons.push(`${units} units on the permit`);
  }

  const contractorText = `${p.contractor ?? ""} ${p.builder ?? ""}`.toLowerCase();
  if (/\bllc\b|\bl\.l\.c\.\b|\blp\b|\bl\.p\.\b|\binc\b/.test(contractorText)) {
    score += 20;
    reasons.push("contractor/builder name suggests a business entity (LLC/LP/Inc)");
  }

  const text = textBlob(p);
  const hits = INVESTMENT_KEYWORDS.filter((kw) => text.includes(kw));
  if (hits.length > 0) {
    score += Math.min(30, 10 * hits.length);
    reasons.push(`keywords: ${hits.join(", ")}`);
  }

  score = round1(Math.min(100, score));
  if (reasons.length === 0) {
    return [0, "No multi-unit, business-entity, or investment keywords detected -- defaulting to 0 (likely owner-occupied)."];
  }
  return [score, `Investment-property likelihood based on: ${reasons.join("; ")} -> ${score}/100.`];
}

function scoreConfidence(p: ScoringInput): [number, string] {
  const fields: [string, unknown][] = [
    ["estimated_cost", p.estimated_cost],
    ["valuation", p.valuation],
    ["square_footage", p.square_footage],
    ["units", p.units],
    ["description", p.description],
    ["permit_type", p.permit_type],
    ["work_category", p.work_category],
    ["issue_date", p.issue_date],
    ["property_address", p.property_address],
  ];
  const present = fields.filter(([, v]) => v !== null && v !== undefined && v !== "");
  const ratio = present.length / fields.length;
  const score = round1(ratio * 100);
  const names = present.map(([n]) => n).join(", ") || "none";
  return [score, `${present.length}/${fields.length} key fields populated (${names}) -> ${score}/100 confidence.`];
}

function scoreLead(
  projectSize: number,
  urgency: number,
  luxury: number,
  investment: number,
  confidence: number,
  budgetTier: string
): [number, string] {
  const tierWeight: Record<string, number> = {
    unknown: 0.0,
    micro: 0.1,
    small: 0.3,
    medium: 0.6,
    large: 0.85,
    major: 1.0,
  };
  const weight = tierWeight[budgetTier] ?? 0.3;
  const raw =
    0.35 * projectSize + 0.2 * urgency + 0.15 * luxury + 0.15 * investment + 0.15 * (weight * 100);
  const confidenceMultiplier = 0.5 + 0.5 * (confidence / 100);
  const final = round1(Math.min(100, raw * confidenceMultiplier));
  const explanation = `Lead score = weighted blend of project_size(${projectSize}), urgency(${urgency}), luxury(${luxury}), investment_likelihood(${investment}), and budget_tier('${budgetTier}'), scaled by data confidence (${confidence}%) -> ${final}/100.`;
  return [final, explanation];
}

export function scorePermit(p: ScoringInput, now: Date = new Date()): ScoreComputed {
  const [projectSize, projectSizeExpl] = scoreProjectSize(p);
  const [tier, tierExpl] = scoreBudgetTier(p);
  const [urgency, urgencyExpl] = scoreUrgency(p, now);
  const [luxury, luxuryExpl] = scoreLuxuryLikelihood(p);
  const [remodelRepair, remodelRepairExpl] = classifyRemodelVsRepair(p);
  const [investment, investmentExpl] = scoreInvestmentPropertyLikelihood(p);
  const [confidence, confidenceExpl] = scoreConfidence(p);
  const [lead, leadExpl] = scoreLead(projectSize, urgency, luxury, investment, confidence, tier);

  return {
    project_size_score: projectSize,
    project_size_explanation: projectSizeExpl,
    budget_tier: tier,
    budget_tier_explanation: tierExpl,
    urgency_score: urgency,
    urgency_explanation: urgencyExpl,
    luxury_likelihood: luxury,
    luxury_explanation: luxuryExpl,
    remodel_vs_repair: remodelRepair,
    remodel_vs_repair_explanation: remodelRepairExpl,
    investment_property_likelihood: investment,
    investment_property_explanation: investmentExpl,
    lead_score: lead,
    lead_score_explanation: leadExpl,
    confidence_score: confidence,
    confidence_explanation: confidenceExpl,
  };
}
