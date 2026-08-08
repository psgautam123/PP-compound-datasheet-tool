// Mirrors backend/api/schemas.py. Keep in sync manually -- small enough
// surface that a codegen step isn't worth it yet.

export interface GradeSummary {
  grade_id: string;
  product_name: string;
  family: string;
  filler_type: string;
  filler_content_pct: number | null;
  density_kg_m3: number | null;
  mfr: number | null;
  tensile_modulus: number | null;
}

export interface PropertyOut {
  key: string;
  cls: string;
  value: number;
  unit: string;
  condition: Record<string, unknown>;
  test_method: string | null;
}

export interface GradeDetail extends GradeSummary {
  source_pdf: string;
  mould_shrinkage_pct: number | null;
  properties: PropertyOut[];
}

// --- Step 1: search ---

export interface PropertyMatchOut {
  key: string;
  target: number;
  actual: number;
  relative_error: number;
  within_margin: boolean;
}

export interface GradeMatchOut {
  grade: GradeSummary;
  source_pdf: string;
  matches: PropertyMatchOut[];
  max_relative_error: number;
}

export interface SearchResponse {
  matches: GradeMatchOut[];
}

// --- Step 2: blend ---

export interface PropertyPredictionOut {
  key: string;
  target: number;
  predicted: number;
  relative_error: number;
  within_margin: boolean;
  method: string;
}

export interface BlendResultOut {
  grade_a: GradeSummary;
  grade_b: GradeSummary;
  phi_a: number;
  wt_pct_a: number;
  predictions: PropertyPredictionOut[];
  within_tolerance: boolean;
  max_relative_error: number;
}

export interface BlendResponse {
  solution_found: boolean;
  result: BlendResultOut | null;
  visbreaking_prompt: string | null;
}

// --- Step 3: visbreaking ---

export interface DoeRunOut {
  dose_wt_pct: number;
  temp_C: number;
  residence_time_min: number;
  predicted_mfi: number;
}

export interface VisbreakingResultOut {
  base_grade: GradeSummary;
  target_mfr: number;
  final_mfi_design_point: number;
  peroxide_dose_wt_pct: number;
  process: string;
  temp_C: number;
  residence_time_min: number;
  peroxide_family_key: string;
  correlation_source_citation: string | null;
  doe: DoeRunOut[];
}

export interface VisbreakingResponse {
  solution_found: boolean;
  result: VisbreakingResultOut | null;
}

export type TargetProperties = Record<string, number>;

export type FlowStep = "idle" | "search" | "blend" | "visbreaking_prompt" | "visbreaking" | "done";

export interface ApiErrorBody {
  detail: string;
}

// --- Review queues (architecture plan §2 and §6) ---

export type PendingStatus = "pending_review" | "approved" | "rejected";

export interface ExtractedPropertyCondition {
  temp_C?: number | null;
  load_kg?: number | null;
  load_MPa?: number | null;
  load_N?: number | null;
  range_C?: string | null;
  rating?: string | null;
  note?: string | null;
}

export interface ExtractedProperty {
  key: string;
  cls: string;
  value: number | null;
  unit: string;
  condition: ExtractedPropertyCondition;
  test_method: string | null;
}

export interface ExtractedGradeJson {
  grade_id: string;
  product_name: string;
  source_pdf: string;
  family: string;
  filler_type: string;
  filler_content_pct: number | null;
  density_kg_m3: number | null;
  mould_shrinkage_pct: number | null;
  properties: ExtractedProperty[];
  extraction_notes: string | null;
}

export interface PendingExtractionSummary {
  id: number;
  source_pdf_filename: string;
  status: PendingStatus;
  submitted_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  grade_id: string | null;
  family: string | null;
}

export interface PendingExtractionDetail extends PendingExtractionSummary {
  extracted_json: ExtractedGradeJson;
  extraction_notes: string | null;
  reviewer_notes: string | null;
  promoted_grade_pk: number | null;
}

export interface CorrelationProposalJson {
  family_key: string;
  name: string;
  ln_mfi_coefficient: number;
  ea_kj_mol: number;
  reference_temp_C: number;
  reference_residence_time_min: number;
  source_citation: string;
  rationale: string;
}

export interface PendingCorrelationSummary {
  id: number;
  family_key: string;
  status: PendingStatus;
  submitted_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  proposed_name: string | null;
}

export interface PendingCorrelationDetail extends PendingCorrelationSummary {
  proposed_json: CorrelationProposalJson;
  search_summary: string;
  reviewer_notes: string | null;
  promoted_correlation_pk: number | null;
}

export interface ResearchCorrelationResult {
  family_key: string;
  update_recommended: boolean;
  search_summary: string;
  pending_correlation_id: number | null;
}
