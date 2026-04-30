from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass
class BaseEdge:
    """Directed relationship between two node ids with a type discriminator."""

    source: str
    target: str
    type: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the edge as a JSON-compatible dictionary.

        Returns:
            Flat mapping with ``source``, ``target``, and ``type`` keys.
        """
        return asdict(self)
