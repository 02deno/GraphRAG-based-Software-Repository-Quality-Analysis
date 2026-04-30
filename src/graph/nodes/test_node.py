from __future__ import annotations

from dataclasses import dataclass, field

from ..base_node import BaseNode


@dataclass
class TestNode(BaseNode):
    name: str
    file_path: str
    target_hint: str
    type: str = field(init=False, default="Test")

    def __init__(self, id: str, name: str, file_path: str, target_hint: str) -> None:
        super().__init__(id=id, type="Test")
        self.name = name
        self.file_path = file_path
        self.target_hint = target_hint
