"""Permission system for controlling tool access per agent."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionLevel(Enum):
    """Permission levels for tool execution."""
    ALLOW = "allow"       # Always allowed without prompting
    ASK = "ask"           # Requires user confirmation
    DENY = "deny"         # Never allowed


@dataclass
class ToolPermission:
    """Permission rule for a specific tool."""
    tool_name: str
    level: PermissionLevel = PermissionLevel.ASK
    # Optional constraints on arguments (e.g., restrict shell commands)
    allowed_args: dict[str, Any] | None = None
    denied_patterns: list[str] | None = None


@dataclass
class PermissionSet:
    """A collection of permission rules for an agent."""
    name: str
    default_level: PermissionLevel = PermissionLevel.ASK
    tool_permissions: dict[str, ToolPermission] = field(default_factory=dict)

    def get_permission(self, tool_name: str) -> PermissionLevel:
        """Get the permission level for a tool."""
        if tool_name in self.tool_permissions:
            return self.tool_permissions[tool_name].level
        return self.default_level

    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed (ALLOW level, no prompting needed)."""
        return self.get_permission(tool_name) == PermissionLevel.ALLOW

    def is_denied(self, tool_name: str) -> bool:
        """Check if a tool is explicitly denied."""
        return self.get_permission(tool_name) == PermissionLevel.DENY

    def needs_approval(self, tool_name: str) -> bool:
        """Check if a tool requires user approval."""
        return self.get_permission(tool_name) == PermissionLevel.ASK

    def set_permission(self, tool_name: str, level: PermissionLevel) -> None:
        """Set the permission level for a tool."""
        if tool_name in self.tool_permissions:
            self.tool_permissions[tool_name].level = level
        else:
            self.tool_permissions[tool_name] = ToolPermission(
                tool_name=tool_name, level=level
            )

    def merge(self, other: "PermissionSet") -> "PermissionSet":
        """Merge with another permission set. The other set's rules take precedence."""
        merged = PermissionSet(
            name=f"{self.name}+{other.name}",
            default_level=other.default_level,
            tool_permissions={**self.tool_permissions, **other.tool_permissions},
        )
        return merged


# ----- Pre-built permission sets -----

def build_permissions() -> PermissionSet:
    """Full-access permissions for the build agent."""
    ps = PermissionSet(name="build", default_level=PermissionLevel.ALLOW)
    # All tools allowed, but destructive shell commands still require approval
    ps.tool_permissions = {
        "shell": ToolPermission("shell", PermissionLevel.ASK,
                                denied_patterns=["rm -rf /", "mkfs", "> /dev/"]),
        "read_file": ToolPermission("read_file", PermissionLevel.ALLOW),
        "write_file": ToolPermission("write_file", PermissionLevel.ALLOW),
        "edit_file": ToolPermission("edit_file", PermissionLevel.ALLOW),
        "multi_edit": ToolPermission("multi_edit", PermissionLevel.ALLOW),
        "apply_patch": ToolPermission("apply_patch", PermissionLevel.ALLOW),
        "list_files": ToolPermission("list_files", PermissionLevel.ALLOW),
        "glob": ToolPermission("glob", PermissionLevel.ALLOW),
        "grep": ToolPermission("grep", PermissionLevel.ALLOW),
        "tree": ToolPermission("tree", PermissionLevel.ALLOW),
        "web_fetch": ToolPermission("web_fetch", PermissionLevel.ASK),
        "web_search": ToolPermission("web_search", PermissionLevel.ASK),
        "task": ToolPermission("task", PermissionLevel.ALLOW),
        "todo": ToolPermission("todo", PermissionLevel.ALLOW),
        "notebook_edit": ToolPermission("notebook_edit", PermissionLevel.ALLOW),
    }
    return ps


def plan_permissions() -> PermissionSet:
    """Read-only permissions for the plan agent."""
    ps = PermissionSet(name="plan", default_level=PermissionLevel.DENY)
    ps.tool_permissions = {
        "read_file": ToolPermission("read_file", PermissionLevel.ALLOW),
        "list_files": ToolPermission("list_files", PermissionLevel.ALLOW),
        "glob": ToolPermission("glob", PermissionLevel.ALLOW),
        "grep": ToolPermission("grep", PermissionLevel.ALLOW),
        "tree": ToolPermission("tree", PermissionLevel.ALLOW),
        "web_fetch": ToolPermission("web_fetch", PermissionLevel.ASK),
        "web_search": ToolPermission("web_search", PermissionLevel.ASK),
        "todo": ToolPermission("todo", PermissionLevel.ALLOW),
    }
    return ps


def subagent_permissions() -> PermissionSet:
    """Permissions for subagents — same as build but no recursive task spawning."""
    ps = build_permissions()
    ps.name = "subagent"
    ps.tool_permissions["task"] = ToolPermission("task", PermissionLevel.DENY)
    return ps
