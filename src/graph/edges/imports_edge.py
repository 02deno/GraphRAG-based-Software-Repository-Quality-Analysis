from __future__ import annotations

from dataclasses import dataclass, field

from ..base_edge import BaseEdge


@dataclass
class ImportsEdge(BaseEdge):
    type: str = field(init=False, default="IMPORTS")

    def __init__(self, source: str, target: str) -> None:
        super().__init__(source=source, target=target, type="IMPORTS")
