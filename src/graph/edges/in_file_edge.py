from __future__ import annotations

from dataclasses import dataclass, field

from ..base_edge import BaseEdge


@dataclass
class InFileEdge(BaseEdge):
    """Directed edge: symbol (function/class) is defined inside *target* file."""

    type: str = field(init=False, default="IN_FILE")

    def __init__(self, source: str, target: str) -> None:
        """Create an IN_FILE edge from symbol *source* id to containing file *target* id."""
        super().__init__(source=source, target=target, type="IN_FILE")
