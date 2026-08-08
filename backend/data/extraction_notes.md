# Extraction Notes — SABIC PP Compound Datasheets

Source: `Technical data sheets/` (19 PDF files found, 18 unique grades — see "Duplicate file" note below).
Output: `backend/data/datasheets.json`

## Duplicate source file

`SABIC-EE-MF11-talc10-31T1010.pdf` and `SABIC-Transport-MF11-talc10-31T1010.pdf` are byte-identical
(verified via MD5 checksum: `83C9A3B06C0BF050E1D98A94CE67E2B7` for both, same file size 108,638 bytes).
Only **one** grade entry (`31T1010`, `source_pdf` set to the `SABIC-EE-...` filename) was created in
the JSON. This is why 19 PDFs in the folder map to 18 grades in the output, matching your stated count.

## Family / filler_type classifications I was not fully certain about

These grades' datasheets do not explicitly state "homopolymer" or "copolymer" in the description text,
so the `family` value was inferred by analogy to sibling grades in the same product series. Recommend
spot-checking against SABIC's internal product classification if precision matters downstream:

- **H1200** — description says "high impact... non mineral filled Polypropylene compound" but never
  says "copolymer" outright. Classified as `copolymer` based on the filename cue ("PP copol") and your
  hand-read reference. Could arguably be `impact_copolymer` given the "high impact" language.
- **H1090** — description says "Polypropylene reinforced with 30% short glass fibers," omitting
  "homopolymer" (unlike sibling grades H1015/H1020/H1025 which explicitly say "homopolymer with X%
  glass fiber"). Classified as `homopolymer` by analogy to the H10xx series.
- **3237U** — description says "mineral filled modified polypropylene," no base-resin type stated.
  Classified as `impact_copolymer` based on the "impact modified... balance between stiffness and
  impact resistance" language, but this is an inference, not a stated fact.
- **STAMAX 30YH611** — description says "Polypropylene reinforced with 30% long glass fiber," omitting
  "copolymer" (unlike sibling STAMAX grades 30YH530/30YH570/20YH510, which all explicitly say
  "copolymer"). Classified as `copolymer` by analogy.
- **1200 (Transport, grade_id `1200T`)** — description says only "mineral filled polypropylene... high
  flow with high stiffness." No base-resin type stated at all. Classified as `copolymer` with the
  **lowest confidence of any grade in this dataset** — this is a guess, not a textual inference like the
  others above. Please verify against SABIC's official grade classification before relying on it.

`filler_type` for **3237U** and **1200T**: neither datasheet's body text says "talc" explicitly (3237U
says generically "mineral filled"; 1200T's PDF doesn't name the mineral at all). Both were set to
`talc` based on your original filenames (`...talc20-3237U.pdf`, `...talc10-1200.pdf`), which I've
treated as reliable pre-classification.

## New canonical keys added (not in your original list)

Your instructions said to add a new key only if nothing else fits — these four cases were genuinely
new property types not covered by the given key list:

1. **`flexural_strength`** (class `strength`) — STAMAX 20YH510, 30YH570, 30YH611 report a "Flexural
   strength" row at both 23°C and 80°C in addition to flexural modulus. This didn't exist on the
   30YH530 sheet you hand-read, so it wasn't in the original pattern. Mapped to class `strength` since
   it's conceptually parallel to tensile_strength.
2. **`vicat_softening_temp_a`** / **`vicat_softening_temp_b`** (class `thermal`) — 108MF97 and 108MF10
   (automotive bumper grades) report Vicat Softening Temperature (VST/A @10N, VST/B @50N, ASTM
   D1525/ISO 306) instead of Heat Deflection Temperature. Vicat and HDT are different physical tests
   (different loading/geometry), so I did **not** fold these into `hdt_a`/`hdt_b` — that would have
   misrepresented the data for blend math.
3. **`vicat_softening_temp`** (class `thermal`, single value, no A/B split) — 310MK10 and 310MK10R
   report one Vicat Softening Point (151°C, ASTM D1525) without an A/B load distinction.
4. **`tensile_strain_yield`** (class `strain`) — 108MF97 and 108MF10 report "strain at yield" (8%)
   rather than "strain at break" (these super-high-impact bumper grades don't report a break point in
   the standard tensile test).

## Properties intentionally not extracted (out of scope / not needed for blend math)

- Formulation flags (UV stabilized, anti-static agent, nucleating agent: yes/no) — not numeric
  properties.
- Rockwell Hardness R-scale (310MK10, 310MK10R: 90, ASTM D785) and Shore D Hardness (108MF10: 52,
  ISO 868) — no canonical key fits and hardness isn't part of the blend-prediction property set per
  your instructions.
- All flammability detail beyond Comparative Tracking Index and UL94 lowest-thickness-for-V0 (GWFI,
  GWIT, UL Yellow Card link, 5VA ratings) — explicitly out of scope per your instructions.
- Processing conditions / storage & handling / disclaimer text — explicitly out of scope.

## Numeric values worth double-checking

- **3237U** — the HDT/A row in the source PDF is garbled/incomplete: it prints as `at 1.8   60   °C
  ISO 75` without the usual `MPa (HDT/A)` label (visible in both the table and the raw PDF text
  layer). I interpreted this as HDT/A = 60°C (consistent with HDT/A < HDT/B, 60 < 110), but recommend
  confirming against SABIC's published sheet or IMDS record.
- **STAMAX 20YH510** — CLTE is printed as `=54` µm/mK and one GWFI value as `=960` in the source PDF.
  This is almost certainly a rendering artifact of a "≤" (less-than-or-equal) symbol that didn't survive
  PDF text extraction. I recorded the numeric value as 54, but flag that it may represent a ceiling/max
  spec rather than a typical value — worth confirming.
- **31T1010** — "stress at yield" and CLTE are both shown as a bare dash `-` in the source table
  (distinct from the literal string "No Yield" used on other H-series sheets). Treated as
  not-reported/null in both cases.
- **H1090** — reports "stress at yield" (95 MPa) and "strain at break" (2.6%) but has no "stress at
  break" row at all — an inconsistent/incomplete property set in the source sheet, not an extraction
  error on my part. Recorded exactly as given; worth checking with SABIC whether a stress-at-break
  value was simply dropped from this particular datasheet revision.
- **310MK10 vs 310MK10R** — every mechanical/thermal value (tensile yield/break, flexural modulus,
  Izod, Vicat, HDT) is identical between the two grades, even though 310MK10R's datasheet omits the
  Density row entirely (310MK10 lists 905 kg/m³; 310MK10R has none). This may be intentional (310MK10R
  is likely a regrind/recycled-content variant sharing the same typical mechanical spec) but is worth
  confirming isn't a copy-paste artifact in SABIC's sheet.
- **310MK10 / 310MK10R `hdt_b` mapping** — the source reports "Heat Deflection Temperature at 455 kPa"
  per ASTM D648, which I mapped to `hdt_b` (nominally the 0.45 MPa / ISO 75 condition) since 455 kPa ≈
  0.455 MPa is the closest match. This is an ASTM/ISO cross-method approximation, not a strict
  equivalence — flagged in the JSON's `condition.note` field for that property.
- **MFR unit normalization** — 108MF97, 108MF10, 310MK10, and 310MK10R report MFR in "g/10min" (ASTM
  D1238) rather than "dg/min" (ISO 1133). These are numerically identical units (1 g/10min = 1 dg/min),
  so values were carried over unchanged with the unit re-labeled `dg/min` for schema consistency across
  the dataset — no value was altered, only the label.

## Verification of your 3 hand-read reference grades

All three were re-derived independently from the source PDFs and matched your hand-read values exactly,
with no discrepancies:

- **H1015**: homopolymer, 15% short GF, MFR 15, density 1100, tensile modulus 4700, flexural modulus
  4500, Izod 6.3/6/3.5 @23/0/-20°C, HDT/A 140, HDT/B 155, CLTE 64, shrinkage 0.8% — confirmed. (Also
  found additional values not in your summary: stress at break 64 MPa, strain at break 3%, stress at
  yield reported as "No Yield".)
- **H1200**: copolymer, unfilled, MFR 13, density 990, tensile modulus 980, stress at yield 15, stress
  at break 11, strain at break 19%, flexural modulus 1000, Izod 13/5/4 @23/0/-20°C, HDT/A 48, HDT/B 85,
  CLTE 130, shrinkage 1.2% — confirmed exactly, no discrepancies.
- **STAMAX 30YH530**: copolymer, 30% LGF, no MFR, density 1224, tensile modulus 7400/4500 @23/80°C,
  tensile strength 80/40 @23/80°C, flexural modulus 6600/4400 @23/80°C, Charpy notched 16/15 @23/-30°C,
  unnotched 43/48 @23/-30°C, HDT/A 155, no CLTE/shrinkage reported — confirmed exactly.

## Grades with an incomplete property set relative to the H10xx "template"

For transparency — these grades are missing one or more properties that most of their peers report,
confirmed as genuinely absent from the source PDF (not an extraction miss):

- **G3230A**: no `tensile_modulus` row at all (only stress/strain at break); no HDT/B; no CTI/UL94
  section present in the sheet.
- **H1020**: no HDT/B reported (only HDT/A).
- **H1090**: no mould shrinkage, no Izod/Charpy impact data, no HDT/B at all.
- **19T1020U, 3237U**: no CTI/UL94 lowest-thickness value (sheets only report a GWFI value, which is
  out of scope per your instructions).
- **310MK10R**: no density reported.
- **1200T**: no CTI/UL94/flammability section present in the sheet at all.
