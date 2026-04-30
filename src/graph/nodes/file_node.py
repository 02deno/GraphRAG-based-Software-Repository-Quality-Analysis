from __future__ import annotations

from dataclasses import dataclass, field

from ..base_node import BaseNode


@dataclass
class FileNode(BaseNode):
    path: str
    module: str
    language: str
    type: str = field(init=False, default="File")

    def __init__(self, id: str, path: str, module: str, language: str = "python") -> None:
        super().__init__(id=id, type="File")
        self.path = path
        self.module = module
        self.language = language
