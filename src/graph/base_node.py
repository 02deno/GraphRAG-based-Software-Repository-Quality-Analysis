from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass
class BaseNode:
    id: str
    type: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the node as a JSON-compatible dictionary."""
        return asdict(self)
