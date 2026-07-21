"""
FMEDA Calculator — Failure Mode Effects and Diagnostic Analysis
Computes ISO 26262 hardware architectural metrics: SPFM, LFM, PMHF.

Author: Nandakumar Palani

An FMEDA quantifies how well a design is protected against random hardware
faults. Each component has a failure rate (in FIT), and each failure mode is
classified by how it affects the safety goal and whether a diagnostic detects
it. From that, we compute the three ISO 26262 metrics.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class FaultClass(Enum):
    """How a failure mode relates to the safety goal."""
    SAFE = "safe"                 # cannot violate the safety goal
    SPF = "single_point"          # directly violates SG, no diagnostic
    RESIDUAL = "residual"         # part of a dangerous fault NOT covered by diagnostic
    MPF_DETECTED = "mpf_detected" # multi-point (latent) fault that IS detected
    MPF_LATENT = "mpf_latent"     # multi-point (latent) fault NOT detected


@dataclass
class FailureMode:
    """
    One failure mode of one component.

    lambda_fit      : failure rate of this mode, in FIT (failures per 1e9 hours)
    dc              : diagnostic coverage of this mode (0.0-1.0), i.e. the
                      fraction of this mode's failure rate that the safety
                      mechanism detects
    is_safety_related : does this mode relate to the safety goal at all?
    is_latent       : is this a multi-point (latent) fault contributor?
    """
    name: str
    component: str
    lambda_fit: float
    dc: float = 0.0
    is_safety_related: bool = True
    is_latent: bool = False

    def __post_init__(self):
        if not 0.0 <= self.dc <= 1.0:
            raise ValueError(f"{self.name}: dc must be 0..1, got {self.dc}")
        if self.lambda_fit < 0:
            raise ValueError(f"{self.name}: lambda_fit must be >= 0")

    # --- failure-rate split -------------------------------------------------
    @property
    def lambda_safe(self) -> float:
        """Rate of the non-safety-related (safe) portion."""
        return self.lambda_fit if not self.is_safety_related else 0.0

    @property
    def lambda_dangerous(self) -> float:
        """Rate of the safety-related (dangerous) portion."""
        return self.lambda_fit if self.is_safety_related else 0.0

    @property
    def lambda_detected(self) -> float:
        """Dangerous rate that the diagnostic detects."""
        return self.lambda_dangerous * self.dc

    @property
    def lambda_undetected(self) -> float:
        """Dangerous rate that escapes the diagnostic (residual/latent)."""
        return self.lambda_dangerous * (1.0 - self.dc)


@dataclass
class FMEDA:
    """A collection of failure modes for one item/element, with metric math."""
    name: str
    modes: List[FailureMode] = field(default_factory=list)

    def add(self, mode: FailureMode):
        self.modes.append(mode)

    # --- aggregate failure rates -------------------------------------------
    @property
    def lambda_total(self) -> float:
        return sum(m.lambda_fit for m in self.modes)

    @property
    def lambda_safe(self) -> float:
        return sum(m.lambda_safe for m in self.modes)

    @property
    def lambda_spf_residual(self) -> float:
        """
        Undetected dangerous single-point + residual faults.
        These are the faults that, on their own, can violate the safety goal
        and are NOT caught by a diagnostic.
        """
        return sum(m.lambda_undetected for m in self.modes if not m.is_latent)

    @property
    def lambda_latent_undetected(self) -> float:
        """Latent (multi-point) faults not detected."""
        return sum(m.lambda_undetected for m in self.modes if m.is_latent)

    @property
    def lambda_dangerous_total(self) -> float:
        return sum(m.lambda_dangerous for m in self.modes)

    @property
    def lambda_latent_total(self) -> float:
        return sum(m.lambda_dangerous for m in self.modes if m.is_latent)

    # --- the three ISO 26262 metrics ---------------------------------------
    @property
    def spfm(self) -> float:
        """
        Single Point Fault Metric.
        Fraction of dangerous failures that are NOT unprotected single-point
        or residual faults. Higher = safer.
            SPFM = 1 - (sum lambda_SPF+residual) / (sum lambda_dangerous)
        """
        d = self.lambda_dangerous_total
        if d == 0:
            return 1.0
        return 1.0 - (self.lambda_spf_residual / d)

    @property
    def lfm(self) -> float:
        """
        Latent Fault Metric.
        Fraction of latent faults that are detected (or safe).
            LFM = 1 - (sum lambda_latent_undetected) / (sum lambda_latent)
        """
        lat = self.lambda_latent_total
        if lat == 0:
            return 1.0
        return 1.0 - (self.lambda_latent_undetected / lat)

    @property
    def pmhf_fit(self) -> float:
        """
        Probabilistic Metric for random Hardware Failures, in FIT.
        Simplified: the residual + single-point dangerous undetected rate is
        the dominant contributor to violating the safety goal per hour.
        (Full PMHF adds a latent-times-exposure term; this is the primary term.)
        """
        return self.lambda_spf_residual

    @property
    def pmhf_per_hour(self) -> float:
        """PMHF expressed as probability per hour (FIT is per 1e9 hours)."""
        return self.pmhf_fit * 1e-9


# ISO 26262 targets per ASIL
ASIL_TARGETS = {
    "A": {"spfm": None,  "lfm": None,  "pmhf": 1e-6},
    "B": {"spfm": 0.90,  "lfm": 0.60,  "pmhf": 1e-7},
    "C": {"spfm": 0.97,  "lfm": 0.80,  "pmhf": 1e-7},
    "D": {"spfm": 0.99,  "lfm": 0.90,  "pmhf": 1e-8},
}


def evaluate(fmeda: FMEDA, asil: str) -> dict:
    """Compute metrics and pass/fail against the ASIL targets."""
    t = ASIL_TARGETS[asil]
    spfm, lfm, pmhf = fmeda.spfm, fmeda.lfm, fmeda.pmhf_per_hour
    return {
        "spfm": spfm,
        "lfm": lfm,
        "pmhf_per_hour": pmhf,
        "spfm_pass": (t["spfm"] is None) or (spfm >= t["spfm"]),
        "lfm_pass":  (t["lfm"]  is None) or (lfm  >= t["lfm"]),
        "pmhf_pass": pmhf <= t["pmhf"],
    }


def report(fmeda: FMEDA, asil: str):
    """Print a readable FMEDA summary."""
    r = evaluate(fmeda, asil)
    t = ASIL_TARGETS[asil]
    print(f"\n{'='*60}")
    print(f"FMEDA: {fmeda.name}   (target ASIL {asil})")
    print(f"{'='*60}")
    print(f"  Total failure rate      : {fmeda.lambda_total:8.2f} FIT")
    print(f"  Safe                    : {fmeda.lambda_safe:8.2f} FIT")
    print(f"  Dangerous (total)       : {fmeda.lambda_dangerous_total:8.2f} FIT")
    print(f"  SPF + residual (undet.) : {fmeda.lambda_spf_residual:8.2f} FIT")
    print(f"  Latent undetected       : {fmeda.lambda_latent_undetected:8.2f} FIT")
    print(f"  {'-'*50}")
    def mark(ok): return "PASS" if ok else "FAIL"
    tgt_spfm = "n/a" if t["spfm"] is None else f">={t['spfm']:.0%}"
    tgt_lfm  = "n/a" if t["lfm"]  is None else f">={t['lfm']:.0%}"
    print(f"  SPFM : {r['spfm']:7.2%}   target {tgt_spfm:>6}   {mark(r['spfm_pass'])}")
    print(f"  LFM  : {r['lfm']:7.2%}   target {tgt_lfm:>6}   {mark(r['lfm_pass'])}")
    print(f"  PMHF : {r['pmhf_per_hour']:.2e}/hr   target <={t['pmhf']:.0e}   {mark(r['pmhf_pass'])}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Example: a small compute-platform element (generic, no proprietary data)
    f = FMEDA("Example Safety MCU")

    # A CPU compute fault, well covered by lockstep (high DC)
    f.add(FailureMode("CPU compute error", "MCU core", lambda_fit=18.0, dc=0.99))
    # Memory fault covered by ECC
    f.add(FailureMode("RAM bit error", "MCU RAM", lambda_fit=12.0, dc=0.97))
    # A watchdog-covered software hang
    f.add(FailureMode("Program hang", "MCU", lambda_fit=6.0, dc=0.99))
    # A safe fault (does not affect the safety goal)
    f.add(FailureMode("Status LED fault", "Board", lambda_fit=5.0,
                      is_safety_related=False))
    # A latent fault: supervisor error-pin stuck, only detected by BIST
    f.add(FailureMode("Supervisor ERR pin stuck", "PMIC", lambda_fit=3.0,
                      dc=0.90, is_latent=True))

    report(f, asil="D")
