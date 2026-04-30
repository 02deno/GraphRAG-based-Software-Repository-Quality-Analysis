from __future__ import annotations

from dataclasses import dataclass, field

from ..base_node import BaseNode


@dataclass
class ClassNode(BaseNode):
    name: str
    qualified_name: str
    file_path: str
    type: str = field(init=False, default="Class")

    def __init__(self, id: str, name: str, qualified_name: str, file_path: str) -> None:
        super().__init__(id=id, type="Class")
        self.name = name
        self.qualified_name = qualified_name
        self.file_path = file_path
