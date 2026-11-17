from __future__ import annotations

import ast
import builtins
from collections import Counter


class _NameCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.loaded: Counter[str] = Counter()
        self.stored: set[str] = set()
        self.mutable_defaults: list[int] = []
        self.bare_excepts: list[int] = []

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loaded[node.id] += 1
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            self.stored.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.stored.add(node.name)
        defaults = [*node.args.defaults, *node.args.kw_defaults]
        self.mutable_defaults.extend(
            item.lineno
            for item in defaults
            if isinstance(item, (ast.List, ast.Dict, ast.Set))
        )
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.bare_excepts.append(node.lineno)
        self.generic_visit(node)


def analyze_python_code(code: str, task: str = "analyze") -> dict[str, object]:
    if not code.strip():
        raise ValueError("Python code must not be empty.")
    if len(code) > 20_000:
        raise ValueError("Python code is limited to 20,000 characters.")
    if task not in {"analyze", "explain", "improve"}:
        raise ValueError("Task must be analyze, explain, or improve.")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "task": task,
            "valid": False,
            "syntax_error": {
                "message": exc.msg,
                "line": exc.lineno,
                "column": exc.offset,
            },
            "executed": False,
        }

    visitor = _NameCollector()
    visitor.visit(tree)
    warnings = [
        {
            "kind": "mutable_default",
            "line": line,
            "message": "Mutable default arguments are shared between function calls.",
        }
        for line in visitor.mutable_defaults
    ]
    warnings.extend(
        {
            "kind": "bare_except",
            "line": line,
            "message": "Bare except clauses can hide unexpected errors.",
        }
        for line in visitor.bare_excepts
    )
    builtin_names = set(dir(builtins))
    unused = sorted(
        name
        for name in visitor.stored - set(visitor.loaded) - builtin_names
        if not name.startswith("_")
    )
    return {
        "task": task,
        "valid": True,
        "line_count": len(code.splitlines()),
        "top_level_nodes": [type(node).__name__ for node in tree.body],
        "unused_names": unused,
        "warnings": warnings,
        "executed": False,
        "note": (
            "Static analysis only; user-provided code was parsed but never executed. "
            "Explain or improvement requests should be answered using the supplied source."
        ),
    }
