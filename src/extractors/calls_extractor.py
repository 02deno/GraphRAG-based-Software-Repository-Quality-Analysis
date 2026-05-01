from __future__ import annotations

import ast
from typing import Dict, List


class CallCollector(ast.NodeVisitor):
    """AST visitor that records unresolved call sites from each caller function."""

    def __init__(self, module_name: str, function_ids_by_qualified: Dict[str, str]) -> None:
        self.module_name = module_name
        self.function_ids_by_qualified = function_ids_by_qualified
        self.scope_stack: List[str] = []
        self.call_sites: set[tuple[str, str]] = set()

    def _caller_qualified(self, func_name: str) -> str:
        scoped = ".".join(self.scope_stack + [func_name])
        return f"{self.module_name}.{scoped}" if self.module_name else scoped

    @staticmethod
    def _resolve_callee_name(node: ast.Call) -> str | None:
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Collect unresolved calls made inside each function body."""
        caller_qn = self._caller_qualified(node.name)
        caller_id = self.function_ids_by_qualified.get(caller_qn)
        if caller_id is None:
            self.scope_stack.append(node.name)
            self.generic_visit(node)
            self.scope_stack.pop()
            return

        self.scope_stack.append(node.name)
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            callee_name = self._resolve_callee_name(child)
            if not callee_name:
                continue
            self.call_sites.add((caller_id, callee_name))
        self.scope_stack.pop()

        # Keep walking for nested defs.
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)
