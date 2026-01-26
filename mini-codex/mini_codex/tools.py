"""Tool definitions and execution for the coding agent."""

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

# Tool definitions for the OpenAI API
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Execute a shell command in the working directory. Use for running tests, installing packages, git operations, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read (relative to working directory)"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file at the given path. Creates the file if it doesn't exist, overwrites if it does.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write (relative to working directory)"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to list (relative to working directory, defaults to '.')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply a unified diff patch to modify a file. Use for making targeted edits to existing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to patch"
                    },
                    "patch": {
                        "type": "string",
                        "description": "The unified diff patch to apply"
                    }
                },
                "required": ["path", "patch"]
            }
        }
    }
]


@dataclass
class ToolResult:
    """Result of executing a tool."""
    success: bool
    output: str
    error: str | None = None


class ToolExecutor:
    """Executes tools in a sandboxed environment."""

    def __init__(self, working_dir: str, timeout: int = 30):
        self.working_dir = os.path.abspath(working_dir)
        self.timeout = timeout

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool with the given arguments."""
        handlers = {
            "shell": self._execute_shell,
            "read_file": self._execute_read_file,
            "write_file": self._execute_write_file,
            "list_files": self._execute_list_files,
            "apply_patch": self._execute_apply_patch,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}"
            )

        try:
            return handler(arguments)
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )

    def _resolve_path(self, path: str) -> str:
        """Resolve a path relative to the working directory."""
        resolved = os.path.normpath(os.path.join(self.working_dir, path))
        # Security: ensure path is within working directory
        if not resolved.startswith(self.working_dir):
            raise ValueError(f"Path {path} is outside working directory")
        return resolved

    def _execute_shell(self, args: dict[str, Any]) -> ToolResult:
        """Execute a shell command."""
        command = args.get("command", "")
        if not command:
            return ToolResult(success=False, output="", error="No command provided")

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"

            return ToolResult(
                success=result.returncode == 0,
                output=output.strip(),
                error=None if result.returncode == 0 else f"Exit code: {result.returncode}"
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {self.timeout}s"
            )

    def _execute_read_file(self, args: dict[str, Any]) -> ToolResult:
        """Read a file's contents."""
        path = args.get("path", "")
        if not path:
            return ToolResult(success=False, output="", error="No path provided")

        resolved = self._resolve_path(path)
        if not os.path.exists(resolved):
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        with open(resolved, "r") as f:
            content = f.read()

        return ToolResult(success=True, output=content)

    def _execute_write_file(self, args: dict[str, Any]) -> ToolResult:
        """Write content to a file."""
        path = args.get("path", "")
        content = args.get("content", "")

        if not path:
            return ToolResult(success=False, output="", error="No path provided")

        resolved = self._resolve_path(path)

        # Create parent directories if needed
        os.makedirs(os.path.dirname(resolved), exist_ok=True)

        with open(resolved, "w") as f:
            f.write(content)

        return ToolResult(success=True, output=f"Wrote {len(content)} bytes to {path}")

    def _execute_list_files(self, args: dict[str, Any]) -> ToolResult:
        """List files in a directory."""
        path = args.get("path", ".")
        resolved = self._resolve_path(path)

        if not os.path.exists(resolved):
            return ToolResult(success=False, output="", error=f"Path not found: {path}")

        if os.path.isfile(resolved):
            return ToolResult(success=True, output=path)

        entries = []
        for entry in sorted(os.listdir(resolved)):
            full_path = os.path.join(resolved, entry)
            if os.path.isdir(full_path):
                entries.append(f"{entry}/")
            else:
                entries.append(entry)

        return ToolResult(success=True, output="\n".join(entries))

    def _execute_apply_patch(self, args: dict[str, Any]) -> ToolResult:
        """Apply a unified diff patch to a file."""
        path = args.get("path", "")
        patch = args.get("patch", "")

        if not path:
            return ToolResult(success=False, output="", error="No path provided")
        if not patch:
            return ToolResult(success=False, output="", error="No patch provided")

        resolved = self._resolve_path(path)

        # Use patch command if available, otherwise fall back to simple replacement
        try:
            # Write patch to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
                f.write(patch)
                patch_file = f.name

            try:
                result = subprocess.run(
                    ["patch", resolved, patch_file],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )

                if result.returncode == 0:
                    return ToolResult(success=True, output=f"Patch applied to {path}")
                else:
                    return ToolResult(
                        success=False,
                        output=result.stdout,
                        error=result.stderr or f"Patch failed with exit code {result.returncode}"
                    )
            finally:
                os.unlink(patch_file)
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="patch command not found. Install patch utility or use write_file instead."
            )
