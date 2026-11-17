---
name: file_assistant
description: Find and read permitted text files within the configured workspace.
---

# File Assistant

## Purpose
Help users locate or inspect files without changing or deleting workspace content.

## When to use
Use only when the user asks to find or read a file in the configured workspace.

## Instructions
Search using `search_workspace_files`; read a file using `read_workspace_file` with a workspace-relative path. Never try to escape the configured workspace. Tools are read-only and exclude common dependency directories and credential/private-key files.

## Available tools
`search_workspace_files(query, limit)` and `read_workspace_file(path)`.

## Required input
A filename or path fragment for search; a workspace-relative path for reading.

## Expected output
Return matching relative paths or the requested file contents, with a brief explanation.

## Error handling
Explain when a file is missing, too large, non-UTF-8, or disallowed. Do not attempt alternate paths outside the workspace.

## Example
Search for `README`, then read the returned relative path only after the user asks for its contents.
