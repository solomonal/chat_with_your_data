---
name: mathematics
description: Help reason about mathematical concepts and use calculator tools for numeric results.
---

# Mathematics

## Purpose
Explain mathematical ideas and solve problems while distinguishing reasoning from exact computation.

## When to use
Use for mathematical concepts, equations, proofs, and applied quantitative questions. Use calculator tools when a numeric computation is required.

## Instructions
State assumptions, show a clear solution path, and verify units. Delegate arithmetic to the corresponding calculator tool when practical; do not claim a calculation was performed unless a tool returned it.

## Available tools
`calculator_evaluate_expression` and the arithmetic tools listed in the Calculator skill.

## Required input
Use the values and constraints supplied by the user. Ask for clarification when key values or units are missing.

## Expected output
A concise explanation, steps when useful, and a final result with units.

## Error handling
Identify inconsistent assumptions or invalid operations. Do not silently substitute values.

## Example
For “What is 25 multiplied by 45?”, call `calculator_multiply(a=25, b=45)` and report the returned result.
