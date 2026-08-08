import { useState } from "react";
import "./App.css";
import { ApiError, predictBlend, proposeVisbreaking, searchGrades } from "./api";
import { BlendResultView } from "./components/BlendResultView";
import { initialEntries, PropertyForm, type PropertyEntries } from "./components/PropertyForm";
import { SearchResults } from "./components/SearchResults";
import { StepIndicator, type StepInfo, type StepStatus } from "./components/StepIndicator";
import { VisbreakingPrompt } from "./components/VisbreakingPrompt";
import { VisbreakingResultView } from "./components/VisbreakingResultView";
import type { BlendResultOut, GradeMatchOut, TargetProperties, VisbreakingResultOut } from "./types";

type Phase =
  | { kind: "form" }
  | { kind: "loading"; step: 1 | 2 | 3 }
  | { kind: "search-results"; matches: GradeMatchOut[] }
  | { kind: "blend-result"; result: BlendResultOut }
  | { kind: "visbreaking-prompt"; promptText: string }
  | { kind: "visbreaking-result"; result: VisbreakingResultOut }
  | { kind: "visbreaking-no-solution" }
  | { kind: "stopped" }
  | { kind: "error"; message: string };

function computeSteps(phase: Phase): StepInfo[] {
  let s1: StepStatus = "pending";
  let s2: StepStatus = "pending";
  let s3: StepStatus = "pending";

  switch (phase.kind) {
    case "form":
      break;
    case "loading":
      if (phase.step === 1) s1 = "active";
      if (phase.step === 2) {
        s1 = "no_match";
        s2 = "active";
      }
      if (phase.step === 3) {
        s1 = "no_match";
        s2 = "no_match";
        s3 = "active";
      }
      break;
    case "search-results":
      s1 = "success";
      s2 = "skipped";
      s3 = "skipped";
      break;
    case "blend-result":
      s1 = "no_match";
      s2 = "success";
      s3 = "skipped";
      break;
    case "visbreaking-prompt":
      s1 = "no_match";
      s2 = "no_match";
      break;
    case "visbreaking-result":
      s1 = "no_match";
      s2 = "no_match";
      s3 = "success";
      break;
    case "visbreaking-no-solution":
    case "stopped":
      s1 = "no_match";
      s2 = "no_match";
      s3 = "no_match";
      break;
    case "error":
      break;
  }

  return [
    { label: "Exact grade match", status: s1 },
    { label: "Blend prediction", status: s2 },
    { label: "Visbreaking option", status: s3 },
  ];
}

function buildTargetProperties(entries: PropertyEntries): { target: TargetProperties; error: string | null } {
  const target: TargetProperties = {};
  let anyEnabled = false;
  for (const [key, entry] of Object.entries(entries)) {
    if (!entry.enabled) continue;
    anyEnabled = true;
    const n = Number(entry.value);
    if (entry.value.trim() === "" || !Number.isFinite(n) || n <= 0) {
      return { target: {}, error: "Enter a positive number for every property you've selected." };
    }
    target[key] = n;
  }
  if (!anyEnabled) return { target: {}, error: "Select at least one property to search on." };
  return { target, error: null };
}

export default function App() {
  const [entries, setEntries] = useState<PropertyEntries>(initialEntries());
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "form" });
  const [lastTarget, setLastTarget] = useState<TargetProperties>({});
  const [validationError, setValidationError] = useState<string | null>(null);

  const loading = phase.kind === "loading";

  function handleToggle(key: string, enabled: boolean) {
    setEntries((prev) => ({ ...prev, [key]: { ...prev[key], enabled } }));
  }

  function handleValueChange(key: string, value: string) {
    setEntries((prev) => ({ ...prev, [key]: { ...prev[key], value } }));
  }

  async function handleSubmit() {
    const { target, error } = buildTargetProperties(entries);
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError(null);
    setLastTarget(target);
    setPhase({ kind: "loading", step: 1 });

    try {
      const searchRes = await searchGrades(target);
      if (searchRes.matches.length > 0) {
        setPhase({ kind: "search-results", matches: searchRes.matches });
        return;
      }

      setPhase({ kind: "loading", step: 2 });
      const blendRes = await predictBlend(target);
      if (blendRes.solution_found && blendRes.result) {
        setPhase({ kind: "blend-result", result: blendRes.result });
        return;
      }
      setPhase({ kind: "visbreaking-prompt", promptText: blendRes.visbreaking_prompt ?? "" });
    } catch (e) {
      setPhase({ kind: "error", message: e instanceof ApiError ? e.message : "Something went wrong. Please try again." });
    }
  }

  async function handleVisbreakingYes() {
    setPhase({ kind: "loading", step: 3 });
    try {
      const res = await proposeVisbreaking(lastTarget);
      if (res.solution_found && res.result) {
        setPhase({ kind: "visbreaking-result", result: res.result });
      } else {
        setPhase({ kind: "visbreaking-no-solution" });
      }
    } catch (e) {
      setPhase({ kind: "error", message: e instanceof ApiError ? e.message : "Something went wrong. Please try again." });
    }
  }

  function handleReset() {
    setEntries(initialEntries());
    setValidationError(null);
    setPhase({ kind: "form" });
  }

  return (
    <div className="app-shell">
      <header className="app-header review-header">
        <div>
          <h1>PP Compound Grade Finder</h1>
          <p className="app-subtitle">
            Specify the properties you need and we'll find a matching grade, predict a blend, or scope a visbreaking
            trial.
          </p>
        </div>
        <a className="btn-secondary" href="/review">
          Reviewer queue
        </a>
      </header>

      <StepIndicator steps={computeSteps(phase)} />

      <main className="app-main">
        {phase.kind !== "search-results" &&
          phase.kind !== "blend-result" &&
          phase.kind !== "visbreaking-result" && (
            <PropertyForm
              entries={entries}
              onToggle={handleToggle}
              onValueChange={handleValueChange}
              onSubmit={handleSubmit}
              showAdvanced={showAdvanced}
              onToggleAdvanced={() => setShowAdvanced((v) => !v)}
              loading={loading}
              validationError={validationError}
            />
          )}

        {phase.kind === "error" && (
          <div className="result-panel result-error" role="alert">
            <h2>Couldn't complete that search</h2>
            <p>{phase.message}</p>
          </div>
        )}

        {phase.kind === "search-results" && <SearchResults matches={phase.matches} />}
        {phase.kind === "blend-result" && <BlendResultView result={phase.result} />}

        {phase.kind === "loading" && phase.step >= 2 && (
          <div className="result-panel result-loading" aria-live="polite">
            <p>
              {phase.step === 2
                ? "No exact match — checking two-grade blends…"
                : "Calculating a peroxide visbreaking route…"}
            </p>
          </div>
        )}

        {phase.kind === "visbreaking-prompt" && (
          <VisbreakingPrompt
            promptText={phase.promptText}
            onYes={handleVisbreakingYes}
            onNo={() => setPhase({ kind: "stopped" })}
            loading={false}
          />
        )}

        {phase.kind === "visbreaking-result" && <VisbreakingResultView result={phase.result} />}

        {phase.kind === "visbreaking-no-solution" && (
          <div className="result-panel result-error">
            <h2>No visbreaking route found either</h2>
            <p>
              No existing grade has both a lower melt flow and a higher tensile modulus than your target, so there's
              no base grade to visbreak from. Try relaxing your target or specifying fewer properties.
            </p>
          </div>
        )}

        {phase.kind === "stopped" && (
          <div className="result-panel result-neutral">
            <h2>Search stopped</h2>
            <p>No solution was pursued further. Start a new search whenever you're ready.</p>
          </div>
        )}

        {phase.kind !== "form" && (
          <button className="btn-link" onClick={handleReset}>
            ← New search
          </button>
        )}
      </main>
    </div>
  );
}
