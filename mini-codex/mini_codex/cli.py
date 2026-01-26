"""Command-line interface for Mini Codex."""

import argparse
import os
import sys

from .agent import Agent, AgentConfig


def print_colored(text: str, color: str) -> None:
    """Print text with ANSI color codes."""
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "red": "\033[91m",
        "cyan": "\033[96m",
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m"
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")


def print_tool_call(name: str, args: dict) -> None:
    """Print a tool call in a formatted way."""
    print_colored(f"\n[Tool: {name}]", "cyan")
    for key, value in args.items():
        if len(str(value)) > 100:
            value = str(value)[:100] + "..."
        print_colored(f"  {key}: {value}", "dim")


def print_tool_result(result, name: str) -> None:
    """Print a tool result in a formatted way."""
    if result.success:
        print_colored(f"[{name} completed]", "green")
        if result.output:
            # Truncate long outputs
            output = result.output
            if len(output) > 500:
                output = output[:500] + f"\n... ({len(result.output) - 500} more characters)"
            print(output)
    else:
        print_colored(f"[{name} failed: {result.error}]", "red")


def run_interactive(agent: Agent) -> None:
    """Run the agent in interactive REPL mode."""
    print_colored("Mini Codex - Interactive Mode", "bold")
    print_colored(f"Working directory: {agent.working_dir}", "dim")
    print_colored("Type 'exit' or 'quit' to leave, 'reset' to clear history\n", "dim")

    while True:
        try:
            user_input = input("\033[94m> \033[0m").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        if user_input.lower() == "reset":
            agent.reset()
            print_colored("Session reset.", "yellow")
            continue

        if user_input.lower() == "history":
            for msg in agent.session.messages:
                print_colored(f"[{msg.role}]", "cyan")
                if msg.content:
                    print(msg.content[:200] + "..." if len(msg.content or "") > 200 else msg.content)
            continue

        # Run the agent loop
        try:
            for turn in agent.run(user_input):
                # Print tool calls and results
                for i, tool_call in enumerate(turn.tool_calls):
                    import json
                    args = json.loads(tool_call["function"]["arguments"])
                    print_tool_call(tool_call["function"]["name"], args)
                    if i < len(turn.tool_results):
                        print_tool_result(turn.tool_results[i], tool_call["function"]["name"])

                # Print final response
                if turn.finished and turn.response:
                    print_colored("\n" + turn.response, "green")
        except Exception as e:
            print_colored(f"Error: {e}", "red")


def run_single(agent: Agent, prompt: str) -> None:
    """Run the agent with a single prompt."""
    for turn in agent.run(prompt):
        # Print tool calls and results
        for i, tool_call in enumerate(turn.tool_calls):
            import json
            args = json.loads(tool_call["function"]["arguments"])
            print_tool_call(tool_call["function"]["name"], args)
            if i < len(turn.tool_results):
                print_tool_result(turn.tool_results[i], tool_call["function"]["name"])

        # Print final response
        if turn.finished and turn.response:
            print(turn.response)


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Mini Codex - A minimal coding agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mini-codex                         # Interactive mode in current directory
  mini-codex -d /path/to/project     # Interactive mode in specific directory
  mini-codex -p "list all files"     # Single prompt mode
  mini-codex --model gpt-4o-mini     # Use a different model
"""
    )

    parser.add_argument(
        "-d", "--directory",
        default=os.getcwd(),
        help="Working directory for the agent (default: current directory)"
    )

    parser.add_argument(
        "-p", "--prompt",
        help="Single prompt to run (non-interactive mode)"
    )

    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o)"
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature for model responses (default: 0.0)"
    )

    parser.add_argument(
        "--max-turns",
        type=int,
        default=50,
        help="Maximum agent loop iterations (default: 50)"
    )

    parser.add_argument(
        "--no-auto-approve",
        action="store_true",
        help="Require confirmation for tool execution"
    )

    args = parser.parse_args()

    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: {args.directory} is not a valid directory", file=sys.stderr)
        sys.exit(1)

    # Create agent config
    config = AgentConfig(
        model=args.model,
        temperature=args.temperature,
        max_turns=args.max_turns,
        auto_approve_tools=not args.no_auto_approve
    )

    # Approval callback if needed
    def approval_callback(tool_name: str, tool_id: str, arguments: dict) -> bool:
        print_colored(f"\nTool request: {tool_name}", "yellow")
        for key, value in arguments.items():
            print(f"  {key}: {value}")
        response = input("Approve? [y/N] ").strip().lower()
        return response in ("y", "yes")

    # Create agent
    agent = Agent(
        working_dir=args.directory,
        config=config,
        approval_callback=approval_callback if not config.auto_approve_tools else None
    )

    # Run in appropriate mode
    if args.prompt:
        run_single(agent, args.prompt)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
