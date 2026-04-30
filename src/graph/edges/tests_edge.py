from __future__ import annotations

from dataclasses import dataclass, field

from ..base_edge import BaseEdge


@dataclass
class TestsEdge(BaseEdge):
    """Directed edge: test *source* exercises or references *target* (file or symbol)."""

    type: str = field(init=False, default="TESTS")

    def __init__(self, source: str, target: str) -> None:
        """Create a TESTS edge from test node id to target node id."""
        super().__init__(source=source, target=target, type="TESTS")
