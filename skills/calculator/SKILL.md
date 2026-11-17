---
name: calculator
description: Use registered calculator tools for exact arithmetic, percentages, powers, and square roots.
---

# Calculator

## Purpose
Perform numeric calculations with the registered calculator tools instead of estimating.

## When to use
Use for arithmetic, totals, percentages, tax, powers, square roots, and safe arithmetic expressions. Do not call a tool for conceptual math questions that require no calculation.

## Instructions
1. Select the smallest relevant calculator tool.
2. For multi-step problems, call tools for each step and keep the intermediate values explicit.
3. Use `calculator_evaluate_expression` only for arithmetic expressions, not arbitrary code.
4. Explain the result and units in a concise natural-language response.
5. Never invent or alter a tool result.

## Available tools
`calculator_add`, `calculator_subtract`, `calculator_multiply`, `calculator_divide`, `calculator_percentage`, `calculator_power`, `calculator_square_root`, `calculator_evaluate_expression`.

## Required input
Each operation accepts its named numeric inputs. The expression tool requires an `expression` string.

## Expected output
Tools return structured JSON with a result and, where useful, calculation steps.

## Error handling
Division by zero, negative square roots, unsupported expressions, and invalid inputs return explicit tool errors. Explain the issue and ask for corrected input when needed.

## Example
For 8.5% tax on $200, calculate `percentage(value=200, percent=8.5)`, then add that result to 200. Report the subtotal, tax, and total.
