from __future__ import annotations

import ast
import math
import operator
from typing import Any


_BINARY_OPERATORS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_MAX_EXPRESSION_LENGTH = 512
_MAX_AST_NODES = 100
_MAX_EXPONENT = 1000


def _ensure_finite(value: int | float) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("The expression must evaluate to a number.")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise ValueError("The result is outside the supported numeric range.") from exc
    if not finite:
        raise ValueError("The result is outside the supported numeric range.")
    return value


def _evaluate_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return _ensure_finite(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate_node(node.operand)
        return _ensure_finite(value if isinstance(node.op, ast.UAdd) else -value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
            raise ValueError("Division by zero is not allowed.")
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError(f"Exponent magnitude must not exceed {_MAX_EXPONENT}.")
        try:
            return _ensure_finite(_BINARY_OPERATORS[type(node.op)](left, right))
        except (OverflowError, ZeroDivisionError) as exc:
            raise ValueError("The expression is outside the supported numeric range.") from exc
    raise ValueError("Only numeric literals and +, -, *, /, %, **, and parentheses are allowed.")


def evaluate_expression(expression: str) -> dict[str, object]:
    if not expression.strip():
        raise ValueError("Expression must not be empty.")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError(f"Expression must be {_MAX_EXPRESSION_LENGTH} characters or fewer.")
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid mathematical expression.") from exc
    if sum(1 for _ in ast.walk(parsed)) > _MAX_AST_NODES:
        raise ValueError("Expression is too complex.")
    result = _evaluate_node(parsed)
    return {"expression": expression, "result": result}


def calculate(operation: str, **values: int | float | str) -> dict[str, object]:
    if operation == "evaluate_expression":
        return evaluate_expression(str(values["expression"]))
    if operation == "add":
        a, b = values["a"], values["b"]
        result = a + b  # type: ignore[operator]
        steps = f"{a} + {b} = {result}"
    elif operation == "subtract":
        a, b = values["a"], values["b"]
        result = a - b  # type: ignore[operator]
        steps = f"{a} - {b} = {result}"
    elif operation == "multiply":
        a, b = values["a"], values["b"]
        result = a * b  # type: ignore[operator]
        steps = f"{a} × {b} = {result}"
    elif operation == "divide":
        a, b = values["a"], values["b"]
        if b == 0:
            raise ValueError("Division by zero is not allowed.")
        result = a / b  # type: ignore[operator]
        steps = f"{a} ÷ {b} = {result}"
    elif operation == "percentage":
        value, percent = values["value"], values["percent"]
        result = value * percent / 100  # type: ignore[operator]
        steps = f"{percent}% of {value} = {result}"
    elif operation == "power":
        base, exponent = values["base"], values["exponent"]
        if abs(exponent) > _MAX_EXPONENT:  # type: ignore[arg-type]
            raise ValueError(f"Exponent magnitude must not exceed {_MAX_EXPONENT}.")
        result = base**exponent  # type: ignore[operator]
        steps = f"{base} ** {exponent} = {result}"
    elif operation == "square_root":
        value = values["value"]
        if value < 0:  # type: ignore[operator]
            raise ValueError("Square root requires a non-negative value.")
        result = math.sqrt(value)  # type: ignore[arg-type]
        steps = f"√{value} = {result}"
    else:
        raise ValueError(f"Unsupported calculator operation: {operation}")
    result = _ensure_finite(result)  # type: ignore[arg-type]
    return {"operation": operation, "result": result, "steps": steps}
