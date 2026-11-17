---
name: python_developer
description: Analyze, explain, and suggest improvements to Python source without executing it.
---

# Python Developer

## Purpose
Help users understand and improve Python code through non-executing static analysis and language reasoning.

## When to use
Use for requests to analyze or explain Python code, diagnose common syntax/structure issues, or suggest improvements.

## Instructions
Use `analyze_python_code` on code the user provides or explicitly asks you to read. The tool parses source but never executes it. Explain findings with accurate line references when available, and separate tool-detected warnings from recommendations.

## Available tools
`analyze_python_code(code, task)` where task is `analyze`, `explain`, or `improve`. Read-only workspace file tools may retrieve source from the configured workspace.

## Required input
Python source, limited to 20,000 characters, and an optional task.

## Expected output
Syntax validity, static findings, and a reasoned explanation or improvement suggestions.

## Error handling
Report parse errors and their locations. Do not run user code or claim runtime behavior was tested.

## Example
Call `analyze_python_code(code="def f(x=[]):\\n    return x", task="analyze")` and explain the mutable-default warning.
