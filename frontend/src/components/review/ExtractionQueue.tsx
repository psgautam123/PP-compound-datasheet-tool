import { useEffect, useRef, useState } from "react";
import {
  approveExtraction,
  getExtraction,
  listExtractions,
  patchExtraction,
  rejectExtraction,
  submitExtraction,
} from "../../api";
import { ApiError } from "../../api";
import type { ExtractedGradeJson, ExtractedPropertyCondition, PendingExtractionSummary, PendingStatus } from "../../types";
import { formatNumber, propertyLabel } from "../../format";
import { StatusBadge } from "./StatusBadge";

const FILTERS: { label: string; value: PendingStatus | undefined }[] = [
  { label: "Pending", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "All", value: undefined },
];

function formatCondition(c: ExtractedPropertyCondition): string {
  const parts: string[] = [];
  if (c.temp_C != null) parts.push(`${c.temp_C}°C`);
  if (c.load_kg != null) parts.push(`${c.load_kg} kg`);
  if (c.load_MPa != null) parts.push(`${c.load_MPa} MPa`);
  if (c.load_N != null) parts.push(`${c.load_N} N`);
  if (c.range_C) parts.push(c.range_C);
  if (c.rating) parts.push(c.rating);
  if (c.note) parts.push(c.note);
  return parts.join(", ");
}

export function ExtractionQueue({ reviewerName }: { reviewerName: string }) {
  const [filter, setFilter] = useState<PendingStatus | undefined>("pending_review");
  const [list, setList] = useState<PendingExtractionSummary[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [jsonDraft, setJsonDraft] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof getExtraction>> | null>(null);

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [showReject, setShowReject] = useState(false);
  const [rejectNotes, setRejectNotes] = useState("");

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadPending, setUploadPending] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const requestId = useRef(0);

  async function refreshList() {
    setListLoading(true);
    setListError(null);
    try {
      const rows = await listExtractions(filter);
      setList(rows);
    } catch (e) {
      setListError(e instanceof ApiError ? e.message : "Couldn't load the extraction queue.");
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    refreshList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    const myRequest = ++requestId.current;
    setDetailLoading(true);
    setActionError(null);
    setShowReject(false);
    setRejectNotes("");
    getExtraction(selectedId)
      .then((d) => {
        if (requestId.current !== myRequest) return;
        setDetail(d);
        setJsonDraft(JSON.stringify(d.extracted_json, null, 2));
        setJsonError(null);
      })
      .catch((e) => {
        if (requestId.current !== myRequest) return;
        setActionError(e instanceof ApiError ? e.message : "Couldn't load that extraction.");
      })
      .finally(() => {
        if (requestId.current === myRequest) setDetailLoading(false);
      });
  }, [selectedId]);

  async function handleUpload() {
    if (!uploadFile) return;
    setUploadPending(true);
    setUploadError(null);
    try {
      const created = await submitExtraction(uploadFile);
      setUploadFile(null);
      setFilter("pending_review");
      await refreshList();
      setSelectedId(created.id);
    } catch (e) {
      setUploadError(e instanceof ApiError ? e.message : "Extraction failed. Please try again.");
    } finally {
      setUploadPending(false);
    }
  }

  function handleJsonChange(value: string) {
    setJsonDraft(value);
    try {
      JSON.parse(value);
      setJsonError(null);
    } catch {
      setJsonError("This isn't valid JSON yet.");
    }
  }

  async function handleSaveCorrection() {
    if (!detail) return;
    let parsed: ExtractedGradeJson;
    try {
      parsed = JSON.parse(jsonDraft);
    } catch {
      setJsonError("This isn't valid JSON yet.");
      return;
    }
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await patchExtraction(detail.id, parsed);
      setDetail(updated);
      setJsonDraft(JSON.stringify(updated.extracted_json, null, 2));
      await refreshList();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Couldn't save that correction.");
    } finally {
      setActionPending(false);
    }
  }

  async function handleApprove() {
    if (!detail || !reviewerName.trim()) return;
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await approveExtraction(detail.id, reviewerName.trim());
      setDetail(updated);
      await refreshList();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Couldn't approve this extraction.");
    } finally {
      setActionPending(false);
    }
  }

  async function handleReject() {
    if (!detail || !reviewerName.trim() || !rejectNotes.trim()) return;
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await rejectExtraction(detail.id, reviewerName.trim(), rejectNotes.trim());
      setDetail(updated);
      setShowReject(false);
      await refreshList();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Couldn't reject this extraction.");
    } finally {
      setActionPending(false);
    }
  }

  const grade = detail?.extracted_json;
  const isDecided = detail && detail.status !== "pending_review";

  return (
    <div className="review-queue">
      <section className="upload-form">
        <h2>Submit a new datasheet</h2>
        <p className="result-subtitle">
          Upload a vendor PDF to run the extraction agent. The result lands here for review -- it is never
          searchable until you approve it.
        </p>
        <div className="upload-row">
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
          />
          <button className="btn-primary" disabled={!uploadFile || uploadPending} onClick={handleUpload}>
            {uploadPending ? "Extracting…" : "Extract"}
          </button>
        </div>
        {uploadError && <div className="form-error">{uploadError}</div>}
      </section>

      <div className="review-layout">
        <aside className="review-list-panel">
          <div className="review-filters" role="tablist">
            {FILTERS.map((f) => (
              <button
                key={f.label}
                role="tab"
                aria-selected={filter === f.value}
                className={filter === f.value ? "review-filter review-filter-active" : "review-filter"}
                onClick={() => {
                  setFilter(f.value);
                }}
              >
                {f.label}
              </button>
            ))}
          </div>

          {listLoading && <p className="result-loading">Loading…</p>}
          {listError && <div className="form-error">{listError}</div>}
          {!listLoading && !listError && list.length === 0 && (
            <p className="review-empty">No extractions in this view.</p>
          )}

          <ul className="review-list">
            {list.map((item) => (
              <li key={item.id}>
                <button
                  className={item.id === selectedId ? "review-list-item review-list-item-active" : "review-list-item"}
                  onClick={() => setSelectedId(item.id)}
                >
                  <span className="review-list-item-title">{item.grade_id ?? item.source_pdf_filename}</span>
                  <span className="review-list-item-sub">{item.source_pdf_filename}</span>
                  <StatusBadge status={item.status} />
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="review-detail">
          {selectedId == null && <p className="review-empty">Select an extraction from the list to review it.</p>}
          {selectedId != null && detailLoading && <p className="result-loading">Loading…</p>}

          {detail && grade && !detailLoading && (
            <>
              <div className="review-detail-header">
                <div>
                  <h2>{grade.product_name || grade.grade_id}</h2>
                  <p className="review-detail-sub">
                    {detail.source_pdf_filename} &middot; submitted {new Date(detail.submitted_at).toLocaleString()}
                  </p>
                </div>
                <StatusBadge status={detail.status} />
              </div>

              {grade.extraction_notes && (
                <div className="review-callout">
                  <strong>Agent flagged for review:</strong> {grade.extraction_notes}
                </div>
              )}

              {isDecided && (
                <div className="review-decided-note">
                  Reviewed by {detail.reviewed_by} on{" "}
                  {detail.reviewed_at ? new Date(detail.reviewed_at).toLocaleString() : "—"}.
                  {detail.reviewer_notes && <> Notes: {detail.reviewer_notes}</>}
                  {detail.promoted_grade_pk != null && <> Promoted to grade #{detail.promoted_grade_pk}.</>}
                </div>
              )}

              <dl className="review-fact-grid">
                <div>
                  <dt>Grade ID</dt>
                  <dd>{grade.grade_id}</dd>
                </div>
                <div>
                  <dt>Family</dt>
                  <dd>{grade.family}</dd>
                </div>
                <div>
                  <dt>Filler</dt>
                  <dd>
                    {grade.filler_type}
                    {grade.filler_content_pct != null ? ` (${grade.filler_content_pct}%)` : ""}
                  </dd>
                </div>
                <div>
                  <dt>Density</dt>
                  <dd>{grade.density_kg_m3 != null ? `${grade.density_kg_m3} kg/m³` : "—"}</dd>
                </div>
              </dl>

              <table className="property-table">
                <thead>
                  <tr>
                    <th>Property</th>
                    <th>Value</th>
                    <th>Condition</th>
                    <th>Method</th>
                  </tr>
                </thead>
                <tbody>
                  {grade.properties.map((p, i) => (
                    <tr key={`${p.key}-${i}`}>
                      <td>{propertyLabel(p.key)}</td>
                      <td>
                        {p.value != null ? formatNumber(p.value) : "No result"} <span className="unit">{p.unit}</span>
                      </td>
                      <td className="method-cell">{formatCondition(p.condition)}</td>
                      <td className="method-cell">{p.test_method ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="json-editor-block">
                <label htmlFor="extraction-json">Correct extracted data (JSON)</label>
                <textarea
                  id="extraction-json"
                  className="json-editor"
                  value={jsonDraft}
                  onChange={(e) => handleJsonChange(e.target.value)}
                  disabled={!!isDecided}
                  spellCheck={false}
                  rows={14}
                />
                {jsonError && <div className="form-error">{jsonError}</div>}
                {!isDecided && (
                  <button
                    className="btn-secondary"
                    disabled={!!jsonError || actionPending}
                    onClick={handleSaveCorrection}
                  >
                    Save correction
                  </button>
                )}
              </div>

              {actionError && <div className="form-error">{actionError}</div>}

              {!isDecided && (
                <div className="review-actions">
                  {!showReject ? (
                    <>
                      <button
                        className="btn-primary"
                        disabled={!reviewerName.trim() || actionPending}
                        onClick={handleApprove}
                        title={!reviewerName.trim() ? "Enter your name above first" : undefined}
                      >
                        Approve &amp; promote to live grade
                      </button>
                      <button className="btn-secondary" disabled={actionPending} onClick={() => setShowReject(true)}>
                        Reject
                      </button>
                    </>
                  ) : (
                    <div className="reject-form">
                      <label htmlFor="reject-notes">Why is this being rejected?</label>
                      <textarea
                        id="reject-notes"
                        rows={3}
                        value={rejectNotes}
                        onChange={(e) => setRejectNotes(e.target.value)}
                        placeholder="e.g. MFR looks OCR-garbled, resubmit a clearer scan."
                      />
                      <div className="prompt-actions">
                        <button
                          className="btn-primary"
                          disabled={!reviewerName.trim() || !rejectNotes.trim() || actionPending}
                          onClick={handleReject}
                        >
                          Confirm reject
                        </button>
                        <button className="btn-secondary" onClick={() => setShowReject(false)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
