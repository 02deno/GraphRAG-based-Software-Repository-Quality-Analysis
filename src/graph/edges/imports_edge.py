from __future__ import annotations

from dataclasses import dataclass, field

from ..base_edge import BaseEdge


@dataclass
class ImportsEdge(BaseEdge):
    """Directed edge: source file imports target file (resolved module)."""

    type: str = field(init=False, default="IMPORTS")

    def __init__(self, source: str, target: str) -> None:
        """Create an IMPORTS edge from *source* file id to *target* file id."""
        super().__init__(source=source, target=target, type="IMPORTS")
