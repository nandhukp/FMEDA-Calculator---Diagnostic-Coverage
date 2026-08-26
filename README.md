# FMEDA Calculator — ISO 26262 Hardware Architectural Metrics

**Author:** Nandakumar Palani
**Standards:** ISO 26262-5 (Tables 3, 4, 5, 6, Annex C) · SN 29500 · IEC TR 62380
**Python:** ≥ 3.9 · No external runtime dependencies

[![Formula Verification](https://github.com/nandhukp/FMEDA-Calculator---Diagnostic-Coverage/actions/workflows/formula-check.yml/badge.svg)](https://github.com/nandhukp/FMEDA-Calculator---Diagnostic-Coverage/actions/workflows/formula-check.yml)

An FMEDA (Failure Mode Effects and Diagnostic Analysis) quantifies how well
a hardware design is protected against random faults. This tool computes the
three ISO 26262 hardware architectural metrics — **SPFM**, **LFM**, **PMHF** —
with three capabilities that spreadsheets cannot provide:

1. **Evidence tracking** — every DC value carries a test-evidence record
   (test case ID, validated DC, date, notes). The tool distinguishes
   *estimated* DC (from specification) from *validated* DC (from fault
   injection test).

2. **Validation debt** — metrics are computed in two modes: *planning*
   (estimated DC) and *validated* (confirmed test evidence only).
   The gap between the two is the **validation debt** — safety improvement
   claimed but not yet proved by test. Debt must reach zero before safety
   case closure (ISO 26262-5 Annex C requirement).

3. **Verified formula correctness** — the green badge above is not decoration.
   Every push and pull request to this repo automatically re-runs
   `tools/verify_formulas.py`, a deterministic regression test that checks
   SPFM/LFM/PMHF output against a known-correct reference case. See
   [*Trusting this repo's correctness*](#trusting-this-repos-correctness)
   below for how to verify it yourself in under a second, with no API key
   required.

---

## Repository structure

```
fmeda-calculator/
├── fmeda/
│   ├── __init__.py
│   └── calculator.py          ← engine: FMEDA, FailureMode, Evidence, report()
├── ui/
│   └── fmeda_ai_calculator.jsx  ← React interactive UI with Claude AI agent
├── examples/
│   ├── adas_platform.py       ← Safety MCU (ASIL D) + Compute SoC (ASIL B)
│   │                             + Companion SBC + GMSL camera pipeline
│   └── safety_mcu.py          ← minimal safety MCU example
├── tests/
│   └── test_calculator.py     ← unit tests (pytest)
├── tools/
│   ├── verify_formulas.py     ← deterministic formula regression check (CI + local)
│   └── ai_formula_audit.py    ← on-demand AI narrative code review (needs API key)
├── .github/workflows/
│   ├── formula-check.yml      ← runs verify_formulas.py + tests on every push/PR
│   └── ai-audit.yml           ← runs ai_formula_audit.py on release / manual trigger
├── requirements.txt
└── README.md
```

---

## Quick start

```bash
git clone https://github.com/nandhukp/FMEDA-Calculator---Diagnostic-Coverage.git
cd FMEDA-Calculator---Diagnostic-Coverage

# Run the ADAS platform example
PYTHONPATH=. python3 examples/adas_platform.py

# Run tests (requires pytest)
pip install pytest
PYTHONPATH=. python3 -m pytest tests/ -v
```

---

## Inputs — what to provide per failure mode

| Field | Type | Description | Source document |
|---|---|---|---|
| `name` | str | Failure mode description | Datasheet FMEA / HAZOP |
| `component` | str | Hardware element (e.g. "Safety MCU", "Compute SoC") | System decomposition |
| `lambda_fit` | float | Failure rate in FIT (1 FIT = 1 failure per 10⁹ hr) | SN 29500 / IEC TR 62380 / manufacturer MTBF |
| `dc` | float 0–1 | Estimated diagnostic coverage | Safety mechanism spec / supplier Safety Manual |
| `is_safety_related` | bool | False = safe fault; excluded from all denominators | HAZOP safety goal analysis |
| `is_latent` | bool | True = multi-point latent fault; feeds LFM not SPFM | ISO 26262-5 §8.4 fault classification |
| `safety_mechanism` | str | Description of the SM providing the DC | SWRS / HW design spec |
| `lambda_source` | str | Traceability to failure rate database | SN 29500 table, IEC TR 62380 section |
| `evidence` | Evidence | Test result linking DC to fault injection test | Fault injection test report |

### Evidence record fields

| Field | Type | Description |
|---|---|---|
| `test_id` | str | Test case identifier (e.g. `TC-SOC-01`) |
| `status` | EvidenceStatus | `ESTIMATED` / `IN_REVIEW` / `VALIDATED` |
| `validated_dc` | float | DC confirmed by test (may differ from design estimate) |
| `test_date` | date | Date the test was executed |
| `notes` | str | Detection latency, pass/fail detail, DTC raised |

---

## Outputs

### Console report (`report(fmeda, asil="D")`)

```
====================================================================
  FMEDA Report : ADAS Safety Channel
  ASIL Target  : D
====================================================================

  Failure Rate Summary
  λ Total (safety-related)              290.00 FIT
  λ Safe (excluded from numerator)       64.00 FIT
  λ Dangerous (total)                   226.00 FIT
  λ_SPF + λ_RF undetected (plan)          4.450 FIT
  λ_SPF + λ_RF undetected (valid)        41.270 FIT   ← validation debt visible

  Metrics               Planning    Validated   Target      Result
  SPFM                   98.47%      85.77%     ≥99%       ❌ FAIL
  LFM                    99.12%      91.44%     ≥90%       ✅ PASS
  PMHF                    4.450 FIT   41.270 FIT ≤10 FIT   ❌ FAIL (validated)

  Validation Debt
  Unvalidated modes              : 6
  SPFM debt (plan − validated)   : +0.1270    ← close this before sign-off

  Validation Backlog (ranked by uncovered FIT risk)
  #1  IMU slow drift           1.000 FIT uncov   DC=80%   estimated
  #2  Thermal shutdown         0.900 FIT uncov   DC=95%   in_review
  ...

  Top-5 Worst Contributors
  #1  IMU slow drift           1.000 FIT         DC=80%   Latent
  ...
```

### File exports

```python
fmeda.to_csv("output.csv")    # spreadsheet-compatible row export
fmeda.to_json()               # full serialisation including evidence records
FMEDA.from_json(json_str)     # reload from JSON (round-trip safe)
```

---

## ISO 26262-5 targets

(Combined Table 5 / Table 6 — SPFM/LFM/PMHF targets per ASIL)

| ASIL | SPFM | LFM | PMHF |
|------|------|-----|------|
| A | — | — | — |
| B | > 90% | > 60% | < 100 FIT |
| C | > 97% | > 80% | < 100 FIT |
| D | > 99% | > 90% | < 10 FIT |

**Formulas used by this tool** (matching the source worksheet exactly):

```
SPFM = (1 − (Σλ_SPF + Σλ_RF) / Σλ) × 100
LFM  = (1 − Σλ_MPF,L / (Σλ − Σλ_SPF − Σλ_RF)) × 100
PMHF = Σλ_SPF + Σλ_RF                                   (simplified, default)
PMHF = Σλ_SPF + Σλ_RF + Σλ_MPF,det × Σλ_MPF,latent × T_lifetime   (full, optional)
```

Where λ_SPF is the failure rate of modes with **no** safety mechanism at all
(DC = 0%), and λ_RF is the *uncovered* portion of modes that **do** have a
mechanism but incomplete coverage (0% < DC < 100%). The dual-point-fault
product term in the full PMHF formula is conventionally omitted (it's
numerically negligible — two already-tiny FIT-scale rates multiplied
together) unless explicitly requested via `pmhf(full=True, t_lifetime_hours=...)`.

**Important denominator convention:** Σλ (the denominator in both SPFM and
LFM) is the **total base failure rate, including safe/non-safety-related
faults** — not a safety-related-only subtotal. This was verified by
reconstructing the source worksheet's numbers: its stated λ (1020.427 FIT)
only reproduces exactly when safe faults are included in the sum. This is
a specific convention from the worksheet this tool matches — other ISO
26262 FMEDA implementations sometimes use a safety-related-only
denominator instead, so double-check this assumption fits your own safety
case's methodology before citing these numbers to an auditor.

---

## Trusting this repo's correctness

Formula bugs in a safety tool are exactly the kind of error that's
invisible until an auditor — or a real vehicle — finds it. Rather than
asking you to trust written claims, this repo backs correctness with three
layers, each doing a different job:

| Layer | What it checks | Cost | Runs |
|---|---|---|---|
| [`tools/verify_formulas.py`](tools/verify_formulas.py) | SPFM/LFM/PMHF output vs. a known-correct reference case, bit-for-bit | Free, instant | Every push/PR (CI badge above) — and you can run it yourself locally |
| [`tests/test_calculator.py`](tests/test_calculator.py) | Unit-level formula behaviour, evidence tracking, edge cases | Free, instant | Every push/PR |
| [`tools/ai_formula_audit.py`](tools/ai_formula_audit.py) | Narrative review: does the code's logic actually match its docstring's claimed formula? Are edge cases handled sensibly? Is terminology consistent? | Costs API tokens | On each GitHub Release, or manually via Actions tab |

**Verify it yourself in one command — no trust required, no API key needed:**

```bash
git clone https://github.com/nandhukp/FMEDA-Calculator---Diagnostic-Coverage.git
cd FMEDA-Calculator---Diagnostic-Coverage
PYTHONPATH=. python3 tools/verify_formulas.py
```

You'll see a line-by-line comparison of every formula's output against the
reference case, with the exact numeric delta for each check. Exit code 0
means every formula matches; exit code 1 means something's wrong — and the
output tells you exactly which formula and by how much.

**Why isn't this automatic on every download?** GitHub has no hook that
fires when someone clones a repo or downloads a zip — it's a static file
transfer, not a service call. The closest practical equivalent is what's
here: a CI badge that's re-verified on every code change (so what you see
on the repo page reflects the current `main` branch, not a stale claim),
plus a one-line command anyone can run themselves the moment they download
it, plus a periodic deeper AI review tied to releases rather than to
individual downloads (since that would mean every visitor's page-load
silently costs someone API money).

### Running the AI audit yourself

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install anthropic
PYTHONPATH=. python3 tools/ai_formula_audit.py
```

This produces a dated Markdown report in `audit_reports/` reviewing the
calculator's formula logic against ISO 26262-5 definitions, edge-case
handling, and terminology consistency — a second opinion from a different
angle than the deterministic numeric check above.

---

## Three problems this solves vs a spreadsheet

| Spreadsheet failure mode | How this tool eliminates it |
|---|---|
| **Formula drift** — SUM ranges silently exclude new rows after insert/sort | Engine iterates the data structure by identity; no cell references to drift |
| **No worst-contributor visibility** — engineer must manually sort to find highest-impact gaps | `worst_contributors()` auto-ranks by uncovered FIT on every call |
| **DC estimated never replaced by validated** — both look identical in a spreadsheet | `Evidence` record per mode; `spfm(validated_only=True)` exposes the gap; validation debt is a first-class number |

---

## Interactive UI (React + Claude AI Agent)

`ui/fmeda_ai_calculator.jsx` is a React artifact that runs in the
[Claude.ai](https://claude.ai) environment and provides:

- Live SPFM / LFM / PMHF gauges with animated target markers
- Worst-contributor bar chart (auto-sorted)
- Four AI agent modes powered by the Claude API:
  - **Gap Analysis** — quantitative coverage gap with improvement recommendations
  - **Suggest Modes** — 3 missing failure modes auto-suggested with λ/DC pre-filled
  - **Gen FTA** — fault tree top-event → gate structure → cut sets → P(TOP)
  - **Safety Case** — GSN claim → strategy → sub-claims → evidence requirements

---

## ADAS platform example

`examples/adas_platform.py` implements a representative dual-channel safety
architecture using generic component names:

- **Compute SoC (ASIL B):** SOC_ERROR supervision, FSI heartbeat, ECC,
  thermal alert, voltage monitoring, PLL fault detection
- **Safety MCU (ASIL D):** hardware lockstep, dual watchdog (internal SMU +
  external companion SBC), SPI E2E monitoring
- **Companion SBC (ASIL D):** external window watchdog, voltage supervisor
  with independent FAULT pin, startup self-test
- **GMSL camera deserializer:** lock-loss detection, pixel data CRC, GP
  fault signal loopback test
- **Camera power supervisor:** FAULT pin supervision, over-current detection
- **PCIe C2C inter-SoC link:** E2E CRC32 + sequence counter (64-case fault
  injection matrix)

Each failure mode carries an Evidence record referencing the corresponding
fault injection test case (TC-SOC-01, TC-CAM-06, TC-PCIE-01, etc.).
Failure rates are representative SN 29500 / IEC TR 62380 values for the
relevant component category — not tied to any specific vendor or product.

---

## License

MIT
