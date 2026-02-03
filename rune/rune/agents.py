"""
Declarative agent definitions for Rune.

Each agent is a configuration object — not a class — that specifies:
  - A name and description
  - A mode: "primary" (user-facing) or "subagent" (spawned by other agents)
  - A system prompt
  - A permission set controlling which tools it can use
  - Model parameters (temperature, max_completion_tokens)

Built-in agents:
  - build:  Primary agent with full read/write/execute access
  - plan:   Read-only agent for exploration, analysis, and planning
"""

from dataclasses import dataclass, field
from typing import Any

from rune.harness.permissions import (
    PermissionSet,
    build_permissions,
    plan_permissions,
    subagent_permissions,
)
from rune.harness.tools import TOOL_DEFINITIONS


@dataclass
class Agent:
    """
    Declarative configuration for an agent type.
    """
    name: str
    description: str
    # "primary" | "subagent"
    mode: str = "primary"
    system_prompt: str = ""
    permission_set: PermissionSet = field(default_factory=lambda: build_permissions())
    temperature: float = 0.0
    max_completion_tokens: int = 8192
    max_turns: int = 50


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _format_tools_list(permission_set: PermissionSet | None = None) -> str:
    """Generate a formatted list of available tools from TOOL_DEFINITIONS.

    Args:
        permission_set: Optional permission set to filter tools. If None, includes all tools.

    Returns:
        A formatted string with tool names and descriptions.
    """
    tools = []
    for tool_def in TOOL_DEFINITIONS:
        name = tool_def["function"]["name"]
        description = tool_def["function"]["description"]

        # Filter by permissions if provided
        if permission_set and permission_set.is_denied(name):
            continue

        tools.append(f"- {name}: {description}")

    return "\n".join(tools)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

BUILD_SYSTEM_PROMPT = f"""\
You are a coding assistant with full access to read, write, and execute code.

Available tools:
{_format_tools_list(build_permissions())}

When working on tasks:
1. Understand the codebase first — read relevant files before making changes
2. Make changes incrementally and verify they work
3. Run tests when available
4. Use the todo tool to track multi-step work
5. Use the task tool to delegate independent subtasks to subagents
6. Be careful with destructive operations
"""

PLAN_SYSTEM_PROMPT = f"""\
You are a read-only planning and analysis assistant. You can explore the codebase \
and answer questions, but you CANNOT modify files or execute commands.

Available tools:
{_format_tools_list(plan_permissions())}

Your role:
1. Explore and understand codebases
2. Design implementation plans with clear steps
3. Identify potential issues and architectural trade-offs
4. Answer questions about code structure and behavior

You CANNOT write files, edit files, run shell commands, or spawn subagents. \
If the user needs changes made, suggest switching to the build agent.
"""

SUBAGENT_SYSTEM_PROMPT = f"""\
You are a subagent handling a specific subtask. Complete the task autonomously \
and return a clear summary of what you did.

Available tools:
{_format_tools_list(subagent_permissions())}

Focus on:
1. Completing the assigned task efficiently
2. Returning a concise summary of actions taken and results
"""


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------

AGENT_REGISTRY: dict[str, Agent] = {
    "build": Agent(
        name="build",
        description="Primary agent with full file and command access",
        mode="primary",
        system_prompt=BUILD_SYSTEM_PROMPT,
        permission_set=build_permissions(),
        temperature=0.0,
        max_completion_tokens=4096,
        max_turns=50,
    ),
    "plan": Agent(
        name="plan",
        description="Read-only agent for exploration and analysis",
        mode="primary",
        system_prompt=PLAN_SYSTEM_PROMPT,
        permission_set=plan_permissions(),
        temperature=0.0,
        max_completion_tokens=4096,
        max_turns=30,
    ),
    "subagent": Agent(
        name="subagent",
        description="Subagent for handling delegated subtasks",
        mode="subagent",
        system_prompt=SUBAGENT_SYSTEM_PROMPT,
        permission_set=subagent_permissions(),
        temperature=0.0,
        max_completion_tokens=4096,
        max_turns=30,
    ),
}


def get_agent(name: str) -> Agent:
    """
    Look up an agent by name.
    """
    if name not in AGENT_REGISTRY:
        available = ", ".join(AGENT_REGISTRY.keys())
        raise ValueError(f"Unknown agent {name!r}. Available: {available}")

    return AGENT_REGISTRY[name]


def list_agents() -> list[Agent]:
    """
    Return all registered agents.
    """
    return list(AGENT_REGISTRY.values())
