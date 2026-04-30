from __future__ import annotations

import ast
from pathlib import Path
from typing import Set


def extract_imports(file_path: Path) -> Set[str]:
    """Collect top-level ``import`` / ``from`` module names from a Python file.

    Walks the AST and records ``Import`` names and ``ImportFrom`` package roots.
    Dynamic or failed parses yield an empty set.

    Args:
        file_path: Path to a ``.py`` file under the repository.

    Returns:
        Set of dotted or simple module strings referenced by static imports.
    """
    imports: Set[str] = set()
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports
