"""Proto - A coding agent harness inspired by OpenCode."""

from proto.agent import Agent, AgentConfig
from proto.agents import AgentDefinition, get_agent_definition, list_agents
from proto.mcp_client import MCPManager
from proto.permissions import PermissionSet, PermissionLevel
from proto.session import Session

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
