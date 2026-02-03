"""Command-line interface for Rune."""

import argparse
import json
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from rune.harness.agent import Agent, AgentConfig
from rune.agents import list_agents

console = Console()


def print_tool_call(name: str, args: dict, agent_name: str = "") -> None:
    """Print a tool call with Rich formatting."""
    prefix = f"[{agent_name}] " if agent_name else ""
    console.print(f"\n{prefix}[cyan bold]Tool:[/cyan bold] {name}")
    for key, value in args.items():
        if len(str(value)) > 100:
            value = str(value)[:100] + "..."
        console.print(f"  [dim]{key}:[/dim] {value}")


def print_tool_result(result, name: str) -> None:
    """Print a tool result with Rich formatting."""
    if result.success:
        console.print(f"[green]✓ {name} completed[/green]")
        if result.output:
            output = result.output
            if len(output) > 500:
                output = output[:500] + f"\n... ({len(result.output) - 500} more characters)"
            console.print(output)
    else:
        console.print(f"[red]✗ {name} failed: {result.error}[/red]")


def run_interactive(agent: Agent) -> None:
    """Run the agent in interactive REPL mode."""
    # Print header
    console.print(Panel.fit(
        f"[bold cyan]Rune[/bold cyan] - Interactive Mode\n"
        f"[dim]Agent:[/dim] {agent.agent_def.name} | [dim]Model:[/dim] {agent.config.model}\n"
        f"[dim]Directory:[/dim] {agent.working_dir}",
        title="Welcome",
        border_style="cyan"
    ))
    console.print("[dim]Commands: exit, reset, history, switch <agent>, agents, status[/dim]\n")

    while True:
        try:
            prompt_char = {"build": "#", "plan": "?"}.get(agent.agent_def.name, ">")
            user_input = console.input(f"[blue]{agent.agent_def.name} {prompt_char}[/blue] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Goodbye![/yellow]")
            agent.shutdown()
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            console.print("[yellow]Goodbye![/yellow]")
            agent.shutdown()
            break

        if user_input.lower() == "reset":
            agent.reset()
            console.print("[yellow]Session reset.[/yellow]")
            continue

        if user_input.lower() == "history":
            table = Table(title="Conversation History", show_header=True, header_style="bold cyan")
            table.add_column("Role", style="cyan")
            table.add_column("Content")

            for msg in agent.session.messages:
                content = msg.content or ""
                if len(content) > 200:
                    content = content[:200] + "..."
                table.add_row(msg.role, content)

            console.print(table)
            continue

        if user_input.lower() == "status":
            stats = agent.session
            panel = Panel(
                f"[cyan]Session:[/cyan] {stats.session_id}\n"
                f"[cyan]Turns:[/cyan] {stats.turn_count}\n"
                f"[cyan]Messages:[/cyan] {len(stats.messages)}\n"
                f"[cyan]Tokens:[/cyan] {stats.usage.total_tokens} "
                f"(prompt: {stats.usage.prompt_tokens}, completion: {stats.usage.completion_tokens})\n"
                f"[cyan]Working Dir:[/cyan] {stats.working_dir}",
                title="Agent Status",
                border_style="blue"
            )
            console.print(panel)
            continue

        if user_input.lower() == "agents":
            table = Table(title="Available Agents", show_header=True, header_style="bold cyan")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            table.add_column("Current", justify="center")

            for ag in list_agents():
                marker = "✓" if ag.name == agent.agent_def.name else ""
                table.add_row(ag.name, ag.description, marker)

            console.print(table)
            continue

        if user_input.lower().startswith("switch "):
            new_name = user_input.split(None, 1)[1].strip()
            try:
                agent.switch_agent(new_name)
                console.print(f"[yellow]Switched to {new_name} agent.[/yellow]")
            except ValueError as e:
                console.print(f"[red]{e}[/red]")
            continue

        # Run the agent loop
        try:
            for turn in agent.stream(user_input):
                for i, tool_call in enumerate(turn.tool_calls):
                    args = json.loads(tool_call["function"]["arguments"])
                    print_tool_call(tool_call["function"]["name"], args, turn.agent_name)
                    if i < len(turn.tool_results):
                        print_tool_result(turn.tool_results[i], tool_call["function"]["name"])

                if turn.finished and turn.response:
                    console.print(f"\n[green]{turn.response}[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def run_single(agent: Agent, prompt: str) -> None:
    """Run the agent with a single prompt."""
    try:
        for turn in agent.stream(prompt):
            for i, tool_call in enumerate(turn.tool_calls):
                args = json.loads(tool_call["function"]["arguments"])
                print_tool_call(tool_call["function"]["name"], args, turn.agent_name)
                if i < len(turn.tool_results):
                    print_tool_result(turn.tool_results[i], tool_call["function"]["name"])

            if turn.finished and turn.response:
                console.print(turn.response)
    finally:
        agent.shutdown()


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Rune - A coding agent with harness features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  rune                              # Interactive build agent
  rune --agent plan                 # Interactive plan (read-only) agent
  rune -p "list all files"          # Single prompt mode
  rune --mcp-config mcp.json        # Load MCP tool servers
  rune --model gpt-5.2-2025-12-11   # Use a different model
""",
    )

    parser.add_argument("-p", "--prompt", help="Single prompt (non-interactive)")
    parser.add_argument("--model", default="gpt-5.2-2025-12-11", help="OpenAI model (default: gpt-4o)")
    parser.add_argument("--agent", default="build", choices=["build", "plan"],
                        help="Agent type (default: build)")
    parser.add_argument("--mcp-config", default=None,
                        help="Path to MCP server config JSON file")
    parser.add_argument("--no-auto-approve", action="store_true",
                        help="Require confirmation for tool execution")

    args = parser.parse_args()

    # Resolve MCP config path
    mcp_path = args.mcp_config
    if mcp_path and not os.path.isabs(mcp_path):
        mcp_path = os.path.abspath(mcp_path)

    config = AgentConfig(
        model=args.model,
        agent_name=args.agent,
        auto_approve_tools=not args.no_auto_approve,
        mcp_config_path=mcp_path,
    )

    def approval_callback(tool_name: str, tool_id: str, arguments: dict) -> bool:
        console.print(f"\n[yellow]Tool request: {tool_name}[/yellow]")
        for key, value in arguments.items():
            console.print(f"  {key}: {value}")
        response = console.input("[yellow]Approve? [y/N][/yellow] ").strip().lower()
        return response in ("y", "yes")

    agent = Agent(
        config=config,
        approval_callback=approval_callback if not config.auto_approve_tools else None,
    )

    if args.prompt:
        run_single(agent, args.prompt)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
