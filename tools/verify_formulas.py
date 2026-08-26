#!/usr/bin/env python3
"""
verify_formulas.py — Deterministic regression check for the FMEDA calculator.

WHAT THIS DOES
---------------
Anyone who clones this repo can run:

    PYTHONPATH=. python3 tools/verify_formulas.py

...and get an immediate PASS/FAIL verdict on whether the ISO 26262-5 formulas
(SPFM, LFM, PMHF) and ASIL target table in fmeda/calculator.py are still
computing correctly.

This is intentionally NOT an AI check — it's a hard, deterministic assertion
against reference numbers taken directly from a verified ISO 26262-5
worksheet (a matched real-world example with known correct SPFM/LFM/PMHF
output). If the formulas are ever accidentally changed, broken by a
refactor, or tampered with, this script fails loudly and immediately.

WHY THIS MATTERS FOR A PUBLIC REPO
-----------------------------------
Formula correctness is exactly the kind of bug that's invisible until an
auditor catches it. This script exists so that:
  1. Every push/PR is auto-checked by CI (see .github/workflows/formula-check.yml)
  2. Anyone downloading the repo can independently verify correctness in
     under a second, without trusting anyone's claims (including mine)
  3. Regressions are caught the moment they're introduced, not months later

Exit code 0 = all checks passed.
Exit code 1 = at least one check failed (formula regression detected).
"""

from __future__ import annotations
import sys
from datetime import date

sys.path.insert(0, ".")

from fmeda import FMEDA, FailureMode, Evidence, EvidenceStatus, ASIL_TARGETS


# ── Reference case: known-correct values from a verified ISO 26262-5 worksheet
#
#   λMPF,D = 572.96824750 FIT   (detected multi-point/latent faults)
#   λMPF,L =  62.48065204 FIT   (undetected multi-point/latent faults)
#   λSPF   =   0.00000000 FIT   (pure single-point faults, no safety mechanism)
#   λRF    =  78.69185011 FIT   (residual faults, uncovered portion)
#   λs     = 199.16940000 FIT   (safe faults, excluded from all metrics)
#   λ      = 1020.42723766 FIT  (total safety-related failure rate)
#
#   Expected results (computed independently in the source worksheet):
#     SPFM = 92.28834284 %
#     LFM  = 93.36749018 %
#     PMHF = 78.69185011 FIT

REFERENCE = {
    "lambda_mpf_det": 572.96824750,
    "lambda_mpf_l":    62.48065204,
    "lambda_spf":       0.00000000,
    "lambda_rf":       78.69185011,
    "lambda_safe":    199.16940000,
    "lambda_total":  1020.42723766,
    "expected_spfm_pct": 92.28834284,
    "expected_lfm_pct":  93.36749018,
    "expected_pmhf_fit": 78.69185011,
}

# Tolerance: source worksheet numbers carry rounding in their intermediate
# cells, so we allow a very small epsilon rather than requiring bit-exact match.
TOLERANCE_PCT = 0.01     # 0.01 percentage points for SPFM/LFM
TOLERANCE_FIT = 0.001    # 0.001 FIT for PMHF


def build_reference_fmeda() -> FMEDA:
    """
    Reconstruct a FMEDA whose lambda_breakdown() reproduces the exact
    reference values above. We do this with four synthetic failure modes,
    one per category, so the breakdown sums land exactly on the reference
    numbers regardless of how many real-world modes a user's own FMEDA has.
    """
    f = FMEDA("Formula Verification Reference Case")

    # λSPF: safety-related, non-latent, DC=0 (no safety mechanism at all)
    if REFERENCE["lambda_spf"] > 0:
        f.add(FailureMode(
            name="[ref] Pure SPF — no safety mechanism",
            component="Reference", lambda_fit=REFERENCE["lambda_spf"],
            dc=0.0, is_safety_related=True, is_latent=False,
        ))

    # λRF: safety-related, non-latent, DC>0, uncovered portion = lambda_rf.
    # Solve the underlying full lambda_fit + dc from the worksheet identity:
    #   lambda_total = lambda_safe + lambda_mpf_total + lambda_spf + lambda_rf_full
    #   → lambda_rf_full = lambda_total - lambda_safe - lambda_mpf_total - lambda_spf
    #   dc s.t. lambda_rf_full * (1 - dc) = lambda_rf (the uncovered/reported portion)
    if REFERENCE["lambda_rf"] > 0:
        lam_mpf_total = REFERENCE["lambda_mpf_det"] + REFERENCE["lambda_mpf_l"]
        lam_rf_full = (REFERENCE["lambda_total"] - REFERENCE["lambda_safe"]
                       - lam_mpf_total - REFERENCE["lambda_spf"])
        dc = 1.0 - (REFERENCE["lambda_rf"] / lam_rf_full)
        f.add(FailureMode(
            name="[ref] Residual fault — SM exists, partial coverage",
            component="Reference", lambda_fit=lam_rf_full,
            dc=dc, is_safety_related=True, is_latent=False,
        ))

    # λMPF,det + λMPF,L: one latent mode split via DC so that
    # lambda_fit*dc == lambda_mpf_det and lambda_fit*(1-dc) == lambda_mpf_l
    lam_latent_total = REFERENCE["lambda_mpf_det"] + REFERENCE["lambda_mpf_l"]
    dc_latent = REFERENCE["lambda_mpf_det"] / lam_latent_total
    f.add(FailureMode(
        name="[ref] Latent (multi-point) fault",
        component="Reference", lambda_fit=lam_latent_total,
        dc=dc_latent, is_safety_related=True, is_latent=True,
    ))

    # λs: safe fault, excluded from all metrics
    if REFERENCE["lambda_safe"] > 0:
        f.add(FailureMode(
            name="[ref] Safe fault",
            component="Reference", lambda_fit=REFERENCE["lambda_safe"],
            dc=0.0, is_safety_related=False, is_latent=False,
        ))

    return f


def check(label: str, actual: float, expected: float, tol: float) -> bool:
    ok = abs(actual - expected) <= tol
    status = "✅ PASS" if ok else "❌ FAIL"
    print(f"  {status}  {label:<45} actual={actual:>14.8f}  expected={expected:>14.8f}  "
          f"Δ={actual-expected:+.8f}")
    return ok


def check_asil_targets() -> bool:
    """
    Verify ASIL_TARGETS exactly matches the combined ISO 26262-5 Table 5/6
    reference table:
        A: no target (spfm=None, lfm=None, pmhf_fit=None)
        B: spfm>90%,  lfm>60%,  pmhf<100 FIT
        C: spfm>97%,  lfm>80%,  pmhf<100 FIT
        D: spfm>99%,  lfm>90%,  pmhf< 10 FIT
    """
    expected = {
        "A": {"spfm": None, "lfm": None, "pmhf_fit": None},
        "B": {"spfm": 0.90, "lfm": 0.60, "pmhf_fit": 100.0},
        "C": {"spfm": 0.97, "lfm": 0.80, "pmhf_fit": 100.0},
        "D": {"spfm": 0.99, "lfm": 0.90, "pmhf_fit":  10.0},
    }
    all_ok = True
    for asil, exp in expected.items():
        actual = ASIL_TARGETS.get(asil)
        ok = actual == exp
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}  ASIL {asil} targets{'':<32} actual={actual}  expected={exp}")
        all_ok = all_ok and ok
    return all_ok


def main() -> int:
    print("=" * 78)
    print("  FMEDA CALCULATOR — FORMULA VERIFICATION")
    print("  Deterministic regression check against known-correct reference case")
    print("=" * 78)

    results = []

    print("\n[1/2] ASIL Target Table (combined ISO 26262-5 Table 5/6)")
    print("-" * 78)
    results.append(check_asil_targets())

    print("\n[2/2] SPFM / LFM / PMHF Formula Output")
    print("-" * 78)
    f = build_reference_fmeda()
    bd = f.lambda_breakdown(validated_only=False)

    # Sanity: breakdown itself should reproduce the raw reference inputs
    results.append(check("λ_total  (breakdown, incl. safe)", bd["lambda_total"],
                          REFERENCE["lambda_total"], 0.01))
    results.append(check("λ_SPF    (breakdown)", bd["lambdaSPF"],
                          REFERENCE["lambda_spf"], 0.01))
    results.append(check("λ_RF     (breakdown)", bd["lambdaRF"],
                          REFERENCE["lambda_rf"], 0.01))
    results.append(check("λ_MPF,L  (breakdown)", bd["lambdaMPF_L"],
                          REFERENCE["lambda_mpf_l"], 0.01))

    # The actual metrics under test
    spfm = f.spfm(validated_only=False) * 100
    lfm  = f.lfm(validated_only=False)  * 100
    pmhf = f.pmhf(validated_only=False)

    results.append(check("SPFM formula", spfm, REFERENCE["expected_spfm_pct"], TOLERANCE_PCT))
    results.append(check("LFM formula",  lfm,  REFERENCE["expected_lfm_pct"],  TOLERANCE_PCT))
    results.append(check("PMHF formula", pmhf, REFERENCE["expected_pmhf_fit"], TOLERANCE_FIT))

    print("\n" + "=" * 78)
    if all(results):
        print("  ✅ ALL CHECKS PASSED — formulas match the verified reference case")
        print("=" * 78)
        return 0
    else:
        failed = len([r for r in results if not r])
        print(f"  ❌ {failed} CHECK(S) FAILED — formula regression detected")
        print("     Do not trust output until this is fixed.")
        print("=" * 78)
        return 1


if __name__ == "__main__":
    sys.exit(main())
