# Proto

A coding agent harness inspired by [OpenCode](https://github.com/anomalyco/opencode), demonstrating production-grade harness patterns in ~1000 lines of Python.

## Project Overview

Proto is a versatile coding agent framework that provides a set of built-in tools and supports external tool servers via the Model Context Protocol (MCP). It features permission management, subagent spawning, and supports both build (full access) and plan (read-only) agent modes.

## Installation Instructions

To set up the project locally, ensure you have Python 3.10 or higher, and then run:

```bash
pip install -e .
```

This will install the necessary dependencies as specified in the `requirements.txt` and `pyproject.toml` files.

## Usage

### Interactive Mode

Run the following commands to start the agent in different modes:

```bash
# Build agent (full access - default)
proto

# Plan agent (read-only)
proto --agent plan

# With MCP tool servers
proto --mcp-config mcp.json
```

### Single Prompt

Execute a single command non-interactively:

```bash
proto -p "find all TODO comments in this project"
```

### REPL Commands

| Command | Description |
|---------|-------------|
| `exit` / `quit` | Exit |
| `reset` | Clear session history |
| `history` | Show conversation |
| `status` | Show session stats (turns, tokens, etc.) |
| `agents` | List available agent types |
| `switch build` / `switch plan` | Switch agent type |

### CLI Options

```
-d, --directory     Working directory (default: current)
-p, --prompt        Single prompt (non-interactive)
--model             OpenAI model (default: gpt-4o)
--agent             Agent type: build or plan (default: build)
--mcp-config        Path to MCP server config JSON
--no-auto-approve   Require confirmation for tool execution
```

## Code Structure

- `proto/agent.py`: Core agent loop with permission checks and MCP routing.
- `proto/agents.py`: Definitions for build and plan agents.
- `proto/tools.py`: Implementation of 15 built-in tools.
- `proto/mcp_client.py`: MCP support for external tool servers.
- `proto/permissions.py`: Tool access control.
- `proto/session.py`: Session management and compaction.

## Contribution Guidelines

Contributions are welcome! Please fork the repository and submit a pull request. Ensure your code adheres to the existing style and includes tests where applicable.

## License

This project is licensed under the MIT License.
