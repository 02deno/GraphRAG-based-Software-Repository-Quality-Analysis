from __future__ import annotations

from dataclasses import dataclass, field

from ..base_edge import BaseEdge


@dataclass
class ModifiedByEdge(BaseEdge):
    type: str = field(init=False, default="MODIFIED_BY")

    def __init__(self, source: str, target: str) -> None:
        super().__init__(source=source, target=target, type="MODIFIED_BY")
