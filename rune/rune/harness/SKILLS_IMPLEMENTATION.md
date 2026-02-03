# Skills System Implementation

## Overview

Implemented a Codex-inspired skills system for Rune that allows loading specialized instructions from `SKILL.md` files.

## Key Components

### 1. Skills Manager (`rune/harness/skills.py`)

**Core Classes:**
- `Skill` - Dataclass representing a skill with name, description, path, and optional short_description
- `SkillMention` - Tracks explicit skill mentions in user input ($skill-name or [$skill-name](path))
- `SkillsManager` - Main class managing skill discovery, loading, and injection

**Key Features:**
- **Progressive Disclosure**: Skills list always in prompt, full content loaded on-demand
- **Multi-root Discovery**: Scans `.agents/skills`, `.codex/skills`, `skills/`, and user-level directories
- **Caching**: Discovered skills are cached for performance
- **Depth Limiting**: Scans up to 6 levels deep to prevent excessive recursion
- **Hidden Directory Filtering**: Skips directories starting with `.`
- **Deduplication**: Same skill found in multiple locations only loaded once

### 2. Skill File Format

```markdown
---
name: skill-name
description: Full description of what this skill does
short_description: Brief version (optional)
---

# Skill Instructions

Markdown content with instructions for the agent...
```

**Constraints:**
- Name: max 64 characters
- Description: max 1024 characters
- Valid YAML frontmatter required

### 3. Skill Activation

**Two methods:**
1. **Plain mention**: `$skill-name`
2. **Linked mention**: `[$skill-name](path/to/SKILL.md)`

When mentioned, full SKILL.md content is injected as a system message for that turn only.

### 4. Integration with Agent

The `Agent` class (in `agent.py`) automatically:
1. Renders skills list in system prompt via `render_skills_section()`
2. Injects mentioned skills per-turn via `apply_turn_injections()`

### 5. Test Coverage

**41 comprehensive tests** covering:
- Skill discovery from multiple roots
- Frontmatter parsing (valid, invalid, missing fields)
- Mention extraction (plain, linked, mixed)
- Skill resolution by name and path
- Skills rendering for prompt
- Caching behavior
- Edge cases (hidden dirs, depth limits, malformed files)

## Usage Example

```python
from rune.harness.skills import SkillsManager

# Initialize
manager = SkillsManager("/path/to/workspace")

# Discover skills
skills = manager.discover_skills()

# Render for system prompt
section = manager.render_skills_section()

# Extract mentions from user input
mention = manager.extract_mentions("Use $my-skill for this")
mentioned_skills = manager.get_skills_for_mentions(mention)

# Load skill content
content = manager.load_skill_content(mentioned_skills[0])
```

## Files Created/Modified

1. **rune/harness/skills.py** - Complete implementation (440 lines)
2. **rune/tests/__init__.py** - Test package initialization
3. **rune/tests/test_skills.py** - Comprehensive test suite (791 lines, 41 tests)
4. **pyproject.toml** - Added PyYAML dependency

## Design Principles

Based on OpenAI Codex implementation:
1. **Context efficiency** - Only load what's needed
2. **Progressive disclosure** - List → SKILL.md → References
3. **Explicit activation** - Skills don't auto-inject
4. **Per-turn scope** - Skills reset each turn unless re-mentioned
5. **Graceful degradation** - Invalid skills are skipped silently

## Next Steps

To use the skills system:
1. Create skills in `.agents/skills/` or `skills/` directories
2. Format them with proper YAML frontmatter
3. Mention them with `$skill-name` in user messages
4. The agent will automatically load and follow their instructions
