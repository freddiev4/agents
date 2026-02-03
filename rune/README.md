# Rune 🔮

A powerful coding agent with a clean API and beautiful Rich terminal output.

## Features

- **Simple API** - Just `Agent().run("task")` and you're done
- **Streaming Support** - See tool calls and progress in real-time
- **Permission System** - Control what the agent can do (allow/ask/deny)
- **Agent Types** - Build (full access) and Plan (read-only) agents
- **15 Built-in Tools** - File operations, shell commands, web search, and more
- **MCP Support** - Extend with external tool servers
- **Subagent Spawning** - Delegate subtasks to child agents
- **Rich Output** - Beautiful terminal UI with panels, tables, and colors
- **Session Management** - Forking, compaction, and persistence

## Installation

```bash
# Clone and install
cd rune
uv venv
source .venv/bin/activate
uv pip install -e .
```

## Quick Start

### CLI Usage

```bash
# Interactive mode
rune

# Single prompt
rune -p "create a hello.py file"

# Read-only agent
rune --agent plan

# Use different model
rune --model gpt-5.2-2025-12-11

# With MCP servers
rune --mcp-config mcp.json
```

### Python API

```python
from rune import Agent, AgentConfig

# Simplest usage
agent = Agent()
result = agent.run("List all Python files")
print(result)

# With configuration
agent = Agent(config=AgentConfig(
    model="gpt-5.2-2025-12-11",
    agent_name="build",
    auto_approve_tools=True
))

# Simple run - get final result
result = agent.run("Create a test.py file")

# Streaming - see progress
for turn in agent.stream("Analyze the codebase"):
    if turn.tool_calls:
        print(f"Using tool: {turn.tool_calls}")
    if turn.finished:
        print(f"Done: {turn.response}")
```

## Configuration

### Agent Types

- **build** - Full access agent (read, write, execute, spawn subagents)
- **plan** - Read-only agent (explore, analyze, but cannot modify)
- **subagent** - Like build but cannot spawn more subagents (prevents recursion)

### Agent Config

```python
from rune import Agent, AgentConfig

config = AgentConfig(
    model="gpt-4o",              # OpenAI model to use
    agent_name="build",          # Agent type
    auto_approve_tools=True,     # Auto-approve tool execution
    mcp_config_path=None         # Path to MCP config JSON
)

agent = Agent(config=config)
```

## Built-in Tools

Rune includes 15 powerful tools:

**File Operations:**
- `read_file` - Read files with line range support
- `write_file` - Create or overwrite files
- `edit_file` - Search and replace in files
- `multi_edit` - Multiple edits in one call
- `apply_patch` - Apply unified diff patches
- `list_files` - List directory contents
- `glob` - Pattern-based file search
- `grep` - Regex content search with context
- `tree` - Recursive directory tree

**Execution:**
- `shell` - Execute shell commands (with approval)

**Web:**
- `web_fetch` - Fetch URL content
- `web_search` - Search the web (requires TAVILY_API_KEY)

**Organization:**
- `task` - Spawn subagent for subtasks
- `todo` - Structured task list management
- `notebook_edit` - Edit Jupyter notebook cells

## MCP Integration

Extend Rune with external tool servers using the Model Context Protocol:

```json
{
  "servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"],
      "env": {}
    }
  }
}
```

```bash
rune --mcp-config mcp.json
```

## Examples

See `example.py` and `researcher.py` for complete examples.

## Architecture

Rune is split into two main layers:

- **Agent definitions** (`rune/agents.py`)  declarative agent types (build/plan/subagent),
  system prompts, model parameters, and permission sets.
- **Harness runtime** (`rune/harness/`)  the orchestration layer that runs the agent loop.

### Harness components (`rune/harness/`)

- `agent.py`  core turn-based loop (`Agent.stream()`), tool routing, subagent spawning, and
  session compaction.
- `session.py`  conversation state, forking (for subagents), compaction, persistence, and
  token usage tracking.
- `tools.py`  built-in tool schemas (`TOOL_DEFINITIONS`) and the `ToolExecutor` implementations
  (filesystem, shell, web_fetch, todo, notebook_edit, etc.).
- `permissions.py`  permission model (ALLOW/ASK/DENY) and prebuilt permission sets.
- `mcp_client.py`  MCP integration for external tool servers (discover tools, call tools,
  shutdown).

### UI / entrypoints

- `rune/cli.py`  Rich-powered interactive CLI and streaming display of tool calls/results.
- `from rune import Agent, AgentConfig`  stable public API re-exported from `rune/__init__.py`.

### Key behaviors

- Turn-based generator loop for streaming results
- Session management with forking and compaction
- Permission-based tool filtering + optional user approval
- Built-in tools + optional MCP-provided external tools
- Subagent spawning for delegated subtasks

## Development

```bash
# Install for development
uv pip install -e .

# Run tests
pytest

# Format code
black .
```

## API Reference

### Agent

```python
Agent(
    config: AgentConfig | None = None,
    approval_callback: Callable | None = None
)
```

**Methods:**
- `run(user_input: str) -> str` - Run and return final result
- `stream(user_input: str) -> Generator[TurnResult, None, str]` - Stream progress
- `switch_agent(agent_name: str)` - Switch agent type
- `reset()` - Reset session
- `shutdown()` - Clean up resources

### AgentConfig

```python
AgentConfig(
    model: str = "gpt-4o",
    agent_name: str = "build",
    auto_approve_tools: bool = True,
    mcp_config_path: str | None = None
)
```

### TurnResult

```python
@dataclass
class TurnResult:
    response: str | None
    tool_calls: list[dict]
    tool_results: list[ToolResult]
    finished: bool
    agent_name: str
```

## License

MIT

## Credits

- Built with [OpenAI API](https://platform.openai.com/)
- Terminal UI with [Rich](https://github.com/Textualize/rich)
