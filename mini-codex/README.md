# Mini Codex

A minimal coding agent inspired by [OpenAI's Codex](https://github.com/openai/codex).

This is a lightweight Python implementation that demonstrates the core concepts of an agentic coding assistant:

- **Agent Loop**: Iteratively processes user requests, calling tools as needed until the task is complete
- **Tool System**: Provides shell execution, file read/write, and patch application capabilities
- **Session Management**: Tracks conversation history for multi-turn interactions

## Architecture

The agent loop follows this pattern:

```
User Input -> Model -> Tool Calls? -> Execute Tools -> Model -> ... -> Final Response
```

Key components:

- `agent.py`: Core agent loop that orchestrates the conversation
- `tools.py`: Tool definitions and executor with sandboxing
- `session.py`: Conversation history and state management
- `cli.py`: Command-line interface

## Installation

```bash
# From the mini-codex directory
pip install -e .

# Or just install dependencies
pip install -r requirements.txt
```

## Usage

### Interactive Mode

```bash
# Run in current directory
mini-codex

# Run in specific directory
mini-codex -d /path/to/project
```

### Single Prompt Mode

```bash
mini-codex -p "list all Python files and count lines of code"
```

### Options

```
-d, --directory    Working directory (default: current)
-p, --prompt       Single prompt to run
--model            OpenAI model (default: gpt-4o)
--temperature      Model temperature (default: 0.0)
--max-turns        Max agent loop iterations (default: 50)
--no-auto-approve  Require confirmation for tools
```

## Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key (required)

## Example Session

```
> list all files in this directory
[Tool: list_files]
  path: .

README.md
main.py
mini_codex/
requirements.txt

The directory contains a Python package with a README, main entry point,
the mini_codex module, and a requirements file.

> read the main.py file
[Tool: read_file]
  path: main.py

#!/usr/bin/env python3
from mini_codex.cli import main
...
```

## Available Tools

| Tool | Description |
|------|-------------|
| `shell` | Execute shell commands |
| `read_file` | Read file contents |
| `write_file` | Write/create files |
| `list_files` | List directory contents |
| `apply_patch` | Apply unified diff patches |

## Programmatic Usage

```python
from mini_codex import Agent, AgentConfig

# Create an agent
agent = Agent(
    working_dir="/path/to/project",
    config=AgentConfig(model="gpt-4o", temperature=0.0)
)

# Run synchronously
response = agent.run_sync("What files are in this project?")
print(response)

# Run with streaming
for turn in agent.run("Add a hello world function"):
    if turn.tool_calls:
        print(f"Executing {len(turn.tool_calls)} tools...")
    if turn.finished:
        print(turn.response)
```

## Credits

Inspired by [OpenAI Codex](https://github.com/openai/codex) and the concepts described in
[Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/).
