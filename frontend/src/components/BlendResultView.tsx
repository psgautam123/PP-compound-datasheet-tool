import { datasheetUrl } from "../api";
import { formatNumber } from "../format";
import type { BlendResultOut } from "../types";
import { GradeBadges } from "./GradeBadges";
import { PropertyTable } from "./PropertyTable";
import { Tooltip } from "./Tooltip";

// Step 2 result: no single grade matched, but a two-grade blend does
// (Workflow2.txt §8-20).
export function BlendResultView({ result }: { result: BlendResultOut }) {
  const wtPctB = 100 - result.wt_pct_a;
  return (
    <div className="result-panel result-success">
      <h2>No single grade matches — here's a blend that does</h2>
      <p className="result-subtitle">
        Predicted using a{" "}
        <Tooltip text="A blend-property estimate that weights each grade's value by its volume fraction in the blend.">
          <span className="glossary-term">rule-of-mixtures</span>
        </Tooltip>{" "}
        model; every specified property lands within 5% of your target.
      </p>

      <div className="blend-composition">
        <div className="blend-share" style={{ flexBasis: `${result.wt_pct_a}%` }}>
          <strong>{formatNumber(result.wt_pct_a)}%</strong>
          <span>{result.grade_a.product_name}</span>
        </div>
        <div className="blend-share blend-share-b" style={{ flexBasis: `${wtPctB}%` }}>
          <strong>{formatNumber(wtPctB)}%</strong>
          <span>{result.grade_b.product_name}</span>
        </div>
      </div>

      <div className="blend-grades">
        {[result.grade_a, result.grade_b].map((g) => (
          <div className="grade-card grade-card-compact" key={g.grade_id}>
            <div className="grade-card-header">
              <div>
                <h3>{g.product_name}</h3>
                <GradeBadges family={g.family} fillerType={g.filler_type} fillerContentPct={g.filler_content_pct} />
              </div>
              <a className="btn-secondary" href={datasheetUrl(g.grade_id)} target="_blank" rel="noreferrer">
                View datasheet ↗
              </a>
            </div>
          </div>
        ))}
      </div>

      <h3>Predicted blend properties</h3>
      <PropertyTable
        actualLabel="Predicted"
        rows={result.predictions.map((p) => ({
          key: p.key,
          target: p.target,
          actual: p.predicted,
          relativeError: p.relative_error,
          withinMargin: p.within_margin,
          method: p.method,
        }))}
      />
    </div>
  );
}
