---
name: data_analysis
description: Help users reason about data and identify appropriate safe analysis workflows.
---

# Data Analysis

## Purpose
Support data analysis requests while preserving the distinction between available tools and future integrations.

## When to use
Use when the user asks to summarize, compare, or interpret data supplied in chat or retrieved with the read-only workspace tools.

## Instructions
Analyze only data actually provided or retrieved. Describe assumptions and calculations. CSV/JSON-specific execution tools are not currently registered; do not claim to have parsed a file unless its contents were read and inspected. Ask the user to provide the data or select a readable workspace file.

## Available tools
`search_workspace_files` and `read_workspace_file` can locate and read permitted UTF-8 text files. No CSV, JSON, or database query tool is registered.

## Required input
The data itself or a workspace-relative path accessible to the file tools.

## Expected output
A traceable summary, relevant calculations, and explicit limitations.

## Error handling
Report missing, oversized, binary, or inaccessible files. Never fabricate rows, values, or statistics.

## Example
If asked to summarize a CSV, locate and read the permitted file first. If the file cannot be read, ask the user to paste a sample instead of implying it was analyzed.
