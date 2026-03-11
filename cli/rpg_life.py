#!/usr/bin/env python3
import click
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import os
from dotenv import load_dotenv

load_dotenv()

console = Console()
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_PREFIX = os.getenv("API_PREFIX", "/api")
USER_ID = os.getenv("USER_ID", "")


class RPGLifeAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{API_PREFIX}{path}"

    @staticmethod
    def _raise_if_no_user() -> None:
        if not USER_ID:
            raise RuntimeError("USER_ID is not set. Configure it in cli/.env.")

    def submit_journal(self, text: str) -> dict:
        """Submit journal entry"""
        self._raise_if_no_user()
        response = self.session.post(
            self._url("/journal/entries"), json={"user_id": USER_ID, "raw_text": text}
        )
        response.raise_for_status()
        return response.json()

    def get_user_stats(self) -> dict:
        """Get user statistics"""
        self._raise_if_no_user()
        response = self.session.get(self._url(f"/users/{USER_ID}/stats"))
        response.raise_for_status()
        return response.json()

    def get_skills(self) -> list:
        """Get user skills"""
        self._raise_if_no_user()
        response = self.session.get(self._url("/skills"), params={"user_id": USER_ID})
        response.raise_for_status()
        return response.json()

    def get_quests(self, status: str = None) -> list:
        """Get user quests"""
        self._raise_if_no_user()
        params = {"user_id": USER_ID}
        if status:
            params["status"] = status

        response = self.session.get(self._url("/quests"), params=params)
        response.raise_for_status()
        return response.json()


api = RPGLifeAPI(API_BASE_URL)


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """RPG Life Tracker CLI - Level up in real life! 🎮"""
    pass


@cli.command()
@click.option("--editor", is_flag=True, help="Open text editor for entry")
def submit(editor):
    """Submit a journal entry"""

    if editor:
        text = click.edit("# Today I practiced...\n\n")
        if not text:
            console.print("[red]No entry provided[/red]")
            return
    else:
        console.print(
            "[bold cyan]Enter your journal entry (Ctrl+D when done):[/bold cyan]"
        )
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        text = "\n".join(lines)

    if not text.strip():
        console.print("[red]Entry cannot be empty[/red]")
        return

    # Submit
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Submitting entry...", total=None)

        try:
            result = api.submit_journal(text)
            progress.update(task, completed=True)

            console.print(
                Panel(
                    "[green]✓ Entry submitted successfully![/green]\n"
                    f"Entry ID: {result.get('entry_id', 'N/A')}\n"
                    f"Status: {result.get('status', 'Processing')}\n"
                    "\n[dim]Processing in background...[/dim]",
                    title="Success",
                    border_style="green",
                )
            )
        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")


@cli.command()
def status():
    """Show current status and XP"""

    try:
        stats = api.get_user_stats()

        # Create status panel
        status_text = f"""
[bold]Level {stats['current_level']}[/bold]
Total XP: [cyan]{stats['total_xp']:,}[/cyan]
Current Level XP: {stats['current_level_xp']:,} / {stats['next_level_xp']:,}

[bold]Statistics[/bold]
Active Quests: {stats['active_quests']}
Skills Practiced: {stats['skills_practiced']}
Journal Entries: {stats['journal_entries']}
Current Streak: [yellow]{stats['current_streak']} days[/yellow] 🔥
        """

        console.print(
            Panel(
                status_text.strip(),
                title="[bold]RPG Life Status[/bold]",
                border_style="cyan",
            )
        )

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")


@cli.command()
@click.option("--limit", "-n", default=10, help="Number of skills to show")
@click.option(
    "--sort", default="xp", type=click.Choice(["xp", "level", "name"]), help="Sort by"
)
def skills(limit, sort):
    """List all skills"""

    try:
        skills_data = api.get_skills()

        # Sort
        if sort == "xp":
            skills_data = sorted(skills_data, key=lambda s: s["total_xp"], reverse=True)
        elif sort == "level":
            skills_data = sorted(
                skills_data, key=lambda s: s["current_level"], reverse=True
            )
        else:  # name
            skills_data = sorted(skills_data, key=lambda s: s["canonical_name"])

        # Limit
        skills_data = skills_data[:limit]

        # Create table
        table = Table(
            title=f"Top {len(skills_data)} Skills",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Skill", style="white")
        table.add_column("Category", style="dim")
        table.add_column("Level", justify="right", style="magenta")
        table.add_column("Total XP", justify="right", style="cyan")

        for skill in skills_data:
            table.add_row(
                skill["canonical_name"],
                skill["category"],
                str(skill["current_level"]),
                f"{skill['total_xp']:,}",
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")


@cli.command()
@click.option(
    "--status",
    default="active",
    type=click.Choice(["active", "completed", "all"]),
    help="Filter by status",
)
def quests(status):
    """List quests"""

    try:
        quest_status = None if status == "all" else status
        quests_data = api.get_quests(quest_status)

        # Create table
        table = Table(
            title=f"{status.capitalize()} Quests",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Quest", style="white")
        table.add_column("Type", style="dim")
        table.add_column("Progress", justify="right", style="cyan")
        table.add_column("Status", style="green")

        for quest in quests_data:
            progress_text = (
                f"{quest.get('current_value', 0)}/{quest.get('target_value', 0)}"
            )
            status_emoji = "✓" if quest["status"] == "completed" else "→"

            table.add_row(
                quest["quest_name"],
                quest["quest_type"],
                progress_text,
                f"{status_emoji} {quest['status']}",
            )

        console.print(table)

        if not quests_data:
            console.print(f"[dim]No {status} quests found[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")


@cli.command()
def stats():
    """Show detailed statistics"""

    try:
        stats = api.get_user_stats()
        skills_data = api.get_skills()
        quests_data = api.get_quests()

        # Overview
        console.print(
            Panel(
                f"[bold]Level {stats['current_level']}[/bold] | "
                f"[cyan]{stats['total_xp']:,} XP[/cyan] | "
                f"[yellow]{stats['current_streak']} day streak[/yellow]",
                title="Overview",
                border_style="cyan",
            )
        )

        # Skills breakdown
        console.print("\n[bold]Skills by Category:[/bold]")
        categories = {}
        for skill in skills_data:
            cat = skill["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(skill)

        for cat, cat_skills in categories.items():
            total_xp = sum(s["total_xp"] for s in cat_skills)
            console.print(f"  {cat}: {len(cat_skills)} skills, {total_xp:,} XP")

        # Quests breakdown
        console.print("\n[bold]Quests:[/bold]")
        active = len([q for q in quests_data if q["status"] == "active"])
        completed = len([q for q in quests_data if q["status"] == "completed"])
        console.print(f"  Active: {active}")
        console.print(f"  Completed: {completed}")

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")


if __name__ == "__main__":
    cli()
