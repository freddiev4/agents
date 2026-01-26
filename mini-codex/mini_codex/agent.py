"""Core agent loop implementation inspired by OpenAI's Codex."""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Generator

from openai import OpenAI

from .session import Session
from .tools import TOOL_DEFINITIONS, ToolExecutor, ToolResult

# Default system prompt for the coding agent
DEFAULT_SYSTEM_PROMPT = """You are a helpful coding assistant that can read, write, and execute code.

You have access to the following tools:
- shell: Execute shell commands (for running tests, git operations, etc.)
- read_file: Read file contents
- write_file: Write content to files
- list_files: List directory contents
- apply_patch: Apply unified diff patches to files

When helping with coding tasks:
1. First understand the codebase by reading relevant files
2. Make changes incrementally and verify they work
3. Run tests when available to ensure correctness
4. Explain what you're doing as you work

Always be careful with destructive operations and confirm before making major changes."""


@dataclass
class AgentConfig:
    """Configuration for the agent."""
    model: str = "gpt-4o"
    temperature: float = 0.0
    max_tokens: int = 4096
    max_turns: int = 50  # Safety limit on agent loop iterations
    auto_approve_tools: bool = True  # If False, will ask for confirmation


@dataclass
class TurnResult:
    """Result of a single agent turn."""
    response: str | None
    tool_calls: list[dict[str, Any]]
    tool_results: list[ToolResult]
    finished: bool = False


class Agent:
    """
    A minimal coding agent inspired by OpenAI's Codex.

    The agent loop:
    1. Receives user input
    2. Sends conversation to the model
    3. If model requests tool calls, execute them and loop back to step 2
    4. When model produces a final response, return it
    """

    def __init__(
        self,
        working_dir: str,
        config: AgentConfig | None = None,
        system_prompt: str | None = None,
        approval_callback: Callable[[str, str, dict], bool] | None = None
    ):
        self.working_dir = os.path.abspath(working_dir)
        self.config = config or AgentConfig()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        # Initialize OpenAI client
        self.client = OpenAI()

        # Initialize session
        self.session = Session(
            working_dir=self.working_dir,
            system_prompt=self._build_system_prompt()
        )

        # Initialize tool executor
        self.tool_executor = ToolExecutor(self.working_dir)

        # Approval callback for tool execution
        self.approval_callback = approval_callback

    def _build_system_prompt(self) -> str:
        """Build the complete system prompt with context."""
        context_info = f"""
Working Directory: {self.working_dir}
"""
        return f"{self.system_prompt}\n\n{context_info}"

    def run(self, user_input: str) -> Generator[TurnResult, None, str]:
        """
        Run the agent loop for a user input.

        Yields TurnResult objects for each iteration of the loop.
        Returns the final response string.
        """
        self.session.add_user_message(user_input)

        turn_count = 0
        while turn_count < self.config.max_turns:
            turn_count += 1

            # Call the model
            response = self._call_model()

            # Extract the message
            message = response.choices[0].message

            # Check if model wants to use tools
            if message.tool_calls:
                # Add assistant message with tool calls
                tool_calls_data = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
                self.session.add_assistant_message(
                    content=message.content,
                    tool_calls=tool_calls_data
                )

                # Execute tools
                tool_results = []
                for tool_call in message.tool_calls:
                    result = self._execute_tool(tool_call)
                    tool_results.append(result)

                    # Add tool result to session
                    result_content = result.output if result.success else f"Error: {result.error}"
                    self.session.add_tool_result(
                        tool_call_id=tool_call.id,
                        name=tool_call.function.name,
                        result=result_content
                    )

                yield TurnResult(
                    response=message.content,
                    tool_calls=tool_calls_data,
                    tool_results=tool_results,
                    finished=False
                )
            else:
                # Model produced a final response
                self.session.add_assistant_message(content=message.content)

                yield TurnResult(
                    response=message.content,
                    tool_calls=[],
                    tool_results=[],
                    finished=True
                )

                return message.content

        # Safety limit reached
        return "Agent reached maximum turn limit."

    def run_sync(self, user_input: str) -> str:
        """Run the agent loop synchronously and return the final response."""
        result = None
        for turn in self.run(user_input):
            result = turn
        return result.response if result else ""

    def _call_model(self):
        """Call the OpenAI API with the current conversation."""
        return self.client.chat.completions.create(
            model=self.config.model,
            messages=self.session.get_api_messages(),
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens
        )

    def _execute_tool(self, tool_call) -> ToolResult:
        """Execute a single tool call."""
        tool_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid JSON arguments: {tool_call.function.arguments}"
            )

        # Check for approval if required
        if not self.config.auto_approve_tools and self.approval_callback:
            if not self.approval_callback(tool_name, tool_call.id, arguments):
                return ToolResult(
                    success=False,
                    output="",
                    error="Tool execution denied by user"
                )

        # Execute the tool
        return self.tool_executor.execute(tool_name, arguments)

    def get_session(self) -> Session:
        """Get the current session."""
        return self.session

    def reset(self) -> None:
        """Reset the agent session."""
        self.session = Session(
            working_dir=self.working_dir,
            system_prompt=self._build_system_prompt()
        )
