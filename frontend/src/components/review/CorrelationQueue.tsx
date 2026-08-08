import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  approveCorrelation,
  getCorrelation,
  listCorrelations,
  patchCorrelation,
  rejectCorrelation,
  runCorrelationResearch,
} from "../../api";
import type { CorrelationProposalJson, PendingCorrelationSummary, PendingStatus } from "../../types";
import { StatusBadge } from "./StatusBadge";

const FILTERS: { label: string; value: PendingStatus | undefined }[] = [
  { label: "Pending", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "All", value: undefined },
];

const FAMILIES = [
  { value: "homopolymer", label: "Homopolymer PP" },
  { value: "impact_pp", label: "Impact (heterophasic) PP" },
];

export function CorrelationQueue({ reviewerName }: { reviewerName: string }) {
  const [filter, setFilter] = useState<PendingStatus | undefined>("pending_review");
  const [list, setList] = useState<PendingCorrelationSummary[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [jsonDraft, setJsonDraft] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof getCorrelation>> | null>(null);

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [showReject, setShowReject] = useState(false);
  const [rejectNotes, setRejectNotes] = useState("");

  const [researchFamily, setResearchFamily] = useState(FAMILIES[0].value);
  const [researchPending, setResearchPending] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);
  const [researchResult, setResearchResult] = useState<{ family_key: string; recommended: boolean; summary: string } | null>(null);

  const requestId = useRef(0);

  async function refreshList() {
    setListLoading(true);
    setListError(null);
    try {
      const rows = await listCorrelations(filter);
      setList(rows);
    } catch (e) {
      setListError(e instanceof ApiError ? e.message : "Couldn't load the correlation queue.");
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
    getCorrelation(selectedId)
      .then((d) => {
        if (requestId.current !== myRequest) return;
        setDetail(d);
        setJsonDraft(JSON.stringify(d.proposed_json, null, 2));
        setJsonError(null);
      })
      .catch((e) => {
        if (requestId.current !== myRequest) return;
        setActionError(e instanceof ApiError ? e.message : "Couldn't load that proposal.");
      })
      .finally(() => {
        if (requestId.current === myRequest) setDetailLoading(false);
      });
  }, [selectedId]);

  async function handleRunResearch() {
    setResearchPending(true);
    setResearchError(null);
    setResearchResult(null);
    try {
      const res = await runCorrelationResearch(researchFamily);
      setResearchResult({
        family_key: res.family_key,
        recommended: res.update_recommended,
        summary: res.search_summary,
      });
      if (res.pending_correlation_id != null) {
        setFilter("pending_review");
        await refreshList();
        setSelectedId(res.pending_correlation_id);
      }
    } catch (e) {
      setResearchError(e instanceof ApiError ? e.message : "Correlation research failed. Please try again.");
    } finally {
      setResearchPending(false);
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
    let parsed: CorrelationProposalJson;
    try {
      parsed = JSON.parse(jsonDraft);
    } catch {
      setJsonError("This isn't valid JSON yet.");
      return;
    }
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await patchCorrelation(detail.id, parsed);
      setDetail(updated);
      setJsonDraft(JSON.stringify(updated.proposed_json, null, 2));
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
      const updated = await approveCorrelation(detail.id, reviewerName.trim());
      setDetail(updated);
      await refreshList();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Couldn't approve this proposal.");
    } finally {
      setActionPending(false);
    }
  }

  async function handleReject() {
    if (!detail || !reviewerName.trim() || !rejectNotes.trim()) return;
    setActionPending(true);
    setActionError(null);
    try {
      const updated = await rejectCorrelation(detail.id, reviewerName.trim(), rejectNotes.trim());
      setDetail(updated);
      setShowReject(false);
      await refreshList();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Couldn't reject this proposal.");
    } finally {
      setActionPending(false);
    }
  }

  const proposal = detail?.proposed_json;
  const isDecided = detail && detail.status !== "pending_review";

  return (
    <div className="review-queue">
      <section className="upload-form">
        <h2>Check for a better correlation</h2>
        <p className="result-subtitle">
          Runs the research agent against the current peer-reviewed literature for one PP family. A proposal is
          only queued here if it recommends an actual change.
        </p>
        <div className="upload-row">
          <select value={researchFamily} onChange={(e) => setResearchFamily(e.target.value)}>
            {FAMILIES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <button className="btn-primary" disabled={researchPending} onClick={handleRunResearch}>
            {researchPending ? "Searching literature…" : "Run research"}
          </button>
        </div>
        {researchError && <div className="form-error">{researchError}</div>}
        {researchResult && (
          <div className={researchResult.recommended ? "review-callout" : "review-decided-note"}>
            {researchResult.recommended
              ? "Update recommended -- see the new pending proposal below."
              : "No update recommended for this family."}{" "}
            {researchResult.summary}
          </div>
        )}
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
                onClick={() => setFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {listLoading && <p className="result-loading">Loading…</p>}
          {listError && <div className="form-error">{listError}</div>}
          {!listLoading && !listError && list.length === 0 && (
            <p className="review-empty">No correlation proposals in this view.</p>
          )}

          <ul className="review-list">
            {list.map((item) => (
              <li key={item.id}>
                <button
                  className={item.id === selectedId ? "review-list-item review-list-item-active" : "review-list-item"}
                  onClick={() => setSelectedId(item.id)}
                >
                  <span className="review-list-item-title">{item.proposed_name ?? item.family_key}</span>
                  <span className="review-list-item-sub">{item.family_key}</span>
                  <StatusBadge status={item.status} />
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="review-detail">
          {selectedId == null && (
            <p className="review-empty">Select a proposal from the list, or run research above.</p>
          )}
          {selectedId != null && detailLoading && <p className="result-loading">Loading…</p>}

          {detail && proposal && !detailLoading && (
            <>
              <div className="review-detail-header">
                <div>
                  <h2>{proposal.name}</h2>
                  <p className="review-detail-sub">
                    {proposal.family_key} &middot; submitted {new Date(detail.submitted_at).toLocaleString()}
                  </p>
                </div>
                <StatusBadge status={detail.status} />
              </div>

              <div className="review-callout">
                <strong>Rationale:</strong> {proposal.rationale}
              </div>

              <div className="review-callout review-callout-muted">
                <strong>Search summary:</strong> {detail.search_summary}
              </div>

              {isDecided && (
                <div className="review-decided-note">
                  Reviewed by {detail.reviewed_by} on{" "}
                  {detail.reviewed_at ? new Date(detail.reviewed_at).toLocaleString() : "—"}.
                  {detail.reviewer_notes && <> Notes: {detail.reviewer_notes}</>}
                  {detail.promoted_correlation_pk != null && (
                    <> Promoted to correlation_library #{detail.promoted_correlation_pk}.</>
                  )}
                </div>
              )}

              <dl className="review-fact-grid">
                <div>
                  <dt>ln(MFI) coefficient</dt>
                  <dd>{proposal.ln_mfi_coefficient}</dd>
                </div>
                <div>
                  <dt>Ea (kJ/mol)</dt>
                  <dd>{proposal.ea_kj_mol}</dd>
                </div>
                <div>
                  <dt>Reference temp</dt>
                  <dd>{proposal.reference_temp_C} °C</dd>
                </div>
                <div>
                  <dt>Reference residence time</dt>
                  <dd>{proposal.reference_residence_time_min} min</dd>
                </div>
              </dl>

              <p className="citation-footnote">
                <strong>Citation:</strong> {proposal.source_citation}
              </p>

              <div className="json-editor-block">
                <label htmlFor="correlation-json">Correct proposed data (JSON)</label>
                <textarea
                  id="correlation-json"
                  className="json-editor"
                  value={jsonDraft}
                  onChange={(e) => handleJsonChange(e.target.value)}
                  disabled={!!isDecided}
                  spellCheck={false}
                  rows={12}
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
                        Approve &amp; activate this version
                      </button>
                      <button className="btn-secondary" disabled={actionPending} onClick={() => setShowReject(true)}>
                        Reject
                      </button>
                    </>
                  ) : (
                    <div className="reject-form">
                      <label htmlFor="reject-correlation-notes">Why is this being rejected?</label>
                      <textarea
                        id="reject-correlation-notes"
                        rows={3}
                        value={rejectNotes}
                        onChange={(e) => setRejectNotes(e.target.value)}
                        placeholder="e.g. Citation doesn't hold up on review."
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
