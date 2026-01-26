"""Session management for tracking conversation history."""

import json
import os
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
class Session:
    """Manages conversation history and state for an agent session."""

    working_dir: str
    system_prompt: str = ""
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    turn_count: int = 0

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
        tool_calls: list[dict[str, Any]] | None = None
    ) -> None:
        """Add an assistant message to the history."""
        self.messages.append(Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls
        ))

    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> None:
        """Add a tool result to the history."""
        self.messages.append(Message(
            role="tool",
            content=result,
            tool_call_id=tool_call_id,
            name=name
        ))

    def get_api_messages(self) -> list[dict[str, Any]]:
        """Get messages in OpenAI API format."""
        return [msg.to_api_format() for msg in self.messages]

    def get_context_summary(self) -> str:
        """Get a summary of the current context for display."""
        return f"Turn {self.turn_count} | {len(self.messages)} messages | {self.working_dir}"

    def compact(self, summary: str) -> None:
        """
        Compact the conversation history by replacing older messages with a summary.

        This is useful for long-running sessions to manage context window limits.
        """
        # Keep system message and last few exchanges
        system_msg = None
        if self.messages and self.messages[0].role == "system":
            system_msg = self.messages[0]

        # Create compaction summary message
        compaction_msg = Message(
            role="system",
            content=f"[CONVERSATION SUMMARY]\n{summary}\n[END SUMMARY]"
        )

        # Keep the last 10 messages (5 exchanges) plus the new summary
        recent_messages = self.messages[-10:] if len(self.messages) > 10 else []

        # Rebuild messages
        self.messages = []
        if system_msg:
            self.messages.append(system_msg)
        self.messages.append(compaction_msg)
        self.messages.extend(recent_messages)

    def save(self, path: str) -> None:
        """Save session to a JSON file."""
        data = {
            "working_dir": self.working_dir,
            "system_prompt": self.system_prompt,
            "messages": [msg.to_api_format() for msg in self.messages],
            "created_at": self.created_at.isoformat(),
            "turn_count": self.turn_count
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
            turn_count=data["turn_count"]
        )

        # Reconstruct messages
        session.messages = []
        for msg_data in data["messages"]:
            session.messages.append(Message(
                role=msg_data["role"],
                content=msg_data.get("content"),
                tool_calls=msg_data.get("tool_calls"),
                tool_call_id=msg_data.get("tool_call_id"),
                name=msg_data.get("name")
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
