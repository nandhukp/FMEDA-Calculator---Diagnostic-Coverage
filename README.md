# FMEDA Calculator — ISO 26262 Hardware Architectural Metrics

**Author:** Nandakumar Palani  
**Standards:** ISO 26262-5 (Tables 3, 4, Annex C) · SN 29500 · IEC TR 62380  
**Python:** ≥ 3.9 · No external runtime dependencies

An FMEDA (Failure Mode Effects and Diagnostic Analysis) quantifies how well
a hardware design is protected against random faults. This tool computes the
three ISO 26262 hardware architectural metrics — **SPFM**, **LFM**, **PMHF** —
with two capabilities that spreadsheets cannot provide:

1. **Evidence tracking** — every DC value carries a test-evidence record
   (test case ID, validated DC, date, notes). The tool distinguishes
   *estimated* DC (from specification) from *validated* DC (from fault
   injection test).

2. **Validation debt** — metrics are computed in two modes: *planning*
   (estimated DC) and *validated* (confirmed test evidence only).
   The gap between the two is the **validation debt** — safety improvement
   claimed but not yet proved by test. Debt must reach zero before safety
   case closure (ISO 26262-5 Annex C requirement).

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
  λ Total                               290.00 FIT
  λ Safe (excluded)                      64.00 FIT
  λ Dangerous (total)                   226.00 FIT
  λ SPF+Residual undetected (plan)       4.450 FIT
  λ SPF+Residual undetected (valid)     41.270 FIT   ← validation debt visible

  Metrics               Planning    Validated   Target    Result
  SPFM                   98.03%      81.74%     ≥99%     ❌ FAIL
  LFM                    91.94%      31.29%     ≥90%     ❌ FAIL
  PMHF                   5.700 FIT   51.920 FIT ≤1 FIT   ❌ FAIL

  Validation Debt
  Unvalidated modes              : 6
  SPFM debt (plan − validated)   : +0.1629    ← close this before sign-off

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

| ASIL | SPFM | LFM | PMHF |
|------|------|-----|------|
| A | — | — | < 1000 FIT |
| B | ≥ 90% | ≥ 60% | < 100 FIT |
| C | ≥ 97% | ≥ 80% | < 10 FIT |
| D | ≥ 99% | ≥ 90% | < 1 FIT |

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
