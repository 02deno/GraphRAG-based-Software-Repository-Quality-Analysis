from __future__ import annotations

from dataclasses import dataclass, field

from ..base_node import BaseNode


@dataclass
class CommitNode(BaseNode):
    hash: str
    author: str
    date: str
    message: str
    type: str = field(init=False, default="Commit")

    def __init__(
        self,
        id: str,
        hash: str,
        author: str,
        date: str,
        message: str,
    ) -> None:
        super().__init__(id=id, type="Commit")
        self.hash = hash
        self.author = author
        self.date = date
        self.message = message
