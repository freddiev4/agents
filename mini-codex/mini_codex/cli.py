"""Command-line interface for Mini Codex."""

import argparse
import os
import sys

from mini_codex.agent import Agent, AgentConfig
from mini_codex.agents import list_agents


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
        "dim": "\033[2m",
        "magenta": "\033[95m",
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")


def print_tool_call(name: str, args: dict, agent_name: str = "") -> None:
    """Print a tool call in a formatted way."""
    prefix = f"[{agent_name}] " if agent_name else ""
    print_colored(f"\n{prefix}[Tool: {name}]", "cyan")
    for key, value in args.items():
        if len(str(value)) > 100:
            value = str(value)[:100] + "..."
        print_colored(f"  {key}: {value}", "dim")


def print_tool_result(result, name: str) -> None:
    """Print a tool result in a formatted way."""
    if result.success:
        print_colored(f"[{name} completed]", "green")
        if result.output:
            output = result.output
            if len(output) > 500:
                output = output[:500] + f"\n... ({len(result.output) - 500} more characters)"
            print(output)
    else:
        print_colored(f"[{name} failed: {result.error}]", "red")


def run_interactive(agent: Agent) -> None:
    """Run the agent in interactive REPL mode."""
    print_colored("Mini Codex v0.2 - Interactive Mode", "bold")
    print_colored(f"Agent: {agent.agent_def.name} | Model: {agent.config.model}", "dim")
    print_colored(f"Working directory: {agent.working_dir}", "dim")
    print_colored("Commands: exit, reset, history, switch <agent>, agents, status\n", "dim")

    while True:
        try:
            prompt_char = {"build": "#", "plan": "?"}.get(agent.agent_def.name, ">")
            user_input = input(f"\033[94m{agent.agent_def.name} {prompt_char} \033[0m").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            agent.shutdown()
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            agent.shutdown()
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

        if user_input.lower() == "status":
            print_colored(agent.session.get_context_summary(), "dim")
            continue

        if user_input.lower() == "agents":
            for ag in list_agents():
                marker = " *" if ag.name == agent.agent_def.name else ""
                print_colored(f"  {ag.name}: {ag.description}{marker}", "dim")
            continue

        if user_input.lower().startswith("switch "):
            new_name = user_input.split(None, 1)[1].strip()
            try:
                agent.switch_agent(new_name)
                print_colored(f"Switched to {new_name} agent.", "yellow")
            except ValueError as e:
                print_colored(str(e), "red")
            continue

        # Run the agent loop
        try:
            for turn in agent.run(user_input):
                for i, tool_call in enumerate(turn.tool_calls):
                    import json
                    args = json.loads(tool_call["function"]["arguments"])
                    print_tool_call(tool_call["function"]["name"], args, turn.agent_name)
                    if i < len(turn.tool_results):
                        print_tool_result(turn.tool_results[i], tool_call["function"]["name"])

                if turn.finished and turn.response:
                    print_colored("\n" + turn.response, "green")
        except Exception as e:
            print_colored(f"Error: {e}", "red")


def run_single(agent: Agent, prompt: str) -> None:
    """Run the agent with a single prompt."""
    try:
        for turn in agent.run(prompt):
            for i, tool_call in enumerate(turn.tool_calls):
                import json
                args = json.loads(tool_call["function"]["arguments"])
                print_tool_call(tool_call["function"]["name"], args, turn.agent_name)
                if i < len(turn.tool_results):
                    print_tool_result(turn.tool_results[i], tool_call["function"]["name"])

            if turn.finished and turn.response:
                print(turn.response)
    finally:
        agent.shutdown()


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Mini Codex - A coding agent with harness features inspired by OpenCode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  mini-codex                              # Interactive build agent
  mini-codex --agent plan                 # Interactive plan (read-only) agent
  mini-codex -p "list all files"          # Single prompt mode
  mini-codex --mcp-config mcp.json        # Load MCP tool servers
  mini-codex --model gpt-4o-mini          # Use a different model
""",
    )

    parser.add_argument("-d", "--directory", default=os.getcwd(),
                        help="Working directory (default: current)")
    parser.add_argument("-p", "--prompt", help="Single prompt (non-interactive)")
    parser.add_argument("--model", default="gpt-5.2-2025-12-11", help="OpenAI model (default: gpt-4o)")
    parser.add_argument("--agent", default="build", choices=["build", "plan"],
                        help="Agent type (default: build)")
    parser.add_argument("--mcp-config", default=None,
                        help="Path to MCP server config JSON file")
    parser.add_argument("--no-auto-approve", action="store_true",
                        help="Require confirmation for tool execution")

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: {args.directory} is not a valid directory", file=sys.stderr)
        sys.exit(1)

    # Resolve MCP config path
    mcp_path = args.mcp_config
    if mcp_path and not os.path.isabs(mcp_path):
        mcp_path = os.path.join(args.directory, mcp_path)

    config = AgentConfig(
        model=args.model,
        agent_name=args.agent,
        auto_approve_tools=not args.no_auto_approve,
        mcp_config_path=mcp_path,
    )

    def approval_callback(tool_name: str, tool_id: str, arguments: dict) -> bool:
        print_colored(f"\nTool request: {tool_name}", "yellow")
        for key, value in arguments.items():
            print(f"  {key}: {value}")
        response = input("Approve? [y/N] ").strip().lower()
        return response in ("y", "yes")

    agent = Agent(
        working_dir=args.directory,
        config=config,
        approval_callback=approval_callback if not config.auto_approve_tools else None,
    )

    if args.prompt:
        run_single(agent, args.prompt)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
