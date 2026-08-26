"""
Unit tests for fmeda.calculator
Verifies SPFM, LFM, PMHF formulas and evidence tracking logic.

Run:  python -m pytest tests/ -v

Author: Nandakumar Palani
"""

import json
import math
import pytest
from datetime import date

from fmeda import (
    FMEDA, FailureMode, Evidence, EvidenceStatus, ASIL_TARGETS, evaluate
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def simple_fmeda() -> FMEDA:
    """Minimal FMEDA with known-good hand-calculated values."""
    f = FMEDA("Test")
    # SPF: λ=10, DC=0.90 → uncov = 1.0 FIT
    f.add(FailureMode("SPF_A", "Comp", lambda_fit=10.0, dc=0.90))
    # SPF: λ=20, DC=0.95 → uncov = 1.0 FIT
    f.add(FailureMode("SPF_B", "Comp", lambda_fit=20.0, dc=0.95))
    # Latent: λ=10, DC=0.80 → uncov = 2.0 FIT
    f.add(FailureMode("LAT_A", "Comp", lambda_fit=10.0, dc=0.80, is_latent=True))
    # Safe: excluded
    f.add(FailureMode("SAFE",  "Comp", lambda_fit=5.0,  is_safety_related=False))
    return f


# ── SPFM tests ────────────────────────────────────────────────────────────────

class TestSPFM:
    def test_formula(self):
        """SPFM = 1 - SPF_uncov / dangerous_total."""
        f = simple_fmeda()
        # dangerous = 10 + 20 + 10 = 40 FIT  (safe excluded)
        # SPF uncov  = 10*0.10 + 20*0.05 = 1.0 + 1.0 = 2.0 FIT
        # SPFM = 1 - 2.0/40 = 0.95
        assert math.isclose(f.spfm(), 0.95, rel_tol=1e-6)

    def test_perfect_coverage(self):
        f = FMEDA("Perfect")
        f.add(FailureMode("FM", "C", lambda_fit=50.0, dc=1.0))
        assert f.spfm() == 1.0

    def test_zero_coverage(self):
        f = FMEDA("Zero")
        f.add(FailureMode("FM", "C", lambda_fit=50.0, dc=0.0))
        assert f.spfm() == 0.0

    def test_no_dangerous_modes(self):
        f = FMEDA("OnlySafe")
        f.add(FailureMode("SAFE", "C", lambda_fit=100.0, is_safety_related=False))
        assert f.spfm() == 1.0   # no dangerous modes → SPFM = 1

    def test_asil_b_target(self):
        f = simple_fmeda()
        r = evaluate(f, "B")
        # SPFM = 0.95 ≥ 0.90 → PASS
        assert r["spfm_pass"] is True

    def test_asil_d_fail(self):
        f = simple_fmeda()
        r = evaluate(f, "D")
        # SPFM = 0.95 < 0.99 → FAIL
        assert r["spfm_pass"] is False

    def test_safe_faults_excluded_from_denominator(self):
        f = FMEDA("SafeExcl")
        f.add(FailureMode("SAFE", "C", lambda_fit=1000.0, is_safety_related=False))
        f.add(FailureMode("SPF",  "C", lambda_fit=10.0, dc=0.99))
        # denominator = 10, NOT 1010
        assert math.isclose(f.spfm(), 1 - (10*0.01)/10, rel_tol=1e-6)


# ── LFM tests ─────────────────────────────────────────────────────────────────

class TestLFM:
    def test_formula(self):
        """LFM = 1 - latent_uncov / latent_total."""
        f = simple_fmeda()
        # latent total = 10, uncov = 2.0
        # LFM = 1 - 2.0/10 = 0.80
        assert math.isclose(f.lfm(), 0.80, rel_tol=1e-6)

    def test_no_latent_modes(self):
        f = FMEDA("NoLatent")
        f.add(FailureMode("SPF", "C", lambda_fit=10.0, dc=0.90))
        assert f.lfm() == 1.0   # no latent → LFM = 1

    def test_asil_d_target(self):
        f = FMEDA("LFM_D")
        f.add(FailureMode("LAT", "C", lambda_fit=10.0, dc=0.91, is_latent=True))
        r = evaluate(f, "D")
        assert r["lfm_pass"] is True


# ── PMHF tests ────────────────────────────────────────────────────────────────

class TestPMHF:
    def test_formula(self):
        """PMHF = SPF_uncov + latent_uncov/2."""
        f = simple_fmeda()
        # SPF_uncov = 2.0, latent_uncov = 2.0
        # PMHF = 2.0 + 2.0/2 = 3.0 FIT
        assert math.isclose(f.pmhf(), 3.0, rel_tol=1e-6)

    def test_pmhf_per_hour_conversion(self):
        f = FMEDA("PH")
        f.add(FailureMode("FM", "C", lambda_fit=10.0, dc=0.90))
        assert math.isclose(f.pmhf_per_hour(), 1.0e-9, rel_tol=1e-6)


# ── Evidence and validation debt tests ───────────────────────────────────────

class TestEvidence:
    def test_validated_dc_used_in_validated_mode(self):
        f = FMEDA("EvidTest")
        ev = Evidence("TC-01", EvidenceStatus.VALIDATED, validated_dc=0.80)
        f.add(FailureMode("FM", "C", lambda_fit=10.0, dc=0.99, evidence=ev))
        # Planning mode: dc=0.99 → uncov = 0.1
        assert math.isclose(f.spfm(validated_only=False), 1 - 0.1/10, rel_tol=1e-6)
        # Validated mode: dc=0.80 → uncov = 2.0
        assert math.isclose(f.spfm(validated_only=True),  1 - 2.0/10, rel_tol=1e-6)

    def test_unvalidated_mode_treated_as_zero_dc(self):
        f = FMEDA("Unval")
        ev = Evidence("TC-01", EvidenceStatus.ESTIMATED)  # not confirmed
        f.add(FailureMode("FM", "C", lambda_fit=10.0, dc=0.99, evidence=ev))
        # Validated mode: dc=0 → uncov = 10.0 FIT → SPFM = 0.0
        assert math.isclose(f.spfm(validated_only=True), 0.0, rel_tol=1e-6)

    def test_validation_debt_zero_when_all_validated(self):
        f = FMEDA("AllVal")
        ev = Evidence("TC-01", EvidenceStatus.VALIDATED, validated_dc=0.99)
        f.add(FailureMode("FM", "C", lambda_fit=10.0, dc=0.99, evidence=ev))
        debt = f.validation_debt()
        assert debt["unvalidated_modes"] == 0
        assert math.isclose(debt["spfm_debt"], 0.0, abs_tol=1e-9)

    def test_validation_debt_nonzero_when_estimated(self):
        f = FMEDA("Debt")
        # Estimated DC = 0.99; no test run → validated DC = 0
        ev = Evidence("TC-01", EvidenceStatus.ESTIMATED)
        f.add(FailureMode("FM", "C", lambda_fit=10.0, dc=0.99, evidence=ev))
        debt = f.validation_debt()
        assert debt["unvalidated_modes"] == 1
        assert debt["spfm_debt"] > 0

    def test_in_review_not_confirmed(self):
        ev = Evidence("TC-01", EvidenceStatus.IN_REVIEW, validated_dc=0.95)
        assert ev.is_confirmed is False   # IN_REVIEW is not VALIDATED

    def test_evidence_dc_range_validation(self):
        with pytest.raises(ValueError):
            Evidence("TC-BAD", EvidenceStatus.VALIDATED, validated_dc=1.5)


# ── Worst contributor ranking ─────────────────────────────────────────────────

class TestWorstContributors:
    def test_ranking_order(self):
        f = FMEDA("Rank")
        f.add(FailureMode("Low",  "C", lambda_fit=10.0, dc=0.99))  # uncov=0.10
        f.add(FailureMode("High", "C", lambda_fit=10.0, dc=0.50))  # uncov=5.00
        f.add(FailureMode("Mid",  "C", lambda_fit=10.0, dc=0.80))  # uncov=2.00
        ranked = f.worst_contributors(n=3)
        assert ranked[0].name == "High"
        assert ranked[1].name == "Mid"
        assert ranked[2].name == "Low"

    def test_safe_modes_excluded_from_ranking(self):
        f = FMEDA("SafeExcl")
        f.add(FailureMode("SAFE", "C", lambda_fit=1000.0, is_safety_related=False))
        f.add(FailureMode("SPF",  "C", lambda_fit=10.0, dc=0.90))
        ranked = f.worst_contributors()
        assert len(ranked) == 1
        assert ranked[0].name == "SPF"


# ── Serialisation round-trip ─────────────────────────────────────────────────

class TestSerialisation:
    def test_json_roundtrip(self):
        f = FMEDA("RoundTrip")
        ev = Evidence("TC-01", EvidenceStatus.VALIDATED, 0.95, date(2024, 9, 1), "ok")
        f.add(FailureMode("FM", "C", lambda_fit=10.0, dc=0.95, evidence=ev,
                          safety_mechanism="WD", lambda_source="SN29500"))
        j = f.to_json()
        f2 = FMEDA.from_json(j)
        assert f2.name == f.name
        assert len(f2.modes) == 1
        m2 = f2.modes[0]
        assert m2.name == "FM"
        assert math.isclose(m2.lambda_fit, 10.0)
        assert math.isclose(m2.dc, 0.95)
        assert m2.evidence is not None
        assert m2.evidence.status == EvidenceStatus.VALIDATED
        assert math.isclose(m2.evidence.validated_dc, 0.95)

    def test_failure_mode_dc_validation(self):
        with pytest.raises(ValueError):
            FailureMode("Bad", "C", lambda_fit=10.0, dc=1.5)

    def test_negative_lambda_rejected(self):
        with pytest.raises(ValueError):
            FailureMode("Bad", "C", lambda_fit=-1.0)
