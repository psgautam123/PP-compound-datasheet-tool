export type StepStatus = "pending" | "active" | "success" | "no_match" | "skipped";

export interface StepInfo {
  label: string;
  status: StepStatus;
}

const ICONS: Record<StepStatus, string> = {
  pending: "○",
  active: "◐",
  success: "✓",
  no_match: "–",
  skipped: "·",
};

// Nielsen heuristic #1, visibility of system status: makes explicit which
// of the three workflow steps (exact match / blend / visbreaking) the
// system is currently on, rather than a bare spinner.
export function StepIndicator({ steps }: { steps: StepInfo[] }) {
  return (
    <ol className="step-indicator" aria-label="Search progress">
      {steps.map((step, i) => (
        <li key={step.label} className={`step step-${step.status}`}>
          <span className="step-icon" aria-hidden="true">
            {ICONS[step.status]}
          </span>
          <span className="step-label">{step.label}</span>
          {i < steps.length - 1 && <span className="step-connector" aria-hidden="true" />}
        </li>
      ))}
    </ol>
  );
}
