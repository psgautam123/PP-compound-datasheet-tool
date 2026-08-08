import type {
  ApiErrorBody,
  BlendResponse,
  CorrelationProposalJson,
  ExtractedGradeJson,
  GradeSummary,
  PendingCorrelationDetail,
  PendingCorrelationSummary,
  PendingExtractionDetail,
  PendingExtractionSummary,
  PendingStatus,
  ResearchCorrelationResult,
  SearchResponse,
  TargetProperties,
  VisbreakingResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as ApiErrorBody).detail ?? detail;
    } catch {
      // response wasn't JSON; fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function patchJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function listGrades(): Promise<GradeSummary[]> {
  return fetch(`${API_BASE}/grades`).then((r) => r.json());
}

export function datasheetUrl(gradeId: string): string {
  return `${API_BASE}/grades/${encodeURIComponent(gradeId)}/datasheet`;
}

export function searchGrades(targetProperties: TargetProperties): Promise<SearchResponse> {
  return postJson("/search", { target_properties: targetProperties });
}

export function predictBlend(targetProperties: TargetProperties): Promise<BlendResponse> {
  return postJson("/blend", { target_properties: targetProperties });
}

export function proposeVisbreaking(targetProperties: TargetProperties): Promise<VisbreakingResponse> {
  return postJson("/visbreaking", { target_properties: targetProperties });
}

// --- Extraction review queue (architecture plan §2) ---

function statusQuery(status?: PendingStatus): string {
  return status ? `?status=${encodeURIComponent(status)}` : "";
}

export function listExtractions(status?: PendingStatus): Promise<PendingExtractionSummary[]> {
  return getJson(`/extractions${statusQuery(status)}`);
}

export function getExtraction(id: number): Promise<PendingExtractionDetail> {
  return getJson(`/extractions/${id}`);
}

export function submitExtraction(file: File): Promise<PendingExtractionDetail> {
  const form = new FormData();
  form.append("file", file);
  return request(`/extractions`, { method: "POST", body: form });
}

export function patchExtraction(id: number, extracted_json: ExtractedGradeJson): Promise<PendingExtractionDetail> {
  return patchJson(`/extractions/${id}`, { extracted_json });
}

export function approveExtraction(id: number, reviewed_by: string): Promise<PendingExtractionDetail> {
  return postJson(`/extractions/${id}/approve`, { reviewed_by });
}

export function rejectExtraction(
  id: number,
  reviewed_by: string,
  reviewer_notes: string,
): Promise<PendingExtractionDetail> {
  return postJson(`/extractions/${id}/reject`, { reviewed_by, reviewer_notes });
}

// --- Correlation research queue (architecture plan §6) ---

export function listCorrelations(status?: PendingStatus): Promise<PendingCorrelationSummary[]> {
  return getJson(`/correlations${statusQuery(status)}`);
}

export function getCorrelation(id: number): Promise<PendingCorrelationDetail> {
  return getJson(`/correlations/${id}`);
}

export function runCorrelationResearch(family_key: string): Promise<ResearchCorrelationResult> {
  return postJson("/correlations/research", { family_key });
}

export function patchCorrelation(
  id: number,
  proposed_json: CorrelationProposalJson,
): Promise<PendingCorrelationDetail> {
  return patchJson(`/correlations/${id}`, { proposed_json });
}

export function approveCorrelation(id: number, reviewed_by: string): Promise<PendingCorrelationDetail> {
  return postJson(`/correlations/${id}/approve`, { reviewed_by });
}

export function rejectCorrelation(
  id: number,
  reviewed_by: string,
  reviewer_notes: string,
): Promise<PendingCorrelationDetail> {
  return postJson(`/correlations/${id}/reject`, { reviewed_by, reviewer_notes });
}
