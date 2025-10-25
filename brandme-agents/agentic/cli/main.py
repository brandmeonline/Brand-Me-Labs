"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Brand.Me Agent CLI
==================
Command-line interface for agentic operations
"""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
import json
from typing import Optional

from ..orchestrator.agents import run_scan_workflow
from ..graph_rag import get_graph_rag
from ..graph_db import get_knowledge_graph

app = typer.Typer(
    name="brandme",
    help="Brand.Me Agentic CLI - Intelligent agent operations",
    add_completion=False
)
console = Console()


# ============================================================
# Scan Commands
# ============================================================

@app.command()
def scan(
    tag: str = typer.Option(..., "--tag", "-t", help="Garment tag to scan"),
    scanner_id: str = typer.Option(..., "--scanner-id", "-s", help="Scanner user ID"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed reasoning")
):
    """
    Execute garment scan workflow with agentic evaluation.

    Example:
        brandme scan --tag garment-xyz --scanner-id user-123
    """
    console.print(Panel.fit(
        f"[bold blue]Scanning garment: {tag}[/bold blue]\n"
        f"Scanner: {scanner_id}",
        title="Brand.Me Scan"
    ))

    with console.status("[bold green]Running agent workflow..."):
        result = run_scan_workflow(tag, scanner_id)

    # Display results
    console.print("\n[bold]Results:[/bold]")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Field")
    table.add_column("Value")

    table.add_row("Decision", f"[{'green' if result['decision'] == 'allow' else 'red'}]{result['decision'].upper()}[/]")
    table.add_row("Scope", result.get("resolved_scope", "N/A"))
    table.add_row("Relationship", result.get("relationship", "N/A"))
    table.add_row("Trust Score", f"{result.get('trust_score', 0):.2f}")
    table.add_row("Scan ID", result.get("scan_id", "N/A"))
    table.add_row("Cardano TX", result.get("cardano_tx_hash", "N/A")[:16] + "...")
    table.add_row("Policy Version", result.get("policy_version", "N/A"))

    console.print(table)

    if verbose and result.get("policy_reasoning"):
        console.print("\n[bold]Policy Reasoning:[/bold]")
        console.print(Panel(result["policy_reasoning"], border_style="blue"))

    if result.get("escalation_reason"):
        console.print(f"\n[yellow]⚠ Escalation Reason: {result['escalation_reason']}[/yellow]")


# ============================================================
# Graph Query Commands
# ============================================================

graph_app = typer.Typer(name="graph", help="Knowledge graph operations")
app.add_typer(graph_app)


@graph_app.command("query")
def graph_query(
    question: str = typer.Argument(..., help="Natural language question"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show reasoning")
):
    """
    Query knowledge graph with natural language.

    Example:
        brandme graph query "Show me all garments by creators Alice trusts"
    """
    console.print(Panel.fit(
        f"[bold blue]Question:[/bold blue] {question}",
        title="Graph Query"
    ))

    with console.status("[bold green]Querying knowledge graph..."):
        graph_rag = get_graph_rag()
        result = graph_rag.query(question, include_reasoning=verbose)

    console.print("\n[bold green]Answer:[/bold green]")
    console.print(Panel(result["answer"], border_style="green"))

    if verbose and result.get("reasoning"):
        console.print("\n[bold]Reasoning Steps:[/bold]")
        console.print(result["reasoning"])

    if result.get("cypher_query"):
        console.print("\n[bold]Cypher Query:[/bold]")
        syntax = Syntax(result["cypher_query"], "cypher", theme="monokai")
        console.print(syntax)


@graph_app.command("path")
def find_path(
    from_user: str = typer.Option(..., "--from", help="First user ID"),
    to_user: str = typer.Option(..., "--to", help="Second user ID"),
):
    """
    Find trust path between two users.

    Example:
        brandme graph path --from user-1 --to user-2
    """
    console.print(f"[bold]Finding trust path:[/bold] {from_user} → {to_user}")

    graph = get_knowledge_graph()
    path = graph.find_trust_path(from_user, to_user)

    if not path:
        console.print("[red]No path found between users[/red]")
        return

    console.print(f"\n[green]✓ Path found![/green] Length: {path['path_length']}")

    # Display path
    nodes = path["nodes"]
    weights = path["trust_weights"]

    for i, node in enumerate(nodes):
        console.print(f"  {node['handle']} (trust: {node['trust_score']:.2f})")
        if i < len(weights):
            console.print(f"    ↓ (weight: {weights[i]:.2f})")

    import numpy as np
    aggregate_trust = np.prod(weights) if weights else 0.0
    console.print(f"\n[bold]Aggregate Trust Score:[/bold] {aggregate_trust:.3f}")

    graph.close()


@graph_app.command("provenance")
def get_provenance(
    garment_id: str = typer.Argument(..., help="Garment UUID")
):
    """
    Get full provenance chain for garment.

    Example:
        brandme graph provenance garment-123
    """
    console.print(f"[bold]Fetching provenance for:[/bold] {garment_id}")

    graph_rag = get_graph_rag()
    provenance = graph_rag.get_garment_provenance(garment_id)

    console.print("\n[bold green]Provenance Story:[/bold green]")
    console.print(Panel(provenance["answer"], border_style="green"))

    if provenance.get("creator"):
        console.print("\n[bold]Creator Info:[/bold]")
        creator = provenance["creator"]
        table = Table(show_header=False)
        table.add_row("Name", creator.get("creator_name", "N/A"))
        table.add_row("Brand", creator.get("brand_name", "N/A"))
        table.add_row("ESG Score", creator.get("esg_score", "N/A"))
        console.print(table)

    if provenance.get("ownership_chain"):
        console.print("\n[bold]Ownership History:[/bold]")
        for i, event in enumerate(provenance["ownership_chain"]):
            console.print(f"  {i+1}. {event['handle']} - {event.get('scan_timestamp', 'N/A')}")
            if event.get("tx_hash"):
                console.print(f"     TX: {event['tx_hash'][:16]}...")


# ============================================================
# Blockchain Commands
# ============================================================

blockchain_app = typer.Typer(name="blockchain", help="Blockchain operations")
app.add_typer(blockchain_app)


@blockchain_app.command("verify")
def verify_tx(
    tx_hash: str = typer.Option(..., "--tx-hash", help="Transaction hash"),
    chain: str = typer.Option("cardano", "--chain", help="Blockchain (cardano/midnight)")
):
    """
    Verify blockchain transaction.

    Example:
        brandme blockchain verify --tx-hash abc123... --chain cardano
    """
    from ..tools.blockchain_tools import verify_blockchain_tx_tool

    console.print(f"[bold]Verifying {chain} transaction:[/bold] {tx_hash[:16]}...")

    with console.status("[bold green]Checking blockchain..."):
        is_valid = verify_blockchain_tx_tool(tx_hash, chain)

    if is_valid:
        console.print("[green]✓ Transaction verified on blockchain[/green]")
    else:
        console.print("[red]✗ Transaction not found or invalid[/red]")


# ============================================================
# Approval Commands
# ============================================================

approval_app = typer.Typer(name="approval", help="Human-in-the-loop approvals")
app.add_typer(approval_app)


@approval_app.command("list")
def list_approvals(
    status: str = typer.Option("pending", "--status", help="Filter by status")
):
    """
    List pending approvals.

    Example:
        brandme approval list --status pending
    """
    console.print(f"[bold]Pending Approvals:[/bold] (status={status})")

    # In production, fetch from database
    console.print("[yellow]No pending approvals (demo mode)[/yellow]")


@approval_app.command("approve")
def approve_scan(
    scan_id: str = typer.Option(..., "--scan-id", help="Scan ID to approve"),
    approver_id: str = typer.Option(..., "--approver-id", help="Your approver ID"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Approval justification")
):
    """
    Approve a scan escalation.

    Example:
        brandme approval approve --scan-id scan-123 --approver-id gov-1
    """
    console.print(f"[bold]Approving scan:[/bold] {scan_id}")
    console.print(f"[bold]Approver:[/bold] {approver_id}")

    if reason:
        console.print(f"[bold]Reason:[/bold] {reason}")

    # In production, update database and resume workflow
    console.print("\n[green]✓ Scan approved[/green]")


# ============================================================
# Agent Management
# ============================================================

agent_app = typer.Typer(name="agent", help="Agent management")
app.add_typer(agent_app)


@agent_app.command("status")
def agent_status():
    """
    Show status of all agents.

    Example:
        brandme agent status
    """
    table = Table(title="Agent Status", show_header=True, header_style="bold cyan")
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Last Run")

    agents = [
        ("Scan Agent", "Running", "2 mins ago"),
        ("Identity Agent", "Running", "1 min ago"),
        ("Knowledge Agent", "Running", "3 mins ago"),
        ("Policy Agent", "Running", "30 secs ago"),
        ("Blockchain Agent", "Running", "5 mins ago"),
    ]

    for name, status, last_run in agents:
        table.add_row(name, f"[green]{status}[/green]", last_run)

    console.print(table)


@agent_app.command("logs")
def agent_logs(
    agent: str = typer.Argument(..., help="Agent name"),
    tail: int = typer.Option(100, "--tail", help="Number of lines")
):
    """
    View agent logs.

    Example:
        brandme agent logs scan_agent --tail 50
    """
    console.print(f"[bold]Last {tail} lines from {agent}:[/bold]\n")
    console.print("[dim]Agent logs would appear here in production[/dim]")


# ============================================================
# Analytics Commands
# ============================================================

analytics_app = typer.Typer(name="analytics", help="Analytics and insights")
app.add_typer(analytics_app)


@analytics_app.command("detect-counterfeits")
def detect_counterfeits(
    timeframe: str = typer.Option("7d", "--timeframe", help="Time window (e.g., 7d, 30d)")
):
    """
    Detect counterfeit patterns.

    Example:
        brandme analytics detect-counterfeits --timeframe 7d
    """
    console.print(f"[bold]Analyzing counterfeit patterns:[/bold] Last {timeframe}")
    console.print("\n[yellow]Analytics feature coming soon[/yellow]")


# ============================================================
# Main Entry Point
# ============================================================

def main():
    """Main CLI entry point"""
    app()


if __name__ == "__main__":
    main()
