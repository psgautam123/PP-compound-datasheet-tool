import { datasheetUrl } from "../api";
import type { GradeMatchOut } from "../types";
import { GradeBadges } from "./GradeBadges";
import { PropertyTable } from "./PropertyTable";

// Step 1 result: an exact (within-tolerance) existing grade was found --
// Workflow2.txt §6, "output the grade and the technical datasheet."
export function SearchResults({ matches }: { matches: GradeMatchOut[] }) {
  return (
    <div className="result-panel result-success">
      <h2>Matching grade{matches.length > 1 ? "s" : ""} found</h2>
      <p className="result-subtitle">
        {matches.length} existing product{matches.length > 1 ? "s" : ""} meet{matches.length === 1 ? "s" : ""} every
        specified property within 5%.
      </p>
      {matches.map((m) => (
        <div className="grade-card" key={m.grade.grade_id}>
          <div className="grade-card-header">
            <div>
              <h3>{m.grade.product_name}</h3>
              <GradeBadges
                family={m.grade.family}
                fillerType={m.grade.filler_type}
                fillerContentPct={m.grade.filler_content_pct}
              />
            </div>
            <a className="btn-secondary" href={datasheetUrl(m.grade.grade_id)} target="_blank" rel="noreferrer">
              View datasheet ↗
            </a>
          </div>
          <PropertyTable
            rows={m.matches.map((pm) => ({
              key: pm.key,
              target: pm.target,
              actual: pm.actual,
              relativeError: pm.relative_error,
              withinMargin: pm.within_margin,
            }))}
          />
        </div>
      ))}
    </div>
  );
}
