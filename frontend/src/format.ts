import { PROPERTY_META } from "./propertyMeta";

const metaByKey = new Map(PROPERTY_META.map((p) => [p.key, p]));

export function propertyLabel(key: string): string {
  return metaByKey.get(key)?.label ?? key;
}

export function propertyUnit(key: string): string {
  return metaByKey.get(key)?.unit ?? "";
}

export function formatNumber(n: number): string {
  if (Number.isInteger(n)) return n.toString();
  const abs = Math.abs(n);
  const decimals = abs >= 100 ? 1 : abs >= 1 ? 2 : 4;
  return n.toFixed(decimals);
}

export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

export function methodLabel(method: string): string {
  const labels: Record<string, string> = {
    log_additive: "log-additivity",
    linear_rom: "rule of mixtures",
    halpin_tsai: "Halpin-Tsai",
    exponential_decay: "exponential decay",
    hdt_power_law_calibrated: "HDT power law",
  };
  return labels[method] ?? method;
}
