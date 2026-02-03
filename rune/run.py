#!/usr/bin/env python3
"""
Legacy entry point - use 'rune' command instead.

After installing: pip install -e .
Run: rune --help
"""
import sys

print("Note: Use 'rune' command instead of 'python run.py'")
print()
print("Examples:")
print("  rune                    # Interactive mode")
print("  rune -p 'task'          # Single prompt")
print("  rune --agent plan       # Read-only agent")
print()
print("Run 'rune --help' for more options")
print()

# Still run the CLI if called directly
if __name__ == "__main__":
    from rune.cli import main
    main()
