"""Core agent loop implementation.

Orchestrates the harness: agent definitions, permissions, tools (built-in +
MCP), session management, and subagent spawning.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Generator

from openai import OpenAI

from ..agents import Agent as AgentDef, get_agent, AGENT_REGISTRY
from rune.harness.mcp_client import MCPManager
from rune.harness.permissions import PermissionLevel
from rune.harness.session import Session
from rune.harness.tools import TOOL_DEFINITIONS, ToolExecutor, ToolResult, TodoList
from rune.harness.skills import SkillsManager


@dataclass
class AgentConfig:
    """Runtime configuration for an agent instance."""
    model: str = "gpt-4o"
    agent_name: str = "build"  # Which agent definition to use
    auto_approve_tools: bool = True
    mcp_config_path: str | None = None  # Path to mcp.json


@dataclass
class TurnResult:
    """Result of a single agent turn."""
    response: str | None
    tool_calls: list[dict[str, Any]]
    tool_results: list[ToolResult]
    finished: bool = False
    agent_name: str = "build"


class Agent:
    """
    A coding agent with support for multiple agent types, permissions,
    MCP tools, and subagent spawning.

    The agent loop:
    1. Receives user input
    2. Sends conversation to the model with permitted tools
    3. If model requests tool calls, check permissions, execute, loop
    4. When model produces a final response, return it
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        approval_callback: Callable[[str, str, dict], bool] | None = None,
        _is_subagent: bool = False,
        _parent_todo_list: TodoList | None = None,
    ):
        self.working_dir = os.getcwd()
        self.config = config or AgentConfig()
        self.approval_callback = approval_callback
        self._is_subagent = _is_subagent

        # Load agent definition
        self.agent_def: AgentDef = get_agent(self.config.agent_name)

        # Initialize OpenAI client
        self.client = OpenAI()

        # Shared todo list (subagents share with parent)
        self.todo_list = _parent_todo_list or TodoList()

        # Initialize tool executor with subagent callback
        self.tool_executor = ToolExecutor(
            self.working_dir,
            todo_list=self.todo_list,
            subagent_callback=self._spawn_subagent if not _is_subagent else None,
        )

        # Initialize MCP manager
        self.mcp = MCPManager()
        if self.config.mcp_config_path:
            self.mcp.load_config(self.config.mcp_config_path)
            self._mcp_tools = self.mcp.start_all()
        else:
            self._mcp_tools = []

        # Initialize skills manager (prompt augmentation + per-turn injections)
        self.skills = SkillsManager(working_dir=self.working_dir)

        # Initialize session
        self.session = Session(
            working_dir=self.working_dir,
            system_prompt=self._build_system_prompt(),
        )

    def _build_system_prompt(self) -> str:
        """Build the complete system prompt with context."""
        context = f"\nWorking Directory: {self.working_dir}\n"
        mcp_info = ""
        if self._mcp_tools:
            names = ", ".join(t.name for t in self._mcp_tools)
            mcp_info = f"\nAdditional MCP tools available: {names}\n"

        skills_section = self.skills.render_skills_section()
        skills_info = f"\n{skills_section}\n" if skills_section else ""

        return f"{self.agent_def.system_prompt}\n{context}{mcp_info}{skills_info}"

    def _get_permitted_tools(self) -> list[dict[str, Any]]:
        """Get tool definitions filtered by this agent's permissions."""
        perm = self.agent_def.permission_set
        tools = []
        for tool_def in TOOL_DEFINITIONS:
            name = tool_def["function"]["name"]
            if not perm.is_denied(name):
                tools.append(tool_def)
        # Add MCP tools (all allowed unless explicitly denied)
        for mcp_def in self.mcp.get_tool_definitions():
            name = mcp_def["function"]["name"]
            if not perm.is_denied(name):
                tools.append(mcp_def)
        return tools

    def stream(self, user_input: str) -> Generator[TurnResult, None, str]:
        """Stream the agent loop for a user input.

        Yields TurnResult objects for each iteration.
        Returns the final response string.
        """
        self.session.add_user_message(user_input)

        turn_count = 0
        while turn_count < self.agent_def.max_turns:
            turn_count += 1

            # Check if compaction is needed
            if self.session.needs_compaction():
                self._compact_session()

            # Call the model
            response = self._call_model()

            # Record token usage
            if hasattr(response, "usage") and response.usage:
                self.session.record_usage(
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                )

            message = response.choices[0].message

            if message.tool_calls:
                tool_calls_data = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
                self.session.add_assistant_message(
                    content=message.content,
                    tool_calls=tool_calls_data,
                )

                tool_results = []
                for tool_call in message.tool_calls:
                    result = self._execute_tool(tool_call)
                    tool_results.append(result)
                    result_content = result.output if result.success else f"Error: {result.error}"
                    self.session.add_tool_result(
                        tool_call_id=tool_call.id,
                        name=tool_call.function.name,
                        result=result_content,
                    )

                yield TurnResult(
                    response=message.content,
                    tool_calls=tool_calls_data,
                    tool_results=tool_results,
                    finished=False,
                    agent_name=self.agent_def.name,
                )
            else:
                self.session.add_assistant_message(content=message.content)
                yield TurnResult(
                    response=message.content,
                    tool_calls=[],
                    tool_results=[],
                    finished=True,
                    agent_name=self.agent_def.name,
                )
                return message.content

        return "Agent reached maximum turn limit."

    def run(self, user_input: str) -> str:
        """Run the agent and return the final response."""
        result = None
        for turn in self.stream(user_input):
            result = turn
        return result.response if result else ""

    def _call_model(self):
        """Call the OpenAI API with the current conversation."""
        # Inject skill bodies for this turn based on the latest user message.
        # This is done at call time so skills are not persisted across turns.
        self.skills.apply_turn_injections(self.session)
        return self.client.chat.completions.create(
            model=self.config.model,
            messages=self.session.get_api_messages(),
            tools=self._get_permitted_tools(),
            tool_choice="auto",
            temperature=self.agent_def.temperature,
            max_completion_tokens=self.agent_def.max_completion_tokens,
        )

    def _execute_tool(self, tool_call) -> ToolResult:
        """Execute a single tool call with permission checking."""
        tool_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return ToolResult(
                success=False, output="",
                error=f"Invalid JSON arguments: {tool_call.function.arguments}",
            )

        perm = self.agent_def.permission_set

        # Check if tool is denied
        if perm.is_denied(tool_name):
            return ToolResult(
                success=False, output="",
                error=f"Tool {tool_name!r} is not permitted for the {self.agent_def.name} agent",
            )

        # Check if tool needs approval
        if perm.needs_approval(tool_name) and not self.config.auto_approve_tools:
            if self.approval_callback:
                if not self.approval_callback(tool_name, tool_call.id, arguments):
                    return ToolResult(success=False, output="", error="Tool execution denied by user")
            # If auto_approve is on or no callback, proceed

        # Route to MCP if it's an MCP tool
        if self.mcp.has_tool(tool_name):
            return self.mcp.call_tool(tool_name, arguments)

        # Execute built-in tool
        return self.tool_executor.execute(tool_name, arguments)

    def _spawn_subagent(self, description: str, prompt: str) -> str:
        """Spawn a child agent to handle a subtask.

        Creates a new Agent with the 'subagent' definition, a forked session,
        and runs it synchronously to completion.
        """
        # Fork the session for the child
        child_session = self.session.fork(
            system_prompt=get_agent("subagent").system_prompt
        )

        # Create child agent config
        child_config = AgentConfig(
            model=self.config.model,
            agent_name="subagent",
            auto_approve_tools=self.config.auto_approve_tools,
            mcp_config_path=self.config.mcp_config_path,
        )

        child_agent = Agent(
            config=child_config,
            approval_callback=self.approval_callback,
            _is_subagent=True,
            _parent_todo_list=self.todo_list,
        )

        # Replace the child agent's session with the forked one
        child_agent.session = child_session

        # Run the subagent
        result = child_agent.run(prompt)

        # Accumulate child usage into parent
        self.session.usage.add(
            child_session.usage.prompt_tokens,
            child_session.usage.completion_tokens,
        )

        return result

    def _compact_session(self) -> None:
        """Use the model to summarize the conversation and compact it."""
        messages = self.session.get_api_messages()
        summary_prompt = (
            "Summarize the conversation so far in 2-3 paragraphs. "
            "Include key decisions, files modified, and current state."
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages + [{"role": "user", "content": summary_prompt}],
                temperature=0.0,
                max_completion_tokens=1024,
            )
            summary = resp.choices[0].message.content or "No summary available."
            self.session.compact(summary)
        except Exception:
            # If summarization fails, do a simple truncation
            self.session.compact("(Automatic compaction — older messages truncated)")

    # ----- Public API -----

    def switch_agent(self, agent_name: str) -> None:
        """Switch to a different agent type, preserving conversation history."""
        new_def = get_agent(agent_name)
        self.agent_def = new_def
        self.config.agent_name = agent_name

        # Update the system message
        if self.session.messages and self.session.messages[0].role == "system":
            self.session.messages[0].content = self._build_system_prompt()
        # Update tool executor subagent callback
        if new_def.mode == "primary":
            self.tool_executor.subagent_callback = self._spawn_subagent
        else:
            self.tool_executor.subagent_callback = None

    def get_session(self) -> Session:
        return self.session

    def reset(self) -> None:
        """Reset the agent session."""
        self.session = Session(
            working_dir=self.working_dir,
            system_prompt=self._build_system_prompt(),
        )

    def shutdown(self) -> None:
        """Clean up resources (MCP servers, etc.)."""
        self.mcp.shutdown_all()
