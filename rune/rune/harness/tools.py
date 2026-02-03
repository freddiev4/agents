"""Tool definitions and execution for the coding agent.

Provides 15 built-in tools for file operations, shell commands, and more:
  1. shell          - Execute shell commands
  2. read_file      - Read file contents (with optional line range)
  3. write_file     - Write/create files
  4. edit_file      - Search-and-replace editing
  5. multi_edit     - Multiple edits in a single call
  6. apply_patch    - Apply unified diff patches
  7. list_files     - List directory contents
  8. glob           - Fast file pattern matching
  9. grep           - Content search with regex
 10. tree           - Recursive directory tree view
 11. web_fetch      - Fetch URL content
 12. web_search     - Web search (placeholder, needs API key)
 13. task           - Spawn a subagent for a subtask
 14. todo           - Manage a structured task list
 15. notebook_edit  - Edit Jupyter notebook cells
"""

import fnmatch
import json
import os
import pathlib
import re
import subprocess
import tempfile
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Tool result
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Result of executing a tool."""
    success: bool
    output: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Todo state (shared mutable list used by the todo tool)
# ---------------------------------------------------------------------------

@dataclass
class TodoItem:
    content: str
    status: str = "pending"  # pending | in_progress | completed

    def to_dict(self) -> dict:
        return {"content": self.content, "status": self.status}


class TodoList:
    """Simple in-memory task list."""

    def __init__(self):
        self.items: list[TodoItem] = []

    def set(self, items: list[dict]) -> str:
        self.items = [TodoItem(content=i["content"], status=i.get("status", "pending")) for i in items]
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "(empty todo list)"
        lines = []
        for i, item in enumerate(self.items):
            marker = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}.get(item.status, "[ ]")
            lines.append(f"{i + 1}. {marker} {item.content}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# OpenAI-format tool definitions (15 tools)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Execute a shell command in the working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Supports optional offset and limit for large files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file (relative to working directory)"},
                    "offset": {"type": "integer", "description": "Line number to start reading from (1-based)"},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates parent directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Perform a search-and-replace edit on a file. old_string must match exactly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "old_string": {"type": "string", "description": "Exact text to find"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences (default false)"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "multi_edit",
            "description": "Apply multiple search-and-replace edits to a file in one call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_string": {"type": "string"},
                                "new_string": {"type": "string"},
                            },
                            "required": ["old_string", "new_string"],
                        },
                        "description": "List of {old_string, new_string} edits to apply sequentially",
                    },
                },
                "required": ["path", "edits"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply a unified diff patch to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to patch"},
                    "patch": {"type": "string", "description": "Unified diff patch content"},
                },
                "required": ["path", "patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to list (default '.')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern (e.g. '**/*.py').",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern"},
                    "path": {"type": "string", "description": "Base directory (default '.')"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents for a regex pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "File or directory to search in (default '.')"},
                    "include": {"type": "string", "description": "Glob to filter files (e.g. '*.py')"},
                    "context_lines": {"type": "integer", "description": "Lines of context around matches (default 0)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tree",
            "description": "Show a recursive directory tree view.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory (default '.')"},
                    "max_depth": {"type": "integer", "description": "Maximum depth (default 3)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch content from a URL and return it as text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for a query. Returns snippets and URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task",
            "description": "Spawn a subagent to handle a complex subtask autonomously. The subagent gets its own conversation context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Short description of the subtask (3-5 words)"},
                    "prompt": {"type": "string", "description": "Detailed instructions for the subagent"},
                },
                "required": ["description", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo",
            "description": "Manage a structured task list. Provide the full updated list each time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                            },
                            "required": ["content", "status"],
                        },
                        "description": "The full todo list",
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_edit",
            "description": "Replace the source of a cell in a Jupyter notebook (.ipynb).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the .ipynb file"},
                    "cell_index": {"type": "integer", "description": "0-based cell index"},
                    "new_source": {"type": "string", "description": "New source for the cell"},
                    "cell_type": {"type": "string", "enum": ["code", "markdown"], "description": "Cell type (default: keep existing)"},
                },
                "required": ["path", "cell_index", "new_source"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Executes tools in a sandboxed environment."""

    def __init__(
        self,
        working_dir: str,
        timeout: int = 30,
        todo_list: TodoList | None = None,
        subagent_callback=None,
    ):
        self.working_dir = os.path.abspath(working_dir)
        self.timeout = timeout
        self.todo_list = todo_list or TodoList()
        # Callback: (description, prompt) -> str.  Set by the Agent to enable
        # the "task" tool to spawn a child agent loop.
        self.subagent_callback = subagent_callback

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool with the given arguments."""
        handlers = {
            "shell": self._execute_shell,
            "read_file": self._execute_read_file,
            "write_file": self._execute_write_file,
            "edit_file": self._execute_edit_file,
            "multi_edit": self._execute_multi_edit,
            "apply_patch": self._execute_apply_patch,
            "list_files": self._execute_list_files,
            "glob": self._execute_glob,
            "grep": self._execute_grep,
            "tree": self._execute_tree,
            "web_fetch": self._execute_web_fetch,
            "web_search": self._execute_web_search,
            "task": self._execute_task,
            "todo": self._execute_todo,
            "notebook_edit": self._execute_notebook_edit,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return ToolResult(success=False, output="", error=f"Unknown tool: {tool_name}")

        try:
            return handler(arguments)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ----- path helpers -----

    def _resolve_path(self, path: str) -> str:
        resolved = os.path.normpath(os.path.join(self.working_dir, path))
        if not resolved.startswith(self.working_dir):
            raise ValueError(f"Path {path} is outside working directory")
        return resolved

    # ----- tool implementations -----

    def _execute_shell(self, args: dict[str, Any]) -> ToolResult:
        command = args.get("command", "")
        if not command:
            return ToolResult(success=False, output="", error="No command provided")
        timeout = args.get("timeout", self.timeout)
        try:
            result = subprocess.run(
                command, shell=True, cwd=self.working_dir,
                capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            return ToolResult(
                success=result.returncode == 0,
                output=output.strip(),
                error=None if result.returncode == 0 else f"Exit code: {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error=f"Command timed out after {timeout}s")

    def _execute_read_file(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        if not path:
            return ToolResult(success=False, output="", error="No path provided")
        resolved = self._resolve_path(path)
        if not os.path.exists(resolved):
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        with open(resolved, "r") as f:
            lines = f.readlines()
        offset = args.get("offset")
        limit = args.get("limit")
        if offset is not None:
            lines = lines[max(0, offset - 1):]
        if limit is not None:
            lines = lines[:limit]
        # Number lines
        start = max(1, (offset or 1))
        numbered = [f"{start + i:>6}\t{line.rstrip()}" for i, line in enumerate(lines)]
        return ToolResult(success=True, output="\n".join(numbered))

    def _execute_write_file(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        content = args.get("content", "")
        if not path:
            return ToolResult(success=False, output="", error="No path provided")
        resolved = self._resolve_path(path)
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, "w") as f:
            f.write(content)
        return ToolResult(success=True, output=f"Wrote {len(content)} bytes to {path}")

    def _execute_edit_file(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        if not path:
            return ToolResult(success=False, output="", error="No path provided")
        resolved = self._resolve_path(path)
        if not os.path.exists(resolved):
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        with open(resolved, "r") as f:
            content = f.read()
        if old_string not in content:
            return ToolResult(success=False, output="", error="old_string not found in file")
        if not replace_all and content.count(old_string) > 1:
            return ToolResult(
                success=False, output="",
                error=f"old_string found {content.count(old_string)} times; use replace_all or provide more context",
            )
        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        with open(resolved, "w") as f:
            f.write(new_content)
        return ToolResult(success=True, output=f"Edited {path}")

    def _execute_multi_edit(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        edits = args.get("edits", [])
        if not path:
            return ToolResult(success=False, output="", error="No path provided")
        resolved = self._resolve_path(path)
        if not os.path.exists(resolved):
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        with open(resolved, "r") as f:
            content = f.read()
        applied = 0
        for edit in edits:
            old = edit.get("old_string", "")
            new = edit.get("new_string", "")
            if old in content:
                content = content.replace(old, new, 1)
                applied += 1
        with open(resolved, "w") as f:
            f.write(content)
        return ToolResult(success=True, output=f"Applied {applied}/{len(edits)} edits to {path}")

    def _execute_apply_patch(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        patch = args.get("patch", "")
        if not path:
            return ToolResult(success=False, output="", error="No path provided")
        if not patch:
            return ToolResult(success=False, output="", error="No patch provided")
        resolved = self._resolve_path(path)
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
                f.write(patch)
                patch_file = f.name
            try:
                result = subprocess.run(
                    ["patch", resolved, patch_file],
                    capture_output=True, text=True, timeout=self.timeout,
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Patch applied to {path}")
                return ToolResult(success=False, output=result.stdout,
                                  error=result.stderr or f"Patch failed (exit {result.returncode})")
            finally:
                os.unlink(patch_file)
        except FileNotFoundError:
            return ToolResult(success=False, output="", error="patch command not found")

    def _execute_list_files(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", ".")
        resolved = self._resolve_path(path)
        if not os.path.exists(resolved):
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        if os.path.isfile(resolved):
            return ToolResult(success=True, output=path)
        entries = []
        for entry in sorted(os.listdir(resolved)):
            full = os.path.join(resolved, entry)
            entries.append(f"{entry}/" if os.path.isdir(full) else entry)
        return ToolResult(success=True, output="\n".join(entries))

    def _execute_glob(self, args: dict[str, Any]) -> ToolResult:
        pattern = args.get("pattern", "")
        base = args.get("path", ".")
        if not pattern:
            return ToolResult(success=False, output="", error="No pattern provided")
        resolved = self._resolve_path(base)
        matches = sorted(str(p.relative_to(resolved)) for p in pathlib.Path(resolved).glob(pattern))
        if not matches:
            return ToolResult(success=True, output="(no matches)")
        return ToolResult(success=True, output="\n".join(matches[:500]))

    def _execute_grep(self, args: dict[str, Any]) -> ToolResult:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        include = args.get("include")
        ctx = args.get("context_lines", 0)
        if not pattern:
            return ToolResult(success=False, output="", error="No pattern provided")
        resolved = self._resolve_path(path)
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(success=False, output="", error=f"Invalid regex: {e}")

        results: list[str] = []
        max_results = 200

        def _search_file(fpath: str, rel: str):
            try:
                with open(fpath, "r", errors="replace") as f:
                    lines = f.readlines()
            except (OSError, UnicodeDecodeError):
                return
            for i, line in enumerate(lines):
                if len(results) >= max_results:
                    return
                if regex.search(line):
                    start = max(0, i - ctx)
                    end = min(len(lines), i + ctx + 1)
                    for j in range(start, end):
                        marker = ">" if j == i else " "
                        results.append(f"{rel}:{j + 1}{marker} {lines[j].rstrip()}")

        if os.path.isfile(resolved):
            _search_file(resolved, path)
        else:
            for root, _dirs, files in os.walk(resolved):
                for fname in files:
                    if include and not fnmatch.fnmatch(fname, include):
                        continue
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, self.working_dir)
                    _search_file(fpath, rel)
                    if len(results) >= max_results:
                        break

        if not results:
            return ToolResult(success=True, output="(no matches)")
        output = "\n".join(results)
        if len(results) >= max_results:
            output += f"\n... (truncated at {max_results} results)"
        return ToolResult(success=True, output=output)

    def _execute_tree(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", ".")
        max_depth = args.get("max_depth", 3)
        resolved = self._resolve_path(path)
        if not os.path.exists(resolved):
            return ToolResult(success=False, output="", error=f"Path not found: {path}")

        lines: list[str] = []
        max_entries = 500

        def _walk(dir_path: str, prefix: str, depth: int):
            if depth > max_depth or len(lines) >= max_entries:
                return
            try:
                entries = sorted(os.listdir(dir_path))
            except PermissionError:
                return
            dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e)) and not e.startswith(".")]
            files = [e for e in entries if not os.path.isdir(os.path.join(dir_path, e)) and not e.startswith(".")]
            all_entries = dirs + files
            for i, entry in enumerate(all_entries):
                if len(lines) >= max_entries:
                    lines.append(f"{prefix}... (truncated)")
                    return
                is_last = i == len(all_entries) - 1
                connector = "└── " if is_last else "├── "
                full = os.path.join(dir_path, entry)
                suffix = "/" if os.path.isdir(full) else ""
                lines.append(f"{prefix}{connector}{entry}{suffix}")
                if os.path.isdir(full):
                    extension = "    " if is_last else "│   "
                    _walk(full, prefix + extension, depth + 1)

        lines.append(os.path.basename(resolved) + "/")
        _walk(resolved, "", 1)
        return ToolResult(success=True, output="\n".join(lines))

    def _execute_web_fetch(self, args: dict[str, Any]) -> ToolResult:
        url = args.get("url", "")
        if not url:
            return ToolResult(success=False, output="", error="No URL provided")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rune/0.2"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            # Truncate very large responses
            if len(body) > 50_000:
                body = body[:50_000] + "\n... (truncated)"
            return ToolResult(success=True, output=body)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _execute_web_search(self, args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(success=False, output="", error="No query provided")
        # This is a placeholder — a real implementation would call a search API.
        return ToolResult(
            success=False, output="",
            error="web_search requires a SEARCH_API_KEY environment variable. "
                  "Set it to use a search provider, or use web_fetch with a known URL.",
        )

    def _execute_task(self, args: dict[str, Any]) -> ToolResult:
        description = args.get("description", "")
        prompt = args.get("prompt", "")
        if not prompt:
            return ToolResult(success=False, output="", error="No prompt provided")
        if not self.subagent_callback:
            return ToolResult(success=False, output="", error="Subagent spawning not available")
        try:
            result = self.subagent_callback(description, prompt)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Subagent failed: {e}")

    def _execute_todo(self, args: dict[str, Any]) -> ToolResult:
        items = args.get("items", [])
        output = self.todo_list.set(items)
        return ToolResult(success=True, output=output)

    def _execute_notebook_edit(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        cell_index = args.get("cell_index")
        new_source = args.get("new_source", "")
        cell_type = args.get("cell_type")
        if not path:
            return ToolResult(success=False, output="", error="No path provided")
        if cell_index is None:
            return ToolResult(success=False, output="", error="No cell_index provided")
        resolved = self._resolve_path(path)
        if not os.path.exists(resolved):
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        with open(resolved, "r") as f:
            notebook = json.load(f)
        cells = notebook.get("cells", [])
        if cell_index < 0 or cell_index >= len(cells):
            return ToolResult(success=False, output="", error=f"cell_index {cell_index} out of range (0-{len(cells)-1})")
        cells[cell_index]["source"] = new_source.splitlines(True)
        if cell_type:
            cells[cell_index]["cell_type"] = cell_type
        with open(resolved, "w") as f:
            json.dump(notebook, f, indent=1)
        return ToolResult(success=True, output=f"Updated cell {cell_index} in {path}")
