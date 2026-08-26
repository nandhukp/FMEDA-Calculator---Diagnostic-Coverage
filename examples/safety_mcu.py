"""
Example: Generic Safety MCU — mirrors the original example from the program.
Demonstrates the minimal input needed to produce SPFM/LFM/PMHF.

Author: Nandakumar Palani
"""

from fmeda import FMEDA, FailureMode, Evidence, EvidenceStatus, report

f = FMEDA("Example Safety MCU")

f.add(FailureMode(
    name             = "CPU compute error",
    component        = "MCU core",
    lambda_fit       = 18.0,
    dc               = 0.99,
    safety_mechanism = "Hardware lockstep comparator",
    lambda_source    = "SN 29500 MCU category",
    evidence         = Evidence("TC-CPU-01", EvidenceStatus.VALIDATED, 0.99),
))

f.add(FailureMode(
    name             = "RAM bit error",
    component        = "MCU RAM",
    lambda_fit       = 12.0,
    dc               = 0.97,
    safety_mechanism = "SECDED ECC on all SRAM",
    lambda_source    = "SN 29500 SRAM category",
    evidence         = Evidence("TC-MEM-01", EvidenceStatus.VALIDATED, 0.97),
))

f.add(FailureMode(
    name             = "Program hang",
    component        = "MCU",
    lambda_fit       = 6.0,
    dc               = 0.99,
    safety_mechanism = "Hardware watchdog timer",
    lambda_source    = "SN 29500 SW hang category",
    evidence         = Evidence("TC-WD-01", EvidenceStatus.ESTIMATED),  # not yet tested
))

f.add(FailureMode(
    name              = "Status LED fault",
    component         = "Board",
    lambda_fit        = 5.0,
    is_safety_related = False,
    lambda_source     = "IEC TR 62380 board-level",
))

f.add(FailureMode(
    name             = "Supervisor ERR pin stuck",
    component        = "PMIC",
    lambda_fit       = 3.0,
    dc               = 0.90,
    is_latent        = True,
    safety_mechanism = "Periodic BIST — startup ERR pin stimulus test",
    lambda_source    = "SN 29500 analog supervisor",
    evidence         = Evidence("TC-PMIC-01", EvidenceStatus.ESTIMATED),
))

if __name__ == "__main__":
    report(f, asil="D")
