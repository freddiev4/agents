"""Model Context Protocol (MCP) client for loading external tool servers.

MCP allows external processes to expose tools that the agent can call,
extending the built-in tool set without modifying the agent code.

Configuration is via a JSON file (default: mcp.json) with the format:

    {
      "servers": {
        "my-server": {
          "command": "npx",
          "args": ["-y", "@example/mcp-server"],
          "env": {"SOME_KEY": "value"}
        }
      }
    }

Each server is a subprocess that speaks the MCP protocol over stdin/stdout.
This is a *simplified* implementation that covers the core flow:
  1. Launch the server process
  2. Send an "initialize" request
  3. Discover tools via "tools/list"
  4. Forward tool calls via "tools/call"
  5. Shut down cleanly
"""

import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from rune.harness.tools import ToolResult


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _jsonrpc_request(method: str, params: dict | None = None, req_id: str | None = None) -> str:
    """Build a JSON-RPC 2.0 request string."""
    msg: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "id": req_id or str(uuid.uuid4()),
    }
    if params is not None:
        msg["params"] = params
    return json.dumps(msg) + "\n"


# ---------------------------------------------------------------------------
# MCP Server handle
# ---------------------------------------------------------------------------

@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    server_name: str  # Which server provides it


@dataclass
class MCPServer:
    """Handle to a running MCP server process."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    process: subprocess.Popen | None = field(default=None, repr=False)
    tools: list[MCPTool] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _response_buf: dict[str, Any] = field(default_factory=dict, repr=False)

    def start(self) -> None:
        """Launch the server subprocess."""
        env = {**os.environ, **self.env}
        self.process = subprocess.Popen(
            [self.command] + self.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )
        # Start a reader thread
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()

    def _read_stdout(self) -> None:
        """Read JSON-RPC responses from stdout."""
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                msg_id = msg.get("id")
                if msg_id:
                    self._response_buf[msg_id] = msg
            except json.JSONDecodeError:
                continue

    def _send(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        """Send a JSON-RPC request and wait for the response."""
        assert self.process and self.process.stdin
        req_id = str(uuid.uuid4())
        payload = _jsonrpc_request(method, params, req_id)
        with self._lock:
            self.process.stdin.write(payload)
            self.process.stdin.flush()

        # Poll for response
        deadline = time.time() + timeout
        while time.time() < deadline:
            if req_id in self._response_buf:
                return self._response_buf.pop(req_id)
            time.sleep(0.05)
        raise TimeoutError(f"MCP server {self.name!r} did not respond to {method!r}")

    def initialize(self) -> None:
        """Send the MCP initialize handshake."""
        resp = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "rune", "version": "0.2.0"},
            "capabilities": {},
        })
        # Send initialized notification (no response expected)
        assert self.process and self.process.stdin
        notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        self.process.stdin.write(notif)
        self.process.stdin.flush()

    def discover_tools(self) -> list[MCPTool]:
        """Fetch the list of tools from the server."""
        resp = self._send("tools/list")
        result = resp.get("result", {})
        self.tools = []
        for t in result.get("tools", []):
            self.tools.append(MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("inputSchema", {"type": "object", "properties": {}}),
                server_name=self.name,
            ))
        return self.tools

    def call_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        """Call a tool on this server."""
        try:
            resp = self._send("tools/call", {"name": tool_name, "arguments": arguments})
            result = resp.get("result", {})
            # MCP returns content as an array of content blocks
            content_blocks = result.get("content", [])
            text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
            output = "\n".join(text_parts)
            is_error = result.get("isError", False)
            return ToolResult(success=not is_error, output=output, error=output if is_error else None)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def shutdown(self) -> None:
        """Gracefully shut down the server."""
        if self.process and self.process.poll() is None:
            try:
                self._send("shutdown", timeout=5)
            except (TimeoutError, BrokenPipeError):
                pass
            try:
                assert self.process.stdin
                notif = json.dumps({"jsonrpc": "2.0", "method": "exit"}) + "\n"
                self.process.stdin.write(notif)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


# ---------------------------------------------------------------------------
# MCP Manager — loads config, starts servers, routes tool calls
# ---------------------------------------------------------------------------

class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self):
        self.servers: dict[str, MCPServer] = {}
        self._tool_map: dict[str, MCPServer] = {}  # tool_name -> server

    def load_config(self, config_path: str) -> None:
        """Load MCP server configuration from a JSON file."""
        if not os.path.exists(config_path):
            return
        with open(config_path, "r") as f:
            config = json.load(f)
        for name, server_cfg in config.get("servers", {}).items():
            self.servers[name] = MCPServer(
                name=name,
                command=server_cfg["command"],
                args=server_cfg.get("args", []),
                env=server_cfg.get("env", {}),
            )

    def start_all(self) -> list[MCPTool]:
        """Start all configured servers and discover their tools."""
        all_tools: list[MCPTool] = []
        for name, server in self.servers.items():
            try:
                server.start()
                server.initialize()
                tools = server.discover_tools()
                for tool in tools:
                    self._tool_map[tool.name] = server
                all_tools.extend(tools)
            except Exception as e:
                print(f"[MCP] Failed to start server {name!r}: {e}")
        return all_tools

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tool_map

    def call_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        server = self._tool_map.get(tool_name)
        if not server:
            return ToolResult(success=False, output="", error=f"No MCP server provides tool {tool_name!r}")
        return server.call_tool(tool_name, arguments)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get OpenAI-format tool definitions for all MCP tools."""
        defs = []
        for server in self.servers.values():
            for tool in server.tools:
                defs.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                })
        return defs

    def shutdown_all(self) -> None:
        """Shut down all MCP servers."""
        for server in self.servers.values():
            server.shutdown()
