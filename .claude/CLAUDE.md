# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with any project.

## Development Environment
Always `uv` to manage dependencies as well as work within a `virtualenv` for Python codebases. For example:

```bash
# initialize uv
uv init --no-workspace

# create a virtualenv
uv venv

# Activate virtual environment
source .venv/bin/activate

# install deps if exist
uv pip install -e .
```

For Typescript codebases, always use `bun`.

## Development Workflow
When making changes to any codebase, always be sure to make a new branch, add, and commit the changes, as well as push them up to GitHub. 

1. Check git status: `git status`
2. Review changes: `git diff`
3. Stage and commit changes with a descriptive message
4. Push to remote: `git push`

Always commit and push after completing a logical unit of work (e.g., implementing a feature, fixing a bug, refactoring code) rather than committing everything at once.

If the `gh` cli exists, then make a pull request with your changes.

## Subagents & Parallelizable Work

When working on independent tasks, try and use subagents to work on them rather than working on it all within the main chat context.

## Tracking Work
When starting any new piece of work, always make a `docs/[feature]/` folder. The folder should contain a `plan.md` file to track the planning, a `todo.md` for managing todos, and a `docs.md` for documentation about the feature such as setup, how it works, and references.
