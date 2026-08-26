"""
fmeda — ISO 26262 FMEDA Calculator with Evidence Tracking
Author: Nandakumar Palani
"""

from .calculator import (
    FMEDA,
    FailureMode,
    Evidence,
    EvidenceStatus,
    FaultClass,
    ASIL_TARGETS,
    evaluate,
    report,
)

__version__ = "1.1.0"
__all__ = [
    "FMEDA",
    "FailureMode",
    "Evidence",
    "EvidenceStatus",
    "FaultClass",
    "ASIL_TARGETS",
    "evaluate",
    "report",
]
