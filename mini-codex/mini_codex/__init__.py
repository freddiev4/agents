"""Mini Codex - A coding agent harness inspired by OpenCode."""

from mini_codex.agent import Agent, AgentConfig
from mini_codex.agents import AgentDefinition, get_agent_definition, list_agents
from mini_codex.mcp_client import MCPManager
from mini_codex.permissions import PermissionSet, PermissionLevel
from mini_codex.session import Session

__version__ = "0.2.0"
__all__ = [
    "Agent",
    "AgentConfig",
    "AgentDefinition",
    "MCPManager",
    "PermissionLevel",
    "PermissionSet",
    "Session",
    "get_agent_definition",
    "list_agents",
]
