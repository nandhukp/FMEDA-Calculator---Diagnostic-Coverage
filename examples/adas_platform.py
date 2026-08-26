"""
Example: Dual Compute SoC (ASIL B) + Safety MCU (ASIL D) + Companion SBC
Camera Pipeline: GMSL Deserializer + Camera Power Supervisor
Inter-SoC PCIe C2C link + Onboard IMU

This example uses generic component names. Failure rates are representative
values based on SN 29500 / IEC TR 62380 component categories — not tied to
any specific vendor or product.

Demonstrates:
  - Full failure mode definition with lambda sources
  - Evidence records: validated vs estimated vs in-review DC
  - Planning vs validated SPFM/LFM/PMHF comparison
  - Validation debt report and ranked backlog

Author: Nandakumar Palani
"""

from datetime import date
from fmeda import FMEDA, FailureMode, Evidence, EvidenceStatus, report

# ─────────────────────────────────────────────────────────────────────────────
# Component name mapping (generic)
# ─────────────────────────────────────────────────────────────────────────────
# COMPUTE_SOC        : ASIL B — runs perception, NDAS stack, FSI SafetyServices
# SAFETY_MCU         : ASIL D — hardware lockstep MCU; independent safety island
# COMPANION_SBC      : ASIL D — external window watchdog + voltage supervisor
# GMSL_DESER         : ASIL B (allocated) — GMSL2 camera deserializer
# CAM_PWR_SUPERVISOR : ASIL B (allocated) — camera channel power supervisor
# PCIe_C2C           : inter-SoC PCIe link (standard interface)
# IMU                : MEMS inertial measurement unit

COMPUTE_SOC        = "Compute SoC (ASIL B)"
SAFETY_MCU         = "Safety MCU (ASIL D)"
COMPANION_SBC      = "Companion SBC (ASIL D)"
GMSL_DESER         = "GMSL Deserializer"
CAM_PWR_SUPERVISOR = "Camera Power Supervisor"
PCIe_C2C           = "PCIe C2C Link"
IMU                = "MEMS IMU"

# ─────────────────────────────────────────────────────────────────────────────
# Build FMEDA
# ─────────────────────────────────────────────────────────────────────────────

f = FMEDA(
    "ADAS Safety Channel — Safety MCU (ASIL D) monitoring Compute SoC (ASIL B)"
    " with Companion SBC + Camera Pipeline"
)

# ── Block 1: Compute SoC (ASIL B, representative λ = 200 FIT) ───────────────

f.add(FailureMode(
    name              = "CPU lockstep mismatch",
    component         = COMPUTE_SOC,
    lambda_fit        = 15.0,
    dc                = 0.99,
    is_latent         = False,
    safety_mechanism  = "SOC_ERROR pin → Safety MCU GPIO IRQ",
    lambda_source     = "SoC supplier Safety Manual + SN 29500 complex ASIC",
    evidence          = Evidence(
        test_id      = "TC-SOC-01",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.99,
        test_date    = date(2024, 9, 12),
        notes        = "Lockstep fault injected via vendor fault injection API. "
                       "SOC_ERROR asserted < 1 ms. Safety MCU IRQ latency = 3 ms. "
                       "Safe state entered at T+18 ms — within FTTI/2 = 50 ms.",
    ),
))

f.add(FailureMode(
    name              = "DRAM ECC uncorrectable error (DUED)",
    component         = COMPUTE_SOC,
    lambda_fit        = 20.0,
    dc                = 0.97,
    is_latent         = False,
    safety_mechanism  = "SOC_ERROR pin + FSI fault register ECC bit",
    lambda_source     = "SN 29500 DRAM SECDED category + SoC datasheet",
    evidence          = Evidence(
        test_id      = "TC-SOC-02",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.97,
        test_date    = date(2024, 9, 14),
        notes        = "Double-bit injection via memory fault injector. "
                       "SOC_ERROR and FSI ECC bit both set. "
                       "3% residue accounts for multi-bit burst patterns.",
    ),
))

f.add(FailureMode(
    name              = "Perception SW hang — silent, no output",
    component         = COMPUTE_SOC,
    lambda_fit        = 25.0,
    dc                = 0.99,
    is_latent         = False,
    safety_mechanism  = "FSI heartbeat timeout (10 ms period, 20 ms Safety MCU timeout)",
    lambda_source     = "SN 29500 complex SoC SW fault category",
    evidence          = Evidence(
        test_id      = "TC-FSI-01",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.99,
        test_date    = date(2024, 10, 3),
        notes        = "Perception task suspended in OS. Safety MCU timeout fired "
                       "at T+20 ms. Safe state entered at T+22 ms. Pass.",
    ),
))

f.add(FailureMode(
    name              = "Thermal shutdown — no prior warning to Safety MCU",
    component         = COMPUTE_SOC,
    lambda_fit        = 18.0,
    dc                = 0.95,
    is_latent         = False,
    safety_mechanism  = "PMIC THERM_ALERT GPIO + Safety MCU I2C temperature poll (50 ms)",
    lambda_source     = "SN 29500 thermal fault category",
    evidence          = Evidence(
        test_id      = "TC-TMP-01",
        status       = EvidenceStatus.IN_REVIEW,
        validated_dc = None,
        test_date    = date(2024, 11, 5),
        notes        = "Thermal threshold lowered via PMIC register. "
                       "THERM_ALERT fired within 50 ms. Result under review — "
                       "pending sign-off on detection latency measurement.",
    ),
))

f.add(FailureMode(
    name              = "Clock domain fault — PLL unlock",
    component         = COMPUTE_SOC,
    lambda_fit        = 12.0,
    dc                = 0.98,
    is_latent         = False,
    safety_mechanism  = "SOC_ERROR pin (internal SoC PLL supervisor)",
    lambda_source     = "SN 29500 clock circuit category",
    evidence          = Evidence(
        test_id      = "TC-SOC-03",
        status       = EvidenceStatus.ESTIMATED,
        validated_dc = None,
        notes        = "Planned Q1 2025. Fault injection via vendor clock debug "
                       "interface. DC=0.98 is design estimate from SoC Safety Manual.",
    ),
))

f.add(FailureMode(
    name              = "Core voltage rail undervoltage (<5% sag)",
    component         = COMPUTE_SOC,
    lambda_fit        = 15.0,
    dc                = 0.99,
    is_latent         = False,
    safety_mechanism  = "PMIC UV interrupt + Safety MCU ADC — dual independent path",
    lambda_source     = "IEC TR 62380 power rail category",
    evidence          = Evidence(
        test_id      = "TC-VLT-01",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.99,
        test_date    = date(2024, 10, 18),
        notes        = "UV threshold lowered via PMIC programmable trim. "
                       "Both paths confirmed: PMIC HW < 1 ms, MCU ADC < 2 ms. "
                       "DTC raised correctly on both paths.",
    ),
))

f.add(FailureMode(
    name              = "Boot failure — IST_COMPLETE not received within timeout",
    component         = COMPUTE_SOC,
    lambda_fit        = 10.0,
    dc                = 0.97,
    is_latent         = True,
    safety_mechanism  = "Safety MCU FSM holds camera pipeline until IST_COMPLETE",
    lambda_source     = "SN 29500 boot sequence fault category",
    evidence          = Evidence(
        test_id      = "TC-BOOT-01",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.97,
        test_date    = date(2024, 10, 22),
        notes        = "SoC boot suspended at init stage. Safety MCU FSM held "
                       "pipeline. IST_COMPLETE withheld; camera remained gated.",
    ),
))

f.add(FailureMode(
    name              = "IOMMU / memory protection fault — silent, latent",
    component         = COMPUTE_SOC,
    lambda_fit        = 8.0,
    dc                = 0.90,
    is_latent         = True,
    safety_mechanism  = "FSI fault register IOMMU bit; Safety MCU polls every 20 ms",
    lambda_source     = "SN 29500 memory protection unit category",
    evidence          = Evidence(
        test_id      = "TC-FSI-02",
        status       = EvidenceStatus.ESTIMATED,
        validated_dc = None,
        notes        = "Planned Q1 2025. Force IOMMU fault via OS memory protection "
                       "debug interface.",
    ),
))

f.add(FailureMode(
    name              = "Safe / benign Compute SoC faults",
    component         = COMPUTE_SOC,
    lambda_fit        = 52.0,
    dc                = 0.0,
    is_safety_related = False,
    lambda_source     = "Residual λ after safety-relevant fault partition",
))

# ── Block 2: Safety MCU (ASIL D, representative λ = 50 FIT) ─────────────────

f.add(FailureMode(
    name              = "Safety MCU CPU lockstep mismatch",
    component         = SAFETY_MCU,
    lambda_fit        = 10.0,
    dc                = 0.99,
    is_latent         = False,
    safety_mechanism  = "Hardware lockstep comparator (native silicon, ASIL D MCU)",
    lambda_source     = "MCU supplier Safety Manual + SN 29500 lockstep MCU",
    evidence          = Evidence(
        test_id      = "TC-MCU-01",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.99,
        test_date    = date(2024, 9, 20),
        notes        = "Lockstep mismatch injected via JTAG debug port. "
                       "Comparator fired within 1 clock cycle. STL validated at boot.",
    ),
))

f.add(FailureMode(
    name              = "Safety MCU SW hang — watchdog not serviced",
    component         = SAFETY_MCU,
    lambda_fit        = 12.0,
    dc                = 0.99,
    is_latent         = False,
    safety_mechanism  = "Internal SMU watchdog + external Companion SBC window watchdog",
    lambda_source     = "SN 29500 MCU SW fault category",
    evidence          = Evidence(
        test_id      = "TC-MCU-02",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.99,
        test_date    = date(2024, 10, 8),
        notes        = "Safety task suspended. Companion SBC watchdog fired at "
                       "T+285 ms (within 400 ms window). ECU reset initiated.",
    ),
))

f.add(FailureMode(
    name              = "Safety MCU SPI communication error to Compute SoC",
    component         = SAFETY_MCU,
    lambda_fit        = 8.0,
    dc                = 0.95,
    is_latent         = True,
    safety_mechanism  = "SPI frame CRC + alive counter; E2E error after 3 failures",
    lambda_source     = "SN 29500 SPI interface category",
    evidence          = Evidence(
        test_id      = "TC-SPI-01",
        status       = EvidenceStatus.ESTIMATED,
        validated_dc = None,
        notes        = "Planned Q1 2025. SPI fault injector (bus analyser + "
                       "programmable fault insertion).",
    ),
))

f.add(FailureMode(
    name              = "Safe / benign Safety MCU faults",
    component         = SAFETY_MCU,
    lambda_fit        = 12.0,
    dc                = 0.0,
    is_safety_related = False,
    lambda_source     = "MCU supplier Safety Manual residual classification",
))

# ── Block 3: Companion SBC (ASIL D, representative λ = 25 FIT) ──────────────

f.add(FailureMode(
    name              = "Companion SBC watchdog not firing on Safety MCU hang",
    component         = COMPANION_SBC,
    lambda_fit        = 8.0,
    dc                = 0.99,
    is_latent         = False,
    safety_mechanism  = "SBC hardware window watchdog (independent oscillator, ASIL D)",
    lambda_source     = "SBC supplier Safety Manual + SN 29500 SBC category",
    evidence          = Evidence(
        test_id      = "TC-MCU-02",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.99,
        test_date    = date(2024, 10, 8),
        notes        = "Confirmed: SBC watchdog fired independently of Safety MCU SW.",
    ),
))

f.add(FailureMode(
    name              = "Companion SBC voltage monitor stuck — FAULT pin masked",
    component         = COMPANION_SBC,
    lambda_fit        = 7.0,
    dc                = 0.97,
    is_latent         = False,
    safety_mechanism  = "IST: Safety MCU forces test UV stimulus; SBC FAULT pin "
                        "response verified before pipeline enable",
    lambda_source     = "SN 29500 analog supervisor category",
    evidence          = Evidence(
        test_id      = "TC-VLT-02",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.97,
        test_date    = date(2024, 10, 20),
        notes        = "Test UV stimulus applied at IST. SBC FAULT pin responded "
                       "< 5 ms. Pipeline correctly blocked on non-response.",
    ),
))

# ── Block 4: Camera pipeline — GMSL Deserializer + Power Supervisor ──────────

f.add(FailureMode(
    name              = "GMSL link lock loss — silent (LOCK# stuck high)",
    component         = GMSL_DESER,
    lambda_fit        = 8.0,
    dc                = 0.92,
    is_latent         = False,
    safety_mechanism  = "ERRB error signal + SoC frame counter stall detection",
    lambda_source     = "SN 29500 high-speed serialiser / deserialiser category",
    evidence          = Evidence(
        test_id      = "TC-CAM-01",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.92,
        test_date    = date(2024, 11, 1),
        notes        = "Physical cable disconnect during streaming. ERRB asserted; "
                       "SoC frame stall detected in 33 ms (2 frame periods at 60 Hz).",
    ),
))

f.add(FailureMode(
    name              = "Pixel data corruption — no CRC coverage on image path",
    component         = GMSL_DESER,
    lambda_fit        = 15.0,
    dc                = 0.97,
    is_latent         = False,
    safety_mechanism  = "Rolling frame CRC on ISP output; CRC-valid flag to Safety MCU",
    lambda_source     = "SN 29500 high-speed data link category",
    evidence          = Evidence(
        test_id      = "TC-CAM-06",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.97,
        test_date    = date(2024, 11, 8),
        notes        = "1-bit DMA flip injected into ISP frame buffer. "
                       "Frame CRC checker detected within 16.6 ms (1 frame period).",
    ),
))

f.add(FailureMode(
    name              = "Camera power supervisor FAULT pin stuck high (masked)",
    component         = CAM_PWR_SUPERVISOR,
    lambda_fit        = 8.0,
    dc                = 0.97,
    is_latent         = False,
    safety_mechanism  = "IST: Safety MCU forces test over-current; "
                        "FAULT pin response verified before pipeline enable",
    lambda_source     = "SN 29500 analog power supervisor category",
    evidence          = Evidence(
        test_id      = "TC-CAM-09",
        status       = EvidenceStatus.ESTIMATED,
        validated_dc = None,
        notes        = "Test fixture for FAULT pin hold under development. "
                       "Planned Q1 2025.",
    ),
))

f.add(FailureMode(
    name              = "Deserializer GP fault signal output stuck",
    component         = GMSL_DESER,
    lambda_fit        = 10.0,
    dc                = 0.98,
    is_latent         = False,
    safety_mechanism  = "GPIO loopback self-test at boot (IST)",
    lambda_source     = "SN 29500 digital I/O category",
    evidence          = Evidence(
        test_id      = "TC-CAM-04",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.96,
        test_date    = date(2024, 11, 10),
        notes        = "GPIO stuck-low injected via pull-down fixture during IST. "
                       "Absence-of-signal watchdog fired correctly. "
                       "Note: validated DC = 96% vs estimated 98% — one corner case "
                       "missed (long-duration transient before stuck condition).",
    ),
))

# ── Block 5: PCIe C2C link + MEMS IMU ───────────────────────────────────────

f.add(FailureMode(
    name              = "PCIe C2C silent data corruption",
    component         = PCIe_C2C,
    lambda_fit        = 12.0,
    dc                = 0.99,
    is_latent         = False,
    safety_mechanism  = "E2E protection: CRC32 + sequence counter on every safety message",
    lambda_source     = "SN 29500 high-speed PCIe bus category",
    evidence          = Evidence(
        test_id      = "TC-PCIE-01",
        status       = EvidenceStatus.VALIDATED,
        validated_dc = 0.99,
        test_date    = date(2024, 11, 15),
        notes        = "64-case fault injection matrix completed. E2E detected all "
                       "single-bit and burst errors. Sequence replay rejected. Pass.",
    ),
))

f.add(FailureMode(
    name              = "IMU output slow drift — bias shift (latent)",
    component         = IMU,
    lambda_fit        = 5.0,
    dc                = 0.80,
    is_latent         = True,
    safety_mechanism  = "Odometry cross-check; dual IMU if available",
    lambda_source     = "SN 29500 MEMS inertial sensor category",
    evidence          = Evidence(
        test_id      = "TC-IMU-04",
        status       = EvidenceStatus.ESTIMATED,
        validated_dc = None,
        notes        = "DC=0.80 is conservative estimate without dual-IMU redundancy. "
                       "Cross-check algorithm under development. "
                       "Planned validation with odometry bench Q2 2025.",
    ),
))

# ─────────────────────────────────────────────────────────────────────────────
# Run reports
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "█" * 68)
    print("  ADAS Safety Channel FMEDA")
    print("  Safety MCU (ASIL D) monitoring Compute SoC (ASIL B)")
    print("  With Companion SBC | GMSL Camera Pipeline | PCIe C2C")
    print("█" * 68)

    report(f, asil="D")

    f.to_csv("adas_platform_fmeda.csv")
    with open("adas_platform_fmeda.json", "w") as fp:
        fp.write(f.to_json())

    print("  Exported: adas_platform_fmeda.csv")
    print("  Exported: adas_platform_fmeda.json\n")
