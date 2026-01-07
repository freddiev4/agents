# Claude Code Configuration

This directory contains custom plugins, scripts, hooks, and skills for enhancing Claude Code functionality.

## Table of Contents

- [Directory Structure](#directory-structure)
- [Plugins](#plugins)
  - [Ralph Wiggum Plugin](#ralph-wiggum-plugin-pluginsralph)
- [Scripts](#scripts)
  - [Git Safety Guard Installer](#git-safety-guard-installer-install-claude-git-guardsh)
- [Hooks](#hooks)
  - [Currently Active Hooks](#currently-active-hooks)
  - [Hook Types Available](#hook-types-available)
- [Skills](#skills)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Resources](#resources)
- [Contributing](#contributing)

## Directory Structure

```
claude-code/
├── plugins/          # Claude Code plugins
├── scripts/          # Installation and utility scripts
├── .claude/
│   ├── hooks/       # Hook implementations
│   └── settings.json
└── README.md
```

## Plugins

### Ralph Wiggum Plugin (`plugins/ralph/`)

Implementation of the Ralph Wiggum technique for iterative, self-referential AI development loops.

**What it does:**
- Creates a continuous feedback loop where Claude iteratively improves code until completion
- Uses a Stop hook to intercept exit attempts and feed the same prompt back
- Enables autonomous iteration on well-defined tasks with clear success criteria

**Key commands:**
- `/ralph-loop "<prompt>" --max-iterations <n> --completion-promise "<text>"` - Start a Ralph loop
- `/cancel-ralph` - Cancel the active Ralph loop
- `/help` - Get detailed documentation

**When to use:**
- Well-defined tasks with clear success criteria (e.g., "make all tests pass")
- Tasks requiring iteration and refinement
- Greenfield projects where autonomous iteration is valuable
- Tasks with automatic verification (tests, linters, builds)

**When NOT to use:**
- Tasks requiring human judgment or design decisions
- One-shot operations
- Tasks with unclear success criteria

**Example:**
```bash
/ralph-loop "Build a REST API for todos. Requirements: CRUD operations, input validation, tests. Output <promise>COMPLETE</promise> when done." --completion-promise "COMPLETE" --max-iterations 50
```

See [plugins/ralph/README.md](plugins/ralph/README.md) for detailed documentation.

## Scripts

### Git Safety Guard Installer (`install-claude-git-guard.sh`)

Installs a PreToolUse hook that blocks destructive git and filesystem commands to prevent accidental data loss.

**What it does:**
- Intercepts Bash commands before execution
- Blocks dangerous operations like `git reset --hard`, `git push --force`, `rm -rf`, etc.
- Prevents Claude from running destructive commands without explicit user confirmation
- Can be installed per-project or globally

**Usage:**
```bash
# Install in current project (.claude/)
./install-claude-git-guard.sh

# Install globally (~/.claude/)
./install-claude-git-guard.sh --global
```

**Blocked operations:**
- `git reset --hard` - Loss of uncommitted changes
- `git push --force` - Rewriting remote history
- `git clean -fd` - Deleting untracked files
- `rm -rf` - Recursive deletion
- And more...

The hook is currently active in this project (see `.claude/settings.json` and `.claude/hooks/git_safety_guard.py`).

## Hooks

Hooks allow you to execute custom code in response to Claude Code events.

### Currently Active Hooks

**Git Safety Guard** (`.claude/hooks/git_safety_guard.py`)
- **Type:** PreToolUse hook (Bash commands)
- **Purpose:** Blocks destructive git/filesystem operations
- **Installed by:** `install-claude-git-guard.sh`
- **Configuration:** See `.claude/settings.json`

### Hook Types Available

Claude Code supports several hook types:
- **PreToolUse** - Runs before a tool is executed (can block execution)
- **PostToolUse** - Runs after a tool completes
- **UserPromptSubmit** - Runs when user submits a message
- **Stop** - Runs when Claude tries to exit a session

For more information on creating custom hooks, see the [Claude Code documentation](https://github.com/anthropics/claude-code).

## Skills

> **Placeholder for custom skills**
>
> Skills are user-invocable commands (like `/commit` or `/review-pr`) that expand into full prompts when executed.
>
> To add custom skills:
> 1. Create skill files in `.claude/skills/`
> 2. Define skill prompts and parameters
> 3. Invoke with `/skill-name` in Claude Code
>
> See the [Claude Code Skills documentation](https://github.com/anthropics/claude-code) for examples and API reference.

## Getting Started

1. **Install the Git Safety Guard** (if not already installed):
   ```bash
   ./install-claude-git-guard.sh
   ```

2. **Install the Ralph Wiggum plugin** (if not already installed):
   - The plugin is already present in `plugins/ralph/`
   - Configure in your Claude Code settings if needed

3. **Customize hooks and skills** as needed for your workflow

## Configuration

Main configuration file: `.claude/settings.json`

This file defines:
- Active hooks and their matchers
- Plugin settings
- Custom skill paths
- Other Claude Code preferences

## Resources

- [Claude Code Documentation](https://github.com/anthropics/claude-code)
- [Ralph Wiggum Technique](https://ghuntley.com/ralph/)
- [Ralph Orchestrator](https://github.com/mikeyobrien/ralph-orchestrator)

## Contributing

To add new plugins, scripts, or hooks:
1. Add your files to the appropriate directory
2. Update this README with documentation
3. Include examples and usage instructions
4. Test thoroughly before committing
