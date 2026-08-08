// Workflow2.txt §21: the exact branch point -- "If No, stop." must be a
// real, low-friction exit (Nielsen heuristic #3, user control & freedom),
// not a dead end or a buried option.
export function VisbreakingPrompt({
  promptText,
  onYes,
  onNo,
  loading,
}: {
  promptText: string;
  onYes: () => void;
  onNo: () => void;
  loading: boolean;
}) {
  return (
    <div className="result-panel result-prompt">
      <h2>No blend solution found</h2>
      <p>{promptText}</p>
      <div className="prompt-actions">
        <button className="btn-primary" onClick={onYes} disabled={loading}>
          {loading ? "Calculating…" : "Yes, check visbreaking options"}
        </button>
        <button className="btn-secondary" onClick={onNo} disabled={loading}>
          No, stop here
        </button>
      </div>
    </div>
  );
}
