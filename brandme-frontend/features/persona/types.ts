import type { components } from '@brandme/contracts'
export const AXES = [
  ['temperature','Palette','Warm','Cool'], ['sport_couture','Style language','Sport','Couture'],
  ['expression','Expression','Understated','Expressive'], ['fit_language','Silhouette','Tailored','Relaxed'],
  ['detail','Detail','Minimal','Ornate'], ['novelty','Novelty','Timeless','Experimental'],
  ['color','Color','Neutral','Colorful'], ['finish','Finish','Matte','Lustrous'],
  ['structure','Structure','Structured','Fluid'], ['setting','Setting','Urban','Outdoors'],
  ['exploration','Discovery','Familiar','Exploratory'], ['utility','Utility','Functional','Decorative'],
] as const
export type AxisKey = typeof AXES[number][0]
export interface Axis { axis: AxisKey; declared: number|null; inferred: number|null; effective: number|null;
  inferred_confidence: number|null; inferred_evidence_count: number; effective_source: string;
  locked: boolean; inference_allowed: boolean; hidden: boolean; adapt_enabled: boolean }
/** Lane extension PD-01, verified against consumer-domains service DTO at dafd3b1. */
export interface Persona {
  profile: components['schemas']['PersonaProfile']; axes: Axis[];
  constraints: { budget_ceiling_minor: string|null; budget_currency: string|null; excluded_brands: string[];
    excluded_materials: string[]; prefer_owned: boolean; social_signals_enabled: boolean; goals: string[] };
  context_overrides: { override_id: string; label: string; active: boolean; enabled: boolean }[];
  adaptation_proposals: { axis: string; current: number; proposed: number; requires_confirmation: boolean }[];
}
export interface Recommendations { basis: string; rule_version: string; items: {
  product_id: string; title: string; sponsored: boolean; labels: string[];
  reasons: { text?: string; explanation?: string; code?: string }[] }[] }
