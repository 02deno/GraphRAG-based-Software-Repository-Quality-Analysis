"""Single compatibility check outcome (value object)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CheckItem:
    """Represents one weighted compatibility check result."""

    name: str
    description: str
    weight: float
    passed: bool
    score: float  # 0..1 quality for this criterion (not multiplied by weight)
    explanation: str = ""
    result_note: str = ""  # Per-repo outcome from the checker (why this score for this run)
