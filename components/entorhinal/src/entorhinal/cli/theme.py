"""Hermes / OpenClaw-grade UI/UX theme, styles, banners, and formatters for Entorhinal CLI on Windows 11."""

from __future__ import annotations

import sys
from typing import Optional
from prompt_toolkit.styles import Style as PromptToolkitStyle
from questionary import Style as QuestionaryStyle
from rich.box import ROUNDED, DOUBLE
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# Color Palette Constants
COLOR_CYAN = "#00E5FF"
COLOR_GREEN = "#00FF88"
COLOR_PURPLE = "#BD00FF"
COLOR_AMBER = "#FFD600"
COLOR_SLATE = "#718096"
COLOR_DARK_BORDER = "#2D3748"
COLOR_WHITE = "#F7FAFC"
COLOR_RED = "#FF4B4B"

# Unicode Glyphs with Windows CMD Fallback
IS_WINDOWS = sys.platform == "win32"
POINTER_GLYPH = "❯"
CHECKED_GLYPH = "✔"
UNCHECKED_GLYPH = "○"
BULLET_GLYPH = "◆"
SPARKLE_GLYPH = "✦"

# Questionary Interactive Theme Style
QUESTIONARY_THEME = QuestionaryStyle([
    ("qmark", "fg:#00E5FF bold"),
    ("question", "fg:#F7FAFC bold"),
    ("answer", "fg:#00FF88 bold"),
    ("pointer", "fg:#00E5FF bold"),
    ("highlighted", "fg:#00E5FF bold"),
    ("selected", "fg:#00FF88 bold"),
    ("separator", "fg:#718096"),
    ("instruction", "fg:#718096 italic"),
    ("text", "fg:#F7FAFC"),
    ("disabled", "fg:#4A5568 italic"),
])


ASCII_BANNER = r"""
 [bold #00E5FF]███████╗███╗   ██╗████████╗ ██████╗ ██████╗ ██╗  ██╗██╗███╗   ██╗ █████╗ ██╗     [/bold #00E5FF]
 [bold #00E5FF]██╔════╝████╗  ██║╚══██╔══╝██╔═══██╗██╔══██╗██║  ██║██║████╗  ██║██╔══██╗██║     [/bold #00E5FF]
 [bold #00D4FF]█████╗  ██╔██╗ ██║   ██║   ██║   ██║██████╔╝███████║██║██╔██╗ ██║███████║██║     [/bold #00D4FF]
 [bold #00B4D8]██╔══╝  ██║╚██╗██║   ██║   ██║   ██║██╔══██╗██╔══██║██║██║╚██╗██║██╔══██║██║     [/bold #00B4D8]
 [bold #0096C7]███████╗██║ ╚████║   ██║   ╚██████╔╝██║  ██║██║  ██║██║██║ ╚████║██║  ██║███████╗[/bold #0096C7]
 [dim #718096]╚══════╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝[/dim #718096]
"""

TAGLINE = "[bold #00E5FF]LOCAL CONTEXT ENGINE[/bold #00E5FF] [dim]•[/dim] [italic white]Deterministic Privacy, Zero Action Authority & Hybrid AI[/italic white]"


def print_banner() -> None:
    """Print the Hermes / OpenClaw-grade Entorhinal header banner."""
    console.print(ASCII_BANNER)
    console.print(Panel(
        f"{TAGLINE}\n[dim]Windows 11 Local-First Architecture • Named Pipe \\\\.\\pipe\\entorhinal_vnext[/dim]",
        border_style="#00E5FF",
        box=ROUNDED,
        padding=(0, 2),
    ))
    console.print()


def render_step_header(step_num: int, total_steps: int, title: str, subtitle: Optional[str] = None) -> None:
    """Render a step progress badge with a sleek separator panel."""
    badge = f"[bold #BD00FF]Step {step_num}/{total_steps}[/bold #BD00FF]"
    header_text = f"{badge}  [bold white]{title.upper()}[/bold white]"
    if subtitle:
        header_text += f"\n[dim #718096]{subtitle}[/dim #718096]"

    console.print(Panel(
        header_text,
        border_style="#BD00FF",
        box=ROUNDED,
        padding=(0, 1),
    ))
    console.print()


def render_success_card(title: str, message: str) -> None:
    """Render an emerald success status card."""
    content = f"[bold #00FF88]{CHECKED_GLYPH} {title}[/bold #00FF88]\n[white]{message}[/white]"
    console.print(Panel(content, border_style="#00FF88", box=ROUNDED, padding=(0, 2)))
    console.print()


def render_warning_card(title: str, message: str) -> None:
    """Render an amber warning status card."""
    content = f"[bold #FFD600]⚠ {title}[/bold #FFD600]\n[white]{message}[/white]"
    console.print(Panel(content, border_style="#FFD600", box=ROUNDED, padding=(0, 2)))
    console.print()


def render_summary_table(data: list[tuple[str, str]]) -> None:
    """Render a high-contrast key-value configuration summary table."""
    table = Table(
        title="[bold #00E5FF]✦ Active Configuration Summary ✦[/bold #00E5FF]",
        border_style="#00E5FF",
        box=ROUNDED,
        show_header=True,
        header_style="bold #BD00FF",
    )
    table.add_column("Setting / Component", style="bold white", width=30)
    table.add_column("Configured Value", style="#00FF88")

    for key, val in data:
        table.add_row(key, val)

    console.print(table)
    console.print()
