from __future__ import annotations

from dataclasses import dataclass, field

from ..base_edge import BaseEdge


@dataclass
class CallsEdge(BaseEdge):
    """Directed edge: caller to callee (reserved for call-graph extraction)."""

    type: str = field(init=False, default="CALLS")

    def __init__(self, source: str, target: str) -> None:
        """Create a CALLS edge from *source* to *target* node ids."""
        super().__init__(source=source, target=target, type="CALLS")
