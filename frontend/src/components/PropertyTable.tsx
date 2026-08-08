import { formatNumber, formatPercent, propertyLabel, propertyUnit, methodLabel } from "../format";

export interface PropertyTableRow {
  key: string;
  target: number;
  actual: number;
  relativeError: number;
  withinMargin: boolean;
  method?: string;
}

export function PropertyTable({ rows, actualLabel = "Actual" }: { rows: PropertyTableRow[]; actualLabel?: string }) {
  return (
    <table className="property-table">
      <thead>
        <tr>
          <th>Property</th>
          <th>Target</th>
          <th>{actualLabel}</th>
          <th>Error</th>
          {rows.some((r) => r.method) && <th>Method</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} className={r.withinMargin ? "" : "row-out-of-margin"}>
            <td>{propertyLabel(r.key)}</td>
            <td>
              {formatNumber(r.target)} <span className="unit">{propertyUnit(r.key)}</span>
            </td>
            <td>
              {formatNumber(r.actual)} <span className="unit">{propertyUnit(r.key)}</span>
            </td>
            <td className={r.withinMargin ? "error-ok" : "error-bad"}>
              {formatPercent(r.relativeError)}
              {!r.withinMargin && " ⚠"}
            </td>
            {r.method && <td className="method-cell">{methodLabel(r.method)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
