"""Rune harness package.

Contains the core agent loop, session management, tool execution, permissions,
and MCP integration.

Note: this package intentionally does *not* import/re-export the core `Agent`
class to avoid circular imports with `rune.agents` (agent definitions).

Public API is re-exported from `rune.__init__` to preserve:

    from rune import Agent, AgentConfig

"""

from rune.harness.session import Session, Message, UsageStats
from rune.harness.permissions import PermissionLevel, PermissionSet
from rune.harness.tools import ToolExecutor, ToolResult
from rune.harness.mcp_client import MCPManager

__all__ = [
    "Session",
    "Message",
    "UsageStats",
    "PermissionLevel",
    "PermissionSet",
    "ToolExecutor",
    "ToolResult",
    "MCPManager",
]
