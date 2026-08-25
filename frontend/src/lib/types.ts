/** Mirrors ghostnet.schemas / ghostnet.export — keep the two in step. */

export type EvidenceKind =
  | "sentinel2_tile"
  | "current_field"
  | "drifter_track"
  | "river_table"
  | "vessel_record"
  | "mpa_boundary"
  | "derived";

export interface Evidence {
  kind: EvidenceKind;
  ref: string;
  detail: string;
}

export interface Detection {
  id: string;
  tile_id: string;
  acquired_at: string;
  lon: number;
  lat: number;
  area_px: number;
  area_km2: number;
  fdi_mean: number;
  ndvi_mean: number;
  confidence: number;
  detector: "fdi" | "cnn";
  evidence: Evidence[];
}

export interface CheckResult {
  name: string;
  disqualified: boolean;
  reason: string;
  detail: Record<string, number>;
}

export interface VerificationResult {
  detection_id: string;
  verified: boolean;
  checks: CheckResult[];
  confidence: number;
  evidence: Evidence[];
}

export interface TrajectoryPoint {
  t: string;
  lon: number;
  lat: number;
  uncertainty_km: number;
}

export interface Trajectory {
  detection_id: string;
  direction: "backward" | "forward";
  horizon_days: number;
  points: TrajectoryPoint[];
  ensemble_size: number;
  seed: number;
  current_field: string;
  evidence: Evidence[];
}

export interface RiverCandidate {
  name: string;
  lon: number;
  lat: number;
  emission_tonnes_yr: number;
  distance_km: number;
  probability: number;
}

export interface SourceAttribution {
  detection_id: string;
  candidates: RiverCandidate[];
  note: string;
  evidence: Evidence[];
}

export interface VesselDetection {
  id: string;
  lon: number;
  lat: number;
  detected_at: string;
  length_m: number | null;
  matched_ais_mmsi: string | null;
}

export interface VesselCorrelation {
  detection_id: string;
  dark_vessels: VesselDetection[];
  matched_vessels: number;
  correlation_strength: number;
  disclaimer: string;
  evidence: Evidence[];
}

export interface PriorityScore {
  detection_id: string;
  score: number;
  components: Record<string, number>;
  weights: Record<string, number>;
  nearest_mpa_km: number | null;
  evidence: Evidence[];
}

export interface DispatchAssignment {
  rank: number;
  detection_id: string;
  vessel_id: string;
  lon: number;
  lat: number;
  score: number;
  rationale: string;
  rationale_source: "llm" | "template";
  evidence: Evidence[];
}

export interface DispatchPlan {
  region_id: string;
  generated_at: string;
  vessel_capacity: number;
  planning_horizon_days: number;
  assignments: DispatchAssignment[];
  deferred: string[];
  approved: boolean;
  approved_by: string | null;
  caveats: string[];
}

export interface ProtectedArea {
  name: string;
  lon: number;
  lat: number;
  radius_km: number;
  designation: string;
}

export interface RunProvenance {
  generated_at: string;
  generated_on: string;
  ghostnet_version: string;
  git_commit: string | null;
  inputs_are_synthetic: boolean;
  tile_ids: string[];
  tile_count: number;
  dataset_sources: Record<string, string>;
  fdi_threshold: number;
  min_pixels: number;
  verification_thresholds: Record<string, number>;
  drift_ensemble_size: number;
  drift_seed: number;
  notes: string[];
}

export interface RunRegion {
  id: string;
  name: string;
  bbox: [number, number, number, number] | null;
  window_start: string | null;
  window_end: string | null;
}

export interface RunArtefact {
  schema_version: string;
  run_id: string;
  region: RunRegion;
  provenance: RunProvenance;
  detections: Detection[];
  verifications: VerificationResult[];
  backward: Record<string, Trajectory>;
  forward: Record<string, Trajectory>;
  attributions: Record<string, SourceAttribution>;
  correlations: Record<string, VesselCorrelation>;
  protected_areas: ProtectedArea[];
  degradations: string[];
}

export interface RunSummary {
  run_id: string;
  region_id?: string;
  region_name?: string;
  generated_at?: string;
  inputs_are_synthetic?: boolean;
  detections?: number;
  verified?: number;
  rejected?: number;
  trajectories?: number;
  attributions?: number;
  correlations?: number;
  has_mpa_data?: boolean;
  degradations?: number;
  unreadable?: boolean;
  error?: string;
}

export interface PlanResponse {
  run_id: string;
  plan: DispatchPlan | null;
  scores: PriorityScore[];
  degradations: string[];
  considered: number;
  ablated: string[];
}

export interface RejectedEntry {
  detection: Detection | null;
  verification: VerificationResult;
  reasons: string[];
  failed_checks: string[];
}

export interface RejectedResponse {
  run_id: string;
  rejected: RejectedEntry[];
  count: number;
  detections_total: number;
}

export interface AgentMeta {
  id: string;
  name: string;
  fr: string;
}

export interface AppMeta {
  version: string;
  artefact_schema: string;
  prototype_notice: string;
  ablatable_agents: string[];
  rationale_source: "llm" | "template";
  rationale_note: string;
  approvals_durable: boolean;
  agents: AgentMeta[];
}

/** Mirrors ghostnet.benchmark — the measured numbers, never recomputed here. */
export interface DetectorRecall {
  split: string;
  regions: number;
  regions_hit: number;
  regions_missed: number;
  region_recall: number;
}

export interface VerificationDelta {
  split: string;
  scored: number;
  excluded_unlabelled: number;
  baseline_precision: number;
  verified_precision: number;
  baseline_recall: number;
  verified_recall: number;
  baseline_f1: number;
  verified_f1: number;
  precision_gain: number;
  f1_gain: number;
  recall_cost: number;
  baseline_false_positive_rate: number;
  verified_false_positive_rate: number;
}

/** FR-2.2, measured — and measured as costing quality, not adding it. */
export interface MultiTemporalResult {
  tile: string;
  date_a: string;
  date_b: string;
  candidates_labelled: number;
  baseline_f1: number;
  with_check_f1: number;
  baseline_recall: number;
  with_check_recall: number;
  rejections: number;
  true_debris_lost: number;
  transients_found: number;
  current_speed_ms: number | null;
  f1_delta: number;
  recall_delta: number;
  contributes: boolean;
}

export interface BenchmarkReport {
  available: boolean;
  unavailable_reason: string | null;
  dataset: string;
  dataset_version: string;
  dataset_doi: string;
  source_file: string;
  results_doc: string;
  fdi_threshold: number | null;
  detector: DetectorRecall | null;
  verification: VerificationDelta | null;
  multi_temporal: MultiTemporalResult | null;
  multi_temporal_caveats: string[];
  caveats: string[];
}

export interface ApprovalRecord {
  run_id: string;
  reviewer: string;
  approved_at: string;
  vessel_capacity: number;
  ablated: string[];
  detection_ids: string[];
  note: string;
  durable: boolean;
}
