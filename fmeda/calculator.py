"""
FMEDA Calculator — Failure Mode Effects and Diagnostic Analysis
ISO 26262 Hardware Architectural Metrics: SPFM, LFM, PMHF

Author : Nandakumar Palani
License: MIT

This module implements the ISO 26262-5 FMEDA methodology with two key
enhancements over a plain spreadsheet:

  1. Evidence tracking  — every diagnostic coverage (DC) value carries an
     optional test-evidence reference (test case ID, date, result).  Without
     evidence the row is flagged as *estimated*.

  2. Validation debt    — SPFM / LFM / PMHF are computed in two modes:
       • planning  : all DC values (estimated + validated)
       • validated : only rows with confirmed test evidence; unvalidated rows
                     are treated as DC = 0.
     The gap between the two modes is the *validation debt* — the safety
     improvement that is claimed but not yet proved by test.  This debt must
     reach zero before safety-case closure.

ISO 26262-5 references
  • Table 3  : SPFM / LFM targets per ASIL
  • Table 4  : PMHF targets per ASIL
  • Annex C  : DC justification requirements
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional, Dict, Any


# ── Enumerations ──────────────────────────────────────────────────────────────

class FaultClass(Enum):
    """ISO 26262-5 §8.4 fault categories."""
    SAFE         = "safe"          # no effect on safety goal
    SPF          = "single_point"  # directly violates SG; no diagnostic
    RESIDUAL     = "residual"      # SPF partially covered; uncovered portion
    MPF_DETECTED = "mpf_detected"  # latent fault detected within DTI
    MPF_LATENT   = "mpf_latent"    # latent fault NOT detected within DTI


class EvidenceStatus(Enum):
    """Life-cycle state of a DC value."""
    ESTIMATED  = "estimated"   # analysis / specification only
    IN_REVIEW  = "in_review"   # test executed; result under review
    VALIDATED  = "validated"   # test passed; DC confirmed


# ── Evidence record ───────────────────────────────────────────────────────────

@dataclass
class Evidence:
    """
    Traceability record linking a DC value to a fault-injection test result.

    Attributes
    ----------
    test_id      : identifier from the test management system (e.g. TC-SOC-01)
    status       : EvidenceStatus — validated, in_review, or estimated
    validated_dc : DC confirmed by the test (may differ from the design estimate)
    test_date    : date the test was executed
    notes        : free-text; detection latency, pass/fail detail, DTC raised
    """
    test_id      : str
    status       : EvidenceStatus           = EvidenceStatus.ESTIMATED
    validated_dc : Optional[float]          = None   # None until test runs
    test_date    : Optional[date]           = None
    notes        : str                      = ""

    def __post_init__(self):
        if self.validated_dc is not None and not 0.0 <= self.validated_dc <= 1.0:
            raise ValueError(
                f"Evidence {self.test_id}: validated_dc must be 0..1, "
                f"got {self.validated_dc}"
            )

    @property
    def is_confirmed(self) -> bool:
        """True when test result is available (validated or in review)."""
        return self.status == EvidenceStatus.VALIDATED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id"      : self.test_id,
            "status"       : self.status.value,
            "validated_dc" : self.validated_dc,
            "test_date"    : str(self.test_date) if self.test_date else None,
            "notes"        : self.notes,
        }


# ── Failure mode ──────────────────────────────────────────────────────────────

@dataclass
class FailureMode:
    """
    One failure mode of one hardware element.

    Parameters
    ----------
    name              : short description (e.g. "CPU lockstep mismatch")
    component         : hardware element (e.g. "Safety MCU", "Compute SoC")
    lambda_fit        : failure rate in FIT (failures per 1 × 10⁹ hours)
    dc                : estimated diagnostic coverage 0.0 – 1.0
    is_safety_related : False → safe fault; excluded from all metric denominators
    is_latent         : True  → multi-point / latent fault → feeds LFM not SPFM
    evidence          : optional Evidence record; presence means DC was validated
    safety_mechanism  : description of the SM that provides the DC
    lambda_source     : source of the failure rate (e.g. "SN 29500 Table 5")
    """
    name              : str
    component         : str
    lambda_fit        : float
    dc                : float                  = 0.0
    is_safety_related : bool                   = True
    is_latent         : bool                   = False
    evidence          : Optional[Evidence]     = None
    safety_mechanism  : str                    = ""
    lambda_source     : str                    = ""

    def __post_init__(self):
        if not 0.0 <= self.dc <= 1.0:
            raise ValueError(f"{self.name}: dc must be 0..1, got {self.dc}")
        if self.lambda_fit < 0:
            raise ValueError(f"{self.name}: lambda_fit must be >= 0")

    # ── Effective DC (planning vs validated mode) ─────────────────────────────

    def effective_dc(self, validated_only: bool = False) -> float:
        """
        Return the DC to use in metric calculations.

        validated_only=False  → use self.dc (estimated or validated)
        validated_only=True   → use evidence.validated_dc if confirmed,
                                else 0.0 (unvalidated rows treated as uncovered)
        """
        if not validated_only:
            return self.dc
        if self.evidence and self.evidence.is_confirmed:
            return self.evidence.validated_dc if self.evidence.validated_dc is not None else self.dc
        return 0.0

    @property
    def evidence_status(self) -> EvidenceStatus:
        if self.evidence is None:
            return EvidenceStatus.ESTIMATED
        return self.evidence.status

    @property
    def is_validated(self) -> bool:
        return self.evidence is not None and self.evidence.is_confirmed

    # ── Failure-rate split ────────────────────────────────────────────────────

    @property
    def lambda_safe(self) -> float:
        return self.lambda_fit if not self.is_safety_related else 0.0

    @property
    def lambda_dangerous(self) -> float:
        return self.lambda_fit if self.is_safety_related else 0.0

    def lambda_detected(self, validated_only: bool = False) -> float:
        return self.lambda_dangerous * self.effective_dc(validated_only)

    def lambda_undetected(self, validated_only: bool = False) -> float:
        return self.lambda_dangerous * (1.0 - self.effective_dc(validated_only))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name"              : self.name,
            "component"         : self.component,
            "lambda_fit"        : self.lambda_fit,
            "dc"                : self.dc,
            "is_safety_related" : self.is_safety_related,
            "is_latent"         : self.is_latent,
            "safety_mechanism"  : self.safety_mechanism,
            "lambda_source"     : self.lambda_source,
            "evidence"          : self.evidence.to_dict() if self.evidence else None,
        }


# ── FMEDA engine ──────────────────────────────────────────────────────────────

@dataclass
class FMEDA:
    """
    A collection of FailureMode entries for one item / system element.

    Usage
    -----
    fmeda = FMEDA("Safety MCU + Compute SoC channel")
    fmeda.add(FailureMode(...))
    report(fmeda, asil="D")
    """
    name : str
    modes: List[FailureMode] = field(default_factory=list)

    def add(self, mode: FailureMode) -> None:
        self.modes.append(mode)

    # ── Aggregate rates ───────────────────────────────────────────────────────

    @property
    def lambda_total(self) -> float:
        return sum(m.lambda_fit for m in self.modes)

    @property
    def lambda_safe(self) -> float:
        return sum(m.lambda_safe for m in self.modes)

    @property
    def lambda_dangerous_total(self) -> float:
        return sum(m.lambda_dangerous for m in self.modes)

    @property
    def lambda_latent_total(self) -> float:
        return sum(m.lambda_dangerous for m in self.modes if m.is_latent)

    def lambda_spf_residual(self, validated_only: bool = False) -> float:
        """Undetected dangerous single-point + residual fault rate."""
        return sum(
            m.lambda_undetected(validated_only)
            for m in self.modes
            if m.is_safety_related and not m.is_latent
        )

    def lambda_latent_undetected(self, validated_only: bool = False) -> float:
        """Latent (multi-point) fault rate that escapes detection."""
        return sum(
            m.lambda_undetected(validated_only)
            for m in self.modes
            if m.is_safety_related and m.is_latent
        )

    # ── ISO 26262-5 metrics ───────────────────────────────────────────────────

    def spfm(self, validated_only: bool = False) -> float:
        """
        Single-Point Fault Metric (ISO 26262-5, Table 3).

        Per ISO 26262-5:
            SPFM = (1 − (Σλ_SPF + Σλ_RF) / Σλ_total) × 100
        
        Where:
            Σλ_SPF = cumulated failure rate of single-point faults (undetected)
            Σλ_RF  = cumulated failure rate of residual faults (undetected portion)
            Σλ_total = total safety-related failure rate

        validated_only=True uses only test-confirmed DC values.
        """
        lambda_total = self.lambda_dangerous_total
        if lambda_total == 0:
            return 1.0
        
        lambda_uncov = self.lambda_spf_residual(validated_only)
        return (1.0 - lambda_uncov / lambda_total)

    def lfm(self, validated_only: bool = False) -> float:
        """
        Latent Fault Metric (ISO 26262-5, Table 3).

        Exact formula (per source worksheet):
            LFM = (1 − Σλ_MPF,L / (Σλ_total − Σλ_SPF − Σλ_RF)) × 100

        Where:
            Σλ_total          = total safety-related failure rate (λ)
            Σλ_SPF            = cumulated undetected single-point fault rate
            Σλ_RF             = cumulated undetected residual fault rate
            Σλ_total−ΣSPF−ΣRF = denominator = the portion of λ that is NOT
                                 single-point/residual, i.e. the multi-point-fault
                                 pool (both λ_MPF,detected AND λ_MPF,latent)

        NOTE: This denominator is NOT simply "total latent mode λ" — it is
        λ_total minus the SPF/RF pool, matching the source worksheet exactly.
        (Differs subtly from a naive "latent-only total" denominator.)

        validated_only=True uses only test-confirmed DC values.
        """
        bd = self.lambda_breakdown(validated_only)
        denominator = bd["lambda_total"] - bd["lambdaSPF"] - bd["lambdaRF"]
        if denominator <= 0:
            return 1.0
        return (1.0 - bd["lambdaMPF_L"] / denominator)

    def pmhf(self, validated_only: bool = False, full: bool = False,
             t_lifetime_hours: float = 0.0) -> float:
        """
        Probabilistic Metric for random Hardware Failures, in FIT
        (ISO 26262-5, Table 4).

        Simplified formula (default; matches source worksheet):
            PMHF_est = Σλ_SPF + Σλ_RF

        Full formula (ISO 26262-5, set full=True with t_lifetime_hours):
            PMHF_est = Σλ_SPF + Σλ_RF + (Σλ_MPF,det × Σλ_MPF,latent × T_lifetime)

        The third (dual-point-fault) term is a *product* of two already-tiny
        FIT-scale (×10⁻⁹/hr) rates times an operational-lifetime duration in
        hours — numerically negligible (per source worksheet note) and
        conventionally omitted. It's included here only if full=True.

        T_lifetime: operational lifetime in hours.
            Passenger car : 1 h/day  × 365 × (service years)
            Commercial    : 10 h/day × 365 × (service years)

        validated_only=True uses only test-confirmed DC values.
        """
        bd = self.lambda_breakdown(validated_only)
        pmhf_est = bd["lambdaSPF"] + bd["lambdaRF"]

        if full:
            # Convert FIT (per 1e9 hr) to per-hour rate before multiplying
            lam_det_per_hr    = bd["lambdaMPF_det"] * 1e-9
            lam_latent_per_hr = bd["lambdaMPF_L"]    * 1e-9
            dpf_term_per_hr   = lam_det_per_hr * lam_latent_per_hr * t_lifetime_hours
            pmhf_est += dpf_term_per_hr * 1e9   # convert back to FIT for display

        return pmhf_est

    def pmhf_per_hour(self, validated_only: bool = False, **kwargs) -> float:
        """PMHF expressed as probability per hour (FIT × 10⁻⁹)."""
        return self.pmhf(validated_only, **kwargs) * 1e-9

    # ── Validation debt ───────────────────────────────────────────────────────

    def validation_debt(self) -> Dict[str, float]:
        """
        Compute the gap between planning metrics (estimated DC) and
        validated metrics (confirmed DC only).

        Returns a dict with keys:
          spfm_planning, spfm_validated, spfm_debt
          lfm_planning,  lfm_validated,  lfm_debt
          pmhf_planning, pmhf_validated, pmhf_debt   (all in FIT)
          unvalidated_modes : count of modes without confirmed evidence
          unvalidated_fit   : total uncovered FIT from unvalidated modes
        """
        sp = self.spfm(False);  sv = self.spfm(True)
        lp = self.lfm(False);   lv = self.lfm(True)
        pp = self.pmhf(False);  pv = self.pmhf(True)

        unvalidated = [m for m in self.modes if m.is_safety_related and not m.is_validated]
        unvalidated_fit = sum(
            m.lambda_undetected(False) - m.lambda_undetected(True)
            for m in self.modes
            if m.is_safety_related
        )

        return {
            "spfm_planning"    : sp,
            "spfm_validated"   : sv,
            "spfm_debt"        : sp - sv,          # must → 0 at closure
            "lfm_planning"     : lp,
            "lfm_validated"    : lv,
            "lfm_debt"         : lp - lv,
            "pmhf_planning"    : pp,
            "pmhf_validated"   : pv,
            "pmhf_debt"        : pv - pp,          # validated PMHF is worse
            "unvalidated_modes": len(unvalidated),
            "unvalidated_fit"  : max(0.0, unvalidated_fit),
        }

    # ── Worst-contributor ranking ─────────────────────────────────────────────

    def worst_contributors(
        self,
        n: int = 5,
        validated_only: bool = False,
    ) -> List[FailureMode]:
        """
        Return up to n FailureModes ranked by uncovered λ (descending).
        Only safety-related modes are included.
        """
        ranked = sorted(
            [m for m in self.modes if m.is_safety_related],
            key=lambda m: m.lambda_undetected(validated_only),
            reverse=True,
        )
        return ranked[:n]

    # ── Unvalidated-mode backlog ──────────────────────────────────────────────

    def validation_backlog(self) -> List[FailureMode]:
        """
        Return safety-related modes that have no confirmed evidence,
        ranked by their uncovered λ contribution (highest risk first).
        """
        return sorted(
            [m for m in self.modes if m.is_safety_related and not m.is_validated],
            key=lambda m: m.lambda_undetected(False),
            reverse=True,
        )

    # ── Lambda breakdown (ISO 26262-5 terminology) ───────────────────────────

    def lambda_breakdown(self, validated_only: bool = False) -> Dict[str, float]:
        """
        Return detailed failure rate breakdown, exactly matching the source
        worksheet's ISO 26262-5 classification:

            lambdaSPF     = Σλspf      : single-point faults, DC = 0 (no SM at all)
            lambdaRF      = Σλrf       : residual faults, uncovered portion of a
                                          safety-related mode that HAS a safety
                                          mechanism (0 < DC < 100%) → λ×(1−DC)
            lambdaMPF_det = ΣλmpfD     : latent (multi-point) faults, DETECTED
                                          portion → λ×DC   (dual-point detected)
            lambdaMPF_L   = Σλmpfl     : latent (multi-point) faults, UNDETECTED
                                          portion → λ×(1−DC)  (dual-point latent)
            lambda_total  = Σ(BFR)     : total safety-related failure rate (λ)

        Classification logic per mode:
            not safety_related        → excluded (goes to λs, safe faults)
            safety_related + latent   → split into λMPF,det and λMPF,latent
            safety_related + !latent  → DC==0 : λSPF   (pure single-point fault)
                                         DC>0  : λRF    (residual fault, λ×(1−DC))

        Used in:
            SPFM = (1 − (Σλ_SPF + Σλ_RF) / Σλ_total) × 100
            LFM  = (1 − Σλ_MPF,L / (Σλ_total − Σλ_SPF − Σλ_RF)) × 100
            PMHF = Σλ_SPF + Σλ_RF  [+ Σλ_MPF,det×Σλ_MPF,latent×T_lifetime if full]
        """
        spf_completely_uncov = 0.0   # λSPF
        spf_residual_uncov   = 0.0   # λRF
        mpf_detected         = 0.0   # λMPF,det
        mpf_latent           = 0.0   # λMPF,L

        for m in self.modes:
            if not m.is_safety_related:
                continue

            dc = m.effective_dc(validated_only)

            if m.is_latent:
                mpf_detected += m.lambda_fit * dc
                mpf_latent   += m.lambda_fit * (1.0 - dc)
            else:
                # Non-latent, safety-related: pure SPF (no SM) vs residual (SM exists)
                if dc == 0.0:
                    spf_completely_uncov += m.lambda_fit
                else:
                    spf_residual_uncov += m.lambda_fit * (1.0 - dc)

        return {
            "lambdaSPF"          : spf_completely_uncov,
            "lambdaRF"           : spf_residual_uncov,
            "lambdaMPF_det"      : mpf_detected,
            "lambdaMPF_L"        : mpf_latent,
            "lambda_total"       : self.lambda_dangerous_total,
            "lambda_spf_rf_total": spf_completely_uncov + spf_residual_uncov,
        }

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "modes": [m.to_dict() for m in self.modes]}

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FMEDA":
        fmeda = cls(name=data["name"])
        for md in data.get("modes", []):
            ev = None
            if md.get("evidence"):
                ed = md["evidence"]
                ev = Evidence(
                    test_id      = ed["test_id"],
                    status       = EvidenceStatus(ed.get("status", "estimated")),
                    validated_dc = ed.get("validated_dc"),
                    test_date    = date.fromisoformat(ed["test_date"]) if ed.get("test_date") else None,
                    notes        = ed.get("notes", ""),
                )
            fmeda.add(FailureMode(
                name              = md["name"],
                component         = md["component"],
                lambda_fit        = float(md["lambda_fit"]),
                dc                = float(md.get("dc", 0)),
                is_safety_related = bool(md.get("is_safety_related", True)),
                is_latent         = bool(md.get("is_latent", False)),
                evidence          = ev,
                safety_mechanism  = md.get("safety_mechanism", ""),
                lambda_source     = md.get("lambda_source", ""),
            ))
        return fmeda

    @classmethod
    def from_json(cls, json_str: str) -> "FMEDA":
        return cls.from_dict(json.loads(json_str))

    def to_csv(self, path: str) -> None:
        """Export FMEDA table to CSV."""
        fieldnames = [
            "name", "component", "lambda_fit", "dc",
            "is_safety_related", "is_latent",
            "lambda_undetected_planning", "lambda_undetected_validated",
            "evidence_status", "test_id", "validated_dc",
            "safety_mechanism", "lambda_source",
        ]
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for m in self.modes:
                w.writerow({
                    "name"                        : m.name,
                    "component"                   : m.component,
                    "lambda_fit"                  : m.lambda_fit,
                    "dc"                          : m.dc,
                    "is_safety_related"           : m.is_safety_related,
                    "is_latent"                   : m.is_latent,
                    "lambda_undetected_planning"  : round(m.lambda_undetected(False), 4),
                    "lambda_undetected_validated" : round(m.lambda_undetected(True), 4),
                    "evidence_status"             : m.evidence_status.value,
                    "test_id"  : m.evidence.test_id if m.evidence else "",
                    "validated_dc": m.evidence.validated_dc if m.evidence else "",
                    "safety_mechanism": m.safety_mechanism,
                    "lambda_source"   : m.lambda_source,
                })


# ── ASIL targets ──────────────────────────────────────────────────────────────

ASIL_TARGETS: Dict[str, Dict[str, Any]] = {
    "A": {"spfm": None, "lfm": None, "pmhf_fit": 1000.0},
    "B": {"spfm": 0.90, "lfm": 0.60, "pmhf_fit":  100.0},
    "C": {"spfm": 0.97, "lfm": 0.80, "pmhf_fit":   10.0},
    "D": {"spfm": 0.99, "lfm": 0.90, "pmhf_fit":    1.0},
}


# ── Evaluate + report ─────────────────────────────────────────────────────────

def evaluate(
    fmeda: FMEDA,
    asil: str,
    validated_only: bool = False,
) -> Dict[str, Any]:
    """
    Compute metrics and pass/fail against ASIL targets.

    Returns
    -------
    dict with keys: spfm, lfm, pmhf_fit, pmhf_per_hour,
                    spfm_pass, lfm_pass, pmhf_pass
    """
    t = ASIL_TARGETS[asil]
    sp = fmeda.spfm(validated_only)
    lf = fmeda.lfm(validated_only)
    pm = fmeda.pmhf(validated_only)

    return {
        "spfm"         : sp,
        "lfm"          : lf,
        "pmhf_fit"     : pm,
        "pmhf_per_hour": pm * 1e-9,
        "spfm_pass"    : (t["spfm"] is None) or (sp >= t["spfm"]),
        "lfm_pass"     : (t["lfm"]  is None) or (lf >= t["lfm"]),
        "pmhf_pass"    : pm <= t["pmhf_fit"],
    }


def report(fmeda: FMEDA, asil: str) -> None:
    """Print a full FMEDA report with planning, validated, and debt views."""

    def mark(ok: bool) -> str:
        return "✅ PASS" if ok else "❌ FAIL"

    sep  = "=" * 68
    sep2 = "-" * 68

    print(f"\n{sep}")
    print(f"  FMEDA Report : {fmeda.name}")
    print(f"  ASIL Target  : {asil}")
    print(sep)

    # ── Failure rate summary ──────────────────────────────────────────────────
    print(f"\n  Failure Rate Summary (ISO 26262-5 Terminology)")
    print(f"  {sep2}")
    print(f"  {'Total safety-related λ':<35} {fmeda.lambda_total:>8.2f} FIT")
    print(f"  {'λ Safe (excluded)':<35} {fmeda.lambda_safe:>8.2f} FIT")
    print(f"  {'λ Dangerous (total)':<35} {fmeda.lambda_dangerous_total:>8.2f} FIT")
    
    # ISO 26262-5 lambda breakdown (Planning mode)
    bd_plan = fmeda.lambda_breakdown(validated_only=False)
    print(f"\n  Planning Mode (Estimated DC):")
    print(f"  {'  λ_SPF  (no SM at all, DC=0)':<35} {bd_plan['lambdaSPF']:>8.3f} FIT")
    print(f"  {'  λ_RF   (SM exists, uncovered %)':<35} {bd_plan['lambdaRF']:>8.3f} FIT")
    print(f"  {'  λ_SPF + λ_RF (total SPF+RF)':<35} {bd_plan['lambda_spf_rf_total']:>8.3f} FIT")
    print(f"  {'  λ_MPF,det (latent, detected)':<35} {bd_plan['lambdaMPF_det']:>8.3f} FIT")
    print(f"  {'  λ_MPF,L (latent, undetected)':<35} {bd_plan['lambdaMPF_L']:>8.3f} FIT")

    # ISO 26262-5 lambda breakdown (Validated mode)
    bd_valid = fmeda.lambda_breakdown(validated_only=True)
    print(f"\n  Validated Mode (Test-Proven DC Only):")
    print(f"  {'  λ_SPF  (no SM at all, DC=0)':<35} {bd_valid['lambdaSPF']:>8.3f} FIT")
    print(f"  {'  λ_RF   (SM exists, uncovered %)':<35} {bd_valid['lambdaRF']:>8.3f} FIT")
    print(f"  {'  λ_SPF + λ_RF (total SPF+RF)':<35} {bd_valid['lambda_spf_rf_total']:>8.3f} FIT")
    print(f"  {'  λ_MPF,det (latent, detected)':<35} {bd_valid['lambdaMPF_det']:>8.3f} FIT")
    print(f"  {'  λ_MPF,L (latent, undetected)':<35} {bd_valid['lambdaMPF_L']:>8.3f} FIT")

    # ── Metrics: Planning vs Validated ───────────────────────────────────────
    t = ASIL_TARGETS[asil]

    def fmt_target(key: str) -> str:
        v = t[key]
        if v is None:
            return "  n/a  "
        if key == "pmhf_fit":
            return f"≤{v:.0f} FIT"
        return f"≥{v:.0%}"

    rp = evaluate(fmeda, asil, validated_only=False)
    rv = evaluate(fmeda, asil, validated_only=True)

    print(f"\n  ISO 26262-5 Metrics (§5.4.3)")
    print(f"  {sep2}")
    print(f"  Metric                        Planning      Validated     Target        Result")
    print(f"  {sep2}")
    print(f"  {'SPFM = (1−(λ_SPF+λ_RF)/λ)×100':<28} {rp['spfm']:>8.2%}      {rv['spfm']:>8.2%}      "
          f"{fmt_target('spfm'):>10}    {mark(rv['spfm_pass'])}")
    print(f"  {'LFM = (1−λ_MPF,L/(λ−λ_SPF−λ_RF))×100':<28} {rp['lfm']:>8.2%}      {rv['lfm']:>8.2%}      "
          f"{fmt_target('lfm'):>10}    {mark(rv['lfm_pass'])}")
    print(f"  {'PMHF = λ_SPF + λ_RF  (simplified)':<28} {rp['pmhf_fit']:>7.3f} FIT   {rv['pmhf_fit']:>7.3f} FIT   "
          f"{fmt_target('pmhf_fit'):>10}    {mark(rv['pmhf_pass'])}")

    # ── Validation debt ───────────────────────────────────────────────────────
    debt = fmeda.validation_debt()
    print(f"\n  Validation Debt")
    print(f"  {sep2}")
    print(f"  Unvalidated modes              : {debt['unvalidated_modes']}")
    print(f"  Uncovered FIT from unvalidated : {debt['unvalidated_fit']:.3f} FIT")
    print(f"  SPFM debt (plan − validated)   : {debt['spfm_debt']:+.4f}")
    print(f"  LFM  debt (plan − validated)   : {debt['lfm_debt']:+.4f}")
    print(f"  PMHF debt (valid − plan)       : {debt['pmhf_debt']:+.4f} FIT")

    if debt["unvalidated_modes"] == 0:
        print(f"\n  ✅ All DC values validated — validation debt = 0")
    else:
        print(f"\n  ⚠️  Validation debt > 0: safety case closure BLOCKED")
        print(f"     Run fault-injection tests for unvalidated modes below.")

    # ── Validation backlog ────────────────────────────────────────────────────
    backlog = fmeda.validation_backlog()
    if backlog:
        print(f"\n  Validation Backlog (ranked by uncovered FIT risk)")
        print(f"  {sep2}")
        print(f"  {'#':<3} {'Failure Mode':<30} {'Component':<18} "
              f"{'λ uncov':>8}  {'DC est':>7}  {'Status':<12}")
        for i, m in enumerate(backlog, 1):
            print(f"  {i:<3} {m.name:<30} {m.component:<18} "
                  f"{m.lambda_undetected(False):>8.3f}  "
                  f"{m.dc:>7.0%}  {m.evidence_status.value:<12}")

    # ── Worst contributors ────────────────────────────────────────────────────
    worst = fmeda.worst_contributors(n=5)
    print(f"\n  Top-5 Worst Contributors (by uncovered FIT — planning mode)")
    print(f"  {sep2}")
    print(f"  {'#':<3} {'Failure Mode':<30} {'λ uncov':>9}  {'DC':>6}  {'Latent?'}")
    for i, m in enumerate(worst, 1):
        print(f"  {i:<3} {m.name:<30} "
              f"{m.lambda_undetected(False):>9.3f}  "
              f"{m.dc:>6.0%}  "
              f"{'Yes' if m.is_latent else 'No'}")

    print(f"\n{sep}\n")
