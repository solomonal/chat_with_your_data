from __future__ import annotations

import pytest

from tools.calculator_tools import calculate, evaluate_expression


@pytest.mark.parametrize(
    ("operation", "arguments", "expected"),
    [
        ("add", {"a": 25, "b": 45}, 70),
        ("subtract", {"a": 100, "b": 25}, 75),
        ("multiply", {"a": 12, "b": 12}, 144),
        ("divide", {"a": 100, "b": 4}, 25),
        ("percentage", {"value": 200, "percent": 8.5}, 17),
    ],
)
def test_calculator_operations(
    operation: str, arguments: dict[str, int | float], expected: int | float
) -> None:
    assert calculate(operation, **arguments)["result"] == expected


def test_tax_calculation_example() -> None:
    tax = calculate("percentage", value=200, percent=8.5)["result"]
    assert calculate("add", a=200, b=tax)["result"] == 217


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("25 + 45", 70), ("(12 * 12) / 4", 36), ("2 ** 8", 256)],
)
def test_safe_expression(expression: str, expected: int | float) -> None:
    assert evaluate_expression(expression)["result"] == expected


@pytest.mark.parametrize(
    "expression",
    ["1 / 0", "open('secret')", "__import__('os').system('whoami')", "x + 1"],
)
def test_rejects_unsafe_or_invalid_expression(expression: str) -> None:
    with pytest.raises(ValueError):
        evaluate_expression(expression)
