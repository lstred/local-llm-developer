"""Anti-lazy detection + test/lint/type-check pipeline."""

from .anti_lazy import AntiLazyDetector, Finding
from .runners import CommandResult, VerificationReport, VerificationRunner

__all__ = [
    "AntiLazyDetector",
    "Finding",
    "VerificationRunner",
    "VerificationReport",
    "CommandResult",
]
