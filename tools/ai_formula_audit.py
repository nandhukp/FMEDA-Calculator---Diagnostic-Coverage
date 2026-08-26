#!/usr/bin/env python3
"""
ai_formula_audit.py — AI-assisted narrative review of the FMEDA calculator.

WHAT THIS IS (AND ISN'T)
--------------------------
This is a *complement* to tools/verify_formulas.py, not a replacement.

  verify_formulas.py  → deterministic, free, instant, runs in CI on every
                         push. Catches numeric regressions with certainty.

  ai_formula_audit.py → uses the Anthropic API to have Claude read the
                         actual calculator.py source and the ISO 26262-5
                         formula definitions, then produce a narrative
                         second opinion: does the CODE's logic match the
                         DOCSTRING's claimed formula? Are there edge cases
                         (λ_total=0, all-safe FMEDA, DC=1.0 exactly) that
                         look under-handled? Does terminology match the
                         standard consistently?

WHY THIS CAN'T RUN "ON EVERY DOWNLOAD"
----------------------------------------
There is no GitHub mechanism that fires when someone clones or downloads a
public repo — git and GitHub's zip-download endpoint are static file
transfers with no server-side hook. The two realistic options are:

  1. Run this manually, whenever you want a deep review (this script).
  2. Wire it into CI via workflow_dispatch or on release tags, using a
     repository secret ANTHROPIC_API_KEY (see
     .github/workflows/ai-audit.yml) — this runs on YOUR schedule (e.g.
     each release), not on every anonymous clone, because each run costs
     API tokens that someone has to pay for.

Either way, the AI audit's output (this script writes a dated Markdown
report) can be committed to the repo, so anyone browsing it later sees
the AI's most recent independent review without needing their own API key.

USAGE
-----
    export ANTHROPIC_API_KEY=sk-ant-...
    pip install anthropic --break-system-packages
    PYTHONPATH=. python3 tools/ai_formula_audit.py

Writes: audit_reports/ai_audit_<date>.md
"""

from __future__ import annotations
import os
import sys
from datetime import date
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: the 'anthropic' package is required for this script.")
    print("Install it with:  pip install anthropic --break-system-packages")
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
CALCULATOR_PATH = REPO_ROOT / "fmeda" / "calculator.py"
VERIFY_PATH = REPO_ROOT / "tools" / "verify_formulas.py"
OUTPUT_DIR = REPO_ROOT / "audit_reports"

REFERENCE_ISO_DEFINITIONS = """
ISO 26262-5 Hardware Architectural Metrics — reference formula definitions
used for this audit (combined Table 5 / Table 6 target values, and the
SPFM / LFM / PMHF formula structure):

    SPFM = (1 − (Σλ_SPF + Σλ_RF) / Σλ) × 100
    LFM  = (1 − Σλ_MPF,L / (Σλ − Σλ_SPF − Σλ_RF)) × 100
    PMHF_est = Σλ_SPF + Σλ_RF + Σλ_MPF,det × Σλ_MPF,latent × T_lifetime
               (simplified: PMHF_est ≈ Σλ_SPF + Σλ_RF, since the dual-point
               product term is numerically negligible and conventionally
               omitted)

    Where:
      λ_SPF      = cumulated failure rate of single-point faults (no safety
                   mechanism at all, DC = 0%)
      λ_RF       = cumulated failure rate of residual faults (safety
                   mechanism exists, but coverage < 100% — the UNCOVERED
                   portion, λ × (1 − DC))
      λ_MPF,det  = cumulated failure rate of latent/multi-point faults that
                   ARE detected within the diagnostic test interval (λ × DC)
      λ_MPF,L    = cumulated failure rate of latent/multi-point faults that
                   are NOT detected (λ × (1 − DC))
      λ (Σλ)     = TOTAL base failure rate, including safe (non-safety-
                   related) faults — this is the denominator for BOTH SPFM
                   and LFM. (This is a specific, verified convention from
                   the source worksheet this tool was built against — some
                   other ISO 26262 implementations use a safety-related-only
                   denominator instead, so this is worth flagging if you see
                   inconsistency.)

    ASIL targets (combined Table 5 / Table 6):
        ASIL A: no target for any metric
        ASIL B: SPFM > 90%, LFM > 60%, PMHF < 100 FIT
        ASIL C: SPFM > 97%, LFM > 80%, PMHF < 100 FIT
        ASIL D: SPFM > 99%, LFM > 90%, PMHF <  10 FIT
"""


def build_prompt(calculator_source: str, verify_source: str) -> str:
    return f"""You are a functional safety engineer performing an independent
code audit of an ISO 26262-5 FMEDA (Failure Mode, Effects and Diagnostic
Analysis) calculator. Your job is to check whether the CODE correctly
implements the ISO 26262-5 formulas as I've defined them below, and to
flag any discrepancy, ambiguous edge case, or terminology inconsistency.

{REFERENCE_ISO_DEFINITIONS}

Below is the actual source code of the calculator (fmeda/calculator.py),
followed by its existing deterministic regression test
(tools/verify_formulas.py).

Please produce a structured Markdown audit report with these sections:

## 1. Formula Correctness
For each of SPFM, LFM, PMHF: does the code's implementation match the
reference definition above? Quote the specific line(s) of code and explain
your reasoning. If you find a discrepancy, state it clearly and explain
the numeric impact (does it make the metric look better or worse than it
should?).

## 2. ASIL Target Table
Does ASIL_TARGETS match the reference target table above exactly?

## 3. Edge Cases
Check these specific scenarios and state whether the code handles them
sensibly:
  - An FMEDA with zero failure modes
  - An FMEDA where every mode is safe (is_safety_related=False)
  - A failure mode with DC exactly 0.0 vs DC exactly 1.0
  - lambda_total == 0 (division by zero risk)
  - A latent mode with DC == 0 (fully undetected latent fault)

## 4. Terminology Consistency
Does the code's variable naming and docstrings consistently match ISO
26262-5 terminology (λ_SPF, λ_RF, λ_MPF,det, λ_MPF,latent)? Flag anything
that could confuse a future maintainer.

## 5. Test Coverage Gap Analysis
Does tools/verify_formulas.py actually exercise the formulas in a way that
would catch a regression? Are there scenarios NOT covered by the existing
test that you'd want covered?

## 6. Overall Verdict
One paragraph: PASS / PASS WITH CONCERNS / FAIL, and why.

Be specific and cite line numbers or exact code snippets. Do not be
diplomatically vague — if something is wrong, say so plainly with the
numeric consequence.

=== fmeda/calculator.py ===
```python
{calculator_source}
```

=== tools/verify_formulas.py ===
```python
{verify_source}
```
"""


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        print("Get a key at https://console.anthropic.com and:")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        return 1

    if not CALCULATOR_PATH.exists():
        print(f"ERROR: {CALCULATOR_PATH} not found. Run this from the repo root.")
        return 1

    calculator_source = CALCULATOR_PATH.read_text()
    verify_source = VERIFY_PATH.read_text() if VERIFY_PATH.exists() else "(not found)"

    print("Sending calculator.py + verify_formulas.py to Claude for audit...")
    print("(This costs API tokens — roughly the size of both files combined "
          "plus response length.)\n")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_prompt(calculator_source, verify_source)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    audit_text = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"ai_audit_{date.today().isoformat()}.md"
    header = (
        f"# AI Formula Audit — {date.today().isoformat()}\n\n"
        f"Generated by `tools/ai_formula_audit.py` using the Anthropic API.\n"
        f"This is a narrative second opinion, complementary to the "
        f"deterministic checks in `tools/verify_formulas.py`. It is not a "
        f"substitute for human functional-safety review or the CI-enforced "
        f"regression test.\n\n---\n\n"
    )
    out_path.write_text(header + audit_text)

    print(f"Audit written to: {out_path}")
    print("\n" + "=" * 78)
    print(audit_text[:2000])
    print("..." if len(audit_text) > 2000 else "")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    sys.exit(main())
