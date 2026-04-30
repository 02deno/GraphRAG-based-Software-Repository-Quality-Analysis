from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass
class BaseNode:
    """Minimal vertex record shared by all concrete node types."""

    id: str
    type: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the node as a JSON-compatible dictionary.

        Returns:
            Flat mapping suitable for ``graph_to_dict`` / JSON export.
        """
        return asdict(self)
