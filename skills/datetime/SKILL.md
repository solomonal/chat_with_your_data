---
name: datetime
description: Retrieve the current date and time or calculate the difference between dates.
---

# Date and Time

## Purpose
Provide accurate current local date/time information and date differences using registered tools.

## When to use
Use when the user asks for the current date or time, timezone-aware local datetime, or elapsed calendar days between ISO dates.

## Instructions
Use the matching tool rather than relying on model knowledge for current values. Dates must be passed as `YYYY-MM-DD`.

## Available tools
`get_current_datetime`, `get_current_date`, `get_current_time`, `calculate_date_difference`.

## Required input
The date difference tool requires `start_date` and `end_date` in ISO format.

## Expected output
Return the tool's date/time or signed day difference and state the interpretation clearly.

## Error handling
If date input is invalid, report the ISO format requirement and request correction.

## Example
Call `calculate_date_difference(start_date="2026-01-01", end_date="2026-01-10")` to get the signed day difference.
