---
name: example-skill
description: A demonstration skill showing how the Rune skills system works
short_description: Demo skill for testing
---

# Example Skill

This is a demonstration skill that shows how the Rune skills system works.

## What This Skill Does

When this skill is activated (by mentioning `$example-skill` in a message), this entire document is injected into the agent's context for that turn only.

## Instructions

When using this skill, you should:

1. **Acknowledge activation** - Let the user know this skill has been loaded
2. **Follow these guidelines** - Explain that this is just a demo
3. **Show the format** - Demonstrate that skills can include:
   - Structured instructions
   - Code examples
   - Links to other resources
   - Best practices

## Example Code

```python
# Skills can include code snippets
def example_function():
    print("This skill is active!")
```

## Best Practices

- Skills should be focused and specific
- Keep instructions clear and actionable
- Use markdown for formatting
- Include examples when helpful

## Progressive Disclosure

Skills can reference other files in the skill directory:
- `./scripts/helper.py` - Helper scripts
- `./docs/detailed.md` - Detailed documentation
- `./examples/` - Example files

The agent should only load these if actually needed for the task.

## Scope

Remember: This skill is only active for the current turn. If the user wants to use it again in a future message, they must mention it again.
