import { PROPERTY_META } from "../propertyMeta";
import { Tooltip } from "./Tooltip";

export interface PropertyEntry {
  enabled: boolean;
  value: string;
}

export type PropertyEntries = Record<string, PropertyEntry>;

export function initialEntries(): PropertyEntries {
  const entries: PropertyEntries = {};
  for (const p of PROPERTY_META) entries[p.key] = { enabled: false, value: "" };
  return entries;
}

interface Props {
  entries: PropertyEntries;
  onToggle: (key: string, enabled: boolean) => void;
  onValueChange: (key: string, value: string) => void;
  onSubmit: () => void;
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
  loading: boolean;
  validationError: string | null;
}

export function PropertyForm({
  entries,
  onToggle,
  onValueChange,
  onSubmit,
  showAdvanced,
  onToggleAdvanced,
  loading,
  validationError,
}: Props) {
  const common = PROPERTY_META.filter((p) => p.common);
  const advanced = PROPERTY_META.filter((p) => !p.common);

  const row = (p: (typeof PROPERTY_META)[number]) => {
    const entry = entries[p.key];
    const inputId = `prop-${p.key}`;
    return (
      <div className={`property-row${entry.enabled ? " property-row-active" : ""}`} key={p.key}>
        <label className="property-checkbox">
          <input
            type="checkbox"
            checked={entry.enabled}
            onChange={(e) => onToggle(p.key, e.target.checked)}
          />
        </label>
        <label htmlFor={inputId} className="property-label">
          {p.label}
          <Tooltip text={`${p.helpText} Test method: ${p.testMethod}.`}>
            <span className="help-icon" aria-label={`About ${p.label}`}>
              ?
            </span>
          </Tooltip>
        </label>
        <input
          id={inputId}
          type="number"
          inputMode="decimal"
          className="property-input"
          placeholder="target value"
          value={entry.value}
          disabled={!entry.enabled}
          onChange={(e) => onValueChange(p.key, e.target.value)}
        />
        <span className="property-unit">{p.unit}</span>
      </div>
    );
  };

  return (
    <form
      className="property-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div className="property-list">{common.map(row)}</div>

      <details className="advanced-disclosure" open={showAdvanced} onToggle={(e) => {
        const isOpen = (e.target as HTMLDetailsElement).open;
        if (isOpen !== showAdvanced) onToggleAdvanced();
      }}>
        <summary>Advanced properties</summary>
        <div className="property-list">{advanced.map(row)}</div>
      </details>

      {validationError && (
        <p className="form-error" role="alert">
          {validationError}
        </p>
      )}

      <button type="submit" className="btn-primary" disabled={loading}>
        {loading ? "Searching…" : "Find matching grade"}
      </button>
    </form>
  );
}
