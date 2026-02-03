"""Session management for tracking conversation history.

Enhanced with:
  - Session forking (for subagents)
  - Token usage tracking
  - Improved compaction
  - Parent/child session relationships
"""

import copy
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Message:
    """A message in the conversation."""
    role: str  # "system", "user", "assistant", "tool"
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_api_format(self) -> dict[str, Any]:
        """Convert to OpenAI API message format."""
        msg: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class UsageStats:
    """Token usage statistics for a session."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, prompt: int = 0, completion: int = 0) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class Session:
    """Manages conversation history and state for an agent session."""

    working_dir: str
    system_prompt: str = ""
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    turn_count: int = 0
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_session_id: str | None = None
    child_session_ids: list[str] = field(default_factory=list)
    usage: UsageStats = field(default_factory=UsageStats)

    def __post_init__(self):
        """Initialize the session with the system prompt."""
        if self.system_prompt and not self.messages:
            self.messages.append(Message(role="system", content=self.system_prompt))

    def add_user_message(self, content: str) -> None:
        """Add a user message to the history."""
        self.messages.append(Message(role="user", content=content))
        self.turn_count += 1

    def add_assistant_message(
        self,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add an assistant message to the history."""
        self.messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))

    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> None:
        """Add a tool result to the history."""
        self.messages.append(Message(role="tool", content=result, tool_call_id=tool_call_id, name=name))

    def record_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        """Record token usage from an API call."""
        self.usage.add(prompt_tokens, completion_tokens)

    def get_api_messages(self) -> list[dict[str, Any]]:
        """Get messages in OpenAI API format."""
        msgs = [msg.to_api_format() for msg in self.messages]
        return self._ensure_tool_call_responses(msgs)

    @staticmethod
    def _ensure_tool_call_responses(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Repair message list to satisfy tool-call protocol.

        OpenAI requires that any assistant message containing `tool_calls` is
        followed by one `tool` message per `tool_call_id`.

        If the app is interrupted after persisting the assistant tool_calls but
        before persisting tool results, the next API call will fail with a 400.
        This function inserts placeholder tool responses for any missing ids.
        """

        repaired: list[dict[str, Any]] = []
        i = 0
        while i < len(msgs):
            m = msgs[i]
            repaired.append(m)

            if m.get("role") == "assistant" and m.get("tool_calls"):
                tool_calls = m.get("tool_calls") or []
                expected_ids: list[str] = []
                for tc in tool_calls:
                    if isinstance(tc, dict) and tc.get("id"):
                        expected_ids.append(tc["id"])

                # Copy any existing tool messages immediately following.
                j = i + 1
                seen_ids: set[str] = set()
                while j < len(msgs) and msgs[j].get("role") == "tool":
                    tcid = msgs[j].get("tool_call_id")
                    if tcid:
                        seen_ids.add(tcid)
                    repaired.append(msgs[j])
                    j += 1

                # Insert placeholders for missing tool_call_ids.
                for tid in expected_ids:
                    if tid not in seen_ids:
                        repaired.append(
                            {
                                "role": "tool",
                                "tool_call_id": tid,
                                "name": "unknown",
                                "content": "(Tool result missing: previous run was interrupted. Please retry.)",
                            }
                        )

                i = j
                continue

            i += 1

        return repaired

    def get_context_summary(self) -> str:
        """Get a summary of the current context for display."""
        return (
            f"Session {self.session_id} | Turn {self.turn_count} | "
            f"{len(self.messages)} messages | {self.usage.total_tokens} tokens | "
            f"{self.working_dir}"
        )

    # ----- Forking -----

    def fork(self, system_prompt: str | None = None) -> "Session":
        """Create a child session that inherits context but has its own history.

        Used for subagent spawning — the child gets a fresh conversation but
        the parent keeps a reference to it.
        """
        child = Session(
            working_dir=self.working_dir,
            system_prompt=system_prompt or self.system_prompt,
            parent_session_id=self.session_id,
        )
        self.child_session_ids.append(child.session_id)
        return child

    # ----- Compaction -----

    def compact(self, summary: str) -> None:
        """Compact the conversation by replacing older messages with a summary.

        Keeps the system message and last 10 messages.
        """
        system_msg = None
        if self.messages and self.messages[0].role == "system":
            system_msg = self.messages[0]

        compaction_msg = Message(
            role="system",
            content=f"[CONVERSATION SUMMARY]\n{summary}\n[END SUMMARY]",
        )

        recent = self.messages[-10:] if len(self.messages) > 10 else []
        self.messages = []
        if system_msg:
            self.messages.append(system_msg)
        self.messages.append(compaction_msg)
        self.messages.extend(recent)

    def needs_compaction(self, max_messages: int = 100) -> bool:
        """Heuristic: check if the session has grown too large."""
        return len(self.messages) > max_messages

    # ----- Persistence -----

    def save(self, path: str) -> None:
        """Save session to a JSON file."""
        data = {
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "child_session_ids": self.child_session_ids,
            "working_dir": self.working_dir,
            "system_prompt": self.system_prompt,
            "messages": [msg.to_api_format() for msg in self.messages],
            "created_at": self.created_at.isoformat(),
            "turn_count": self.turn_count,
            "usage": self.usage.to_dict(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Session":
        """Load session from a JSON file."""
        with open(path, "r") as f:
            data = json.load(f)

        session = cls(
            working_dir=data["working_dir"],
            system_prompt=data["system_prompt"],
            created_at=datetime.fromisoformat(data["created_at"]),
            turn_count=data["turn_count"],
        )
        session.session_id = data.get("session_id", session.session_id)
        session.parent_session_id = data.get("parent_session_id")
        session.child_session_ids = data.get("child_session_ids", [])

        usage_data = data.get("usage", {})
        session.usage = UsageStats(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        session.messages = []
        for msg_data in data["messages"]:
            session.messages.append(Message(
                role=msg_data["role"],
                content=msg_data.get("content"),
                tool_calls=msg_data.get("tool_calls"),
                tool_call_id=msg_data.get("tool_call_id"),
                name=msg_data.get("name"),
            ))

        return session

    def clear(self) -> None:
        """Clear all messages except the system prompt."""
        system_msg = None
        if self.messages and self.messages[0].role == "system":
            system_msg = self.messages[0]
        self.messages = []
        if system_msg:
            self.messages.append(system_msg)
        self.turn_count = 0
