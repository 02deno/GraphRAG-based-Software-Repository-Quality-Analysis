from __future__ import annotations

from dataclasses import dataclass, field

from ..base_edge import BaseEdge


@dataclass
class ModifiedByEdge(BaseEdge):
    """Directed edge: commit or actor modified an artifact (future VCS integration)."""

    type: str = field(init=False, default="MODIFIED_BY")

    def __init__(self, source: str, target: str) -> None:
        """Create a MODIFIED_BY edge from *source* to *target* node ids."""
        super().__init__(source=source, target=target, type="MODIFIED_BY")
