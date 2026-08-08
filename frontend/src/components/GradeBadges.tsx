const FILLER_LABELS: Record<string, string> = {
  none: "unfilled",
  glass_fiber_short: "short glass fiber",
  glass_fiber_long: "long glass fiber",
  talc: "talc filled",
};

export function GradeBadges({
  family,
  fillerType,
  fillerContentPct,
}: {
  family: string;
  fillerType: string;
  fillerContentPct: number | null;
}) {
  return (
    <span className="grade-badges">
      <span className="badge badge-family">{family.replace("_", " ")}</span>
      <span className="badge badge-filler">
        {FILLER_LABELS[fillerType] ?? fillerType}
        {fillerContentPct ? ` ${fillerContentPct}%` : ""}
      </span>
    </span>
  );
}
