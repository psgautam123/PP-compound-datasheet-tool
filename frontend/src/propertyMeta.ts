// Canonical property keys the backend understands (must match
// backend/engine/property_taxonomy.py). Grouped into "common" (shown by
// default) and the rest (behind an "Advanced properties" disclosure) --
// Nielsen heuristic #8, minimalist design / progressive disclosure.

export interface PropertyMeta {
  key: string;
  label: string;
  unit: string;
  testMethod: string;
  common: boolean;
  helpText: string;
}

export const PROPERTY_META: PropertyMeta[] = [
  {
    key: "mfr",
    label: "Melt Flow Rate (MFR)",
    unit: "dg/min",
    testMethod: "ISO 1133, 230°C / 2.16 kg",
    common: true,
    helpText: "How easily the melted resin flows. Higher MFR = thinner, faster-flowing melt.",
  },
  {
    key: "tensile_modulus",
    label: "Tensile Modulus",
    unit: "MPa",
    testMethod: "ISO 527/1A",
    common: true,
    helpText: "Stiffness under tension — resistance to stretching.",
  },
  {
    key: "flexural_modulus",
    label: "Flexural Modulus",
    unit: "MPa",
    testMethod: "ISO 178",
    common: true,
    helpText: "Stiffness under bending.",
  },
  {
    key: "hdt_a",
    label: "Heat Deflection Temp (HDT/A)",
    unit: "°C",
    testMethod: "ISO 75, 1.8 MPa",
    common: true,
    helpText: "Temperature at which the part starts to sag under a standard load.",
  },
  {
    key: "izod_notched",
    label: "Izod Impact, Notched",
    unit: "kJ/m²",
    testMethod: "ISO 180/1A, 23°C",
    common: true,
    helpText: "Impact resistance from a notched-bar swing test. Higher = tougher.",
  },
  {
    key: "charpy_notched",
    label: "Charpy Impact, Notched",
    unit: "kJ/m²",
    testMethod: "ISO 179/1eA, 23°C",
    common: true,
    helpText: "Impact resistance (Charpy method) — some grades report this instead of Izod.",
  },
  {
    key: "tensile_stress_yield",
    label: "Tensile Stress at Yield",
    unit: "MPa",
    testMethod: "ISO 527/1A",
    common: false,
    helpText: "Stress at the onset of permanent (plastic) deformation.",
  },
  {
    key: "tensile_stress_break",
    label: "Tensile Stress at Break",
    unit: "MPa",
    testMethod: "ISO 527/1A",
    common: false,
    helpText: "Stress at which the specimen fractures in a tensile test.",
  },
  {
    key: "tensile_strength",
    label: "Tensile Strength",
    unit: "MPa",
    testMethod: "ISO 527/1A",
    common: false,
    helpText: "Peak tensile stress the material can sustain (reported directly on some grades).",
  },
  {
    key: "tensile_strain_break",
    label: "Tensile Strain at Break",
    unit: "%",
    testMethod: "ISO 527/1A",
    common: false,
    helpText: "Elongation at fracture — a ductility measure.",
  },
  {
    key: "charpy_unnotched",
    label: "Charpy Impact, Unnotched",
    unit: "kJ/m²",
    testMethod: "ISO 179/1eU, 23°C",
    common: false,
    helpText: "Impact resistance without a stress-concentrating notch.",
  },
  {
    key: "hdt_b",
    label: "Heat Deflection Temp (HDT/B)",
    unit: "°C",
    testMethod: "ISO 75, 0.45 MPa",
    common: false,
    helpText: "HDT under a lighter load than HDT/A — typically a higher temperature.",
  },
  {
    key: "clte",
    label: "Coeff. of Linear Thermal Expansion",
    unit: "µm/mK",
    testMethod: "ISO 11359-2, -30 to 100°C",
    common: false,
    helpText: "How much the part's dimensions change per degree of temperature change.",
  },
];

export const GLOSSARY: Record<string, string> = {
  "rule of mixtures":
    "A blend-property estimate that weights each grade's value by its volume fraction in the blend — the simplest way to predict a two-grade blend's properties.",
  "log-additivity":
    "For melt flow, blend behavior follows a logarithmic (not linear) weighting of the two grades' MFR values — melt viscosity blends this way, not flow rate directly.",
  "Halpin-Tsai":
    "A composite-mechanics equation used to predict modulus from fiber content when the simple rule of mixtures isn't accurate enough.",
  "DCP":
    "Dicumyl peroxide — a common reactive-extrusion additive that lowers PP's molecular weight, raising its melt flow (\"visbreaking\").",
  "visbreaking":
    "Deliberately degrading a polymer's molecular weight (usually with peroxide) to raise its melt flow rate.",
};
