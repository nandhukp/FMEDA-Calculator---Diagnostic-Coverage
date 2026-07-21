# FMEDA Calculator

A Python tool that computes ISO 26262 hardware architectural safety metrics —
**SPFM**, **LFM**, and **PMHF** — from a set of component failure modes.

## What it does

An FMEDA (Failure Mode Effects and Diagnostic Analysis) quantifies how well a
safety-critical design is protected against random hardware faults. For each
failure mode you provide a failure rate (in FIT) and a diagnostic coverage, and
the tool computes:

- **SPFM** (Single Point Fault Metric) — protection against single-point faults
- **LFM** (Latent Fault Metric) — protection against undetected latent faults
- **PMHF** (Probabilistic Metric for random Hardware Failures) — probability per
  hour of violating a safety goal

Results are checked against the ISO 26262 target for the selected ASIL (A–D).

## Usage

```python
from fmeda import FMEDA, FailureMode, report

f = FMEDA("My Element")
f.add(FailureMode("CPU compute error", "MCU core", lambda_fit=18.0, dc=0.99))
f.add(FailureMode("RAM bit error", "MCU RAM", lambda_fit=12.0, dc=0.97))
report(f, asil="D")
```

## Concepts

- **FIT**: failures per 10^9 hours.
- **Diagnostic coverage (dc)**: fraction of a mode's dangerous failure rate that
  a safety mechanism detects. Never claim 100% for software diagnostics.
- **Latent fault**: a dormant fault that is only hazardous if a second fault
  occurs before it is detected — addressed by LFM (and by BIST / periodic tests).

## Roadmap / ideas

- CSV import/export of failure modes
- Multi-block aggregation (roll up per-block metrics to a platform total)
- Full PMHF latent-exposure term
- Unit tests (pytest)

## Author

Nandakumar Palani — functional safety engineer (ISO 26262 / ADAS compute platforms)
