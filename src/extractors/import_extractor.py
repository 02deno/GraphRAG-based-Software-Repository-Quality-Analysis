from __future__ import annotations

import ast
from pathlib import Path
from typing import Set


def extract_imports(file_path: Path) -> Set[str]:
    """Extract imported module names from a Python file using AST."""
    imports: Set[str] = set()
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports
