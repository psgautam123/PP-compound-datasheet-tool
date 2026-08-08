import { datasheetUrl } from "../api";
import { formatNumber } from "../format";
import type { VisbreakingResultOut } from "../types";
import { GradeBadges } from "./GradeBadges";
import { Tooltip } from "./Tooltip";

const PROCESS_LABELS: Record<string, string> = {
  reactive_extrusion: "reactive extrusion",
  injection_molding: "injection molding",
};

// Step 3 result: predicted peroxide dose + a small factorial DOE for
// physical validation (Workflow2.txt §57). Every number here is a
// starting point, not a guarantee -- flagged in the UI copy per the
// project's truth/accuracy standard.
export function VisbreakingResultView({ result }: { result: VisbreakingResultOut }) {
  return (
    <div className="result-panel result-success">
      <h2>Visbreaking route found</h2>
      <p className="result-subtitle">
        Predicted via peroxide-controlled{" "}
        <Tooltip text="Deliberately degrading a polymer's molecular weight (usually with peroxide) to raise its melt flow rate.">
          <span className="glossary-term">visbreaking</span>
        </Tooltip>{" "}
        of a lower-MFR, higher-modulus base grade — treat this as a starting point for the validation trials below,
        not a guaranteed result.
      </p>

      <div className="grade-card grade-card-compact">
        <div className="grade-card-header">
          <div>
            <h3>Base grade: {result.base_grade.product_name}</h3>
            <GradeBadges
              family={result.base_grade.family}
              fillerType={result.base_grade.filler_type}
              fillerContentPct={result.base_grade.filler_content_pct}
            />
          </div>
          <a className="btn-secondary" href={datasheetUrl(result.base_grade.grade_id)} target="_blank" rel="noreferrer">
            View datasheet ↗
          </a>
        </div>
      </div>

      <div className="visbreaking-stats">
        <div className="stat-tile">
          <span className="stat-label">Target MFR</span>
          <span className="stat-value">{formatNumber(result.target_mfr)} dg/min</span>
        </div>
        <div className="stat-tile">
          <span className="stat-label">Design point (0–10% over target)</span>
          <span className="stat-value">{formatNumber(result.final_mfi_design_point)} dg/min</span>
        </div>
        <div className="stat-tile stat-tile-highlight">
          <span className="stat-label">
            Predicted{" "}
            <Tooltip text="Dicumyl peroxide — a common reactive-extrusion additive that lowers PP's molecular weight, raising its melt flow.">
              <span className="glossary-term">DCP</span>
            </Tooltip>{" "}
            dose
          </span>
          <span className="stat-value">{result.peroxide_dose_wt_pct.toFixed(4)} wt%</span>
        </div>
        <div className="stat-tile">
          <span className="stat-label">Process</span>
          <span className="stat-value">{PROCESS_LABELS[result.process] ?? result.process}</span>
        </div>
        <div className="stat-tile">
          <span className="stat-label">Temperature</span>
          <span className="stat-value">{formatNumber(result.temp_C)} °C</span>
        </div>
        <div className="stat-tile">
          <span className="stat-label">Residence time</span>
          <span className="stat-value">{formatNumber(result.residence_time_min)} min</span>
        </div>
      </div>

      <h3>Validation DOE (±20% around the predicted dose &amp; residence time)</h3>
      <p className="result-subtitle">
        Temperature is held fixed across every run — a ±20% swing in °C is not physically meaningful and could exceed
        this grade's processing ceiling, so only dose and residence time (both true ratio quantities) are varied.
      </p>
      <table className="property-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Peroxide dose (wt%)</th>
            <th>Residence time (min)</th>
            <th>Temperature (°C)</th>
            <th>Predicted MFR (dg/min)</th>
          </tr>
        </thead>
        <tbody>
          {result.doe.map((r, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td>{r.dose_wt_pct.toFixed(4)}</td>
              <td>{formatNumber(r.residence_time_min)}</td>
              <td>{formatNumber(r.temp_C)}</td>
              <td>{formatNumber(r.predicted_mfi)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {result.correlation_source_citation && (
        <p className="citation-footnote">Correlation source: {result.correlation_source_citation}</p>
      )}
    </div>
  );
}
