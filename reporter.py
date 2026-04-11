from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich import box
from cleaner import CleanResult

console = Console()

RISK_COLOURS = {
    "safe": "green",
    "review": "yellow",
    "inform-only": "cyan",
}

RISK_LABELS = {
    "safe": "SAFE",
    "review": "REVIEW",
    "inform-only": "INFO",
}


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / 1024**3:.1f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / 1024**2:.0f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def print_banner() -> None:
    console.print(Panel.fit(
        "[bold cyan]Mac Maid[/bold cyan] [dim]— macOS Maintenance Tool[/dim]",
        border_style="cyan"
    ))


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    )


def print_results(results: list[dict]) -> None:
    for r in results:
        risk = r["risk"]
        colour = RISK_COLOURS.get(risk, "white")
        label = RISK_LABELS.get(risk, risk.upper())
        total = format_size(r["total_size_bytes"])
        title = f"[{colour}][{label}][/{colour}] {r['category']} — {total}"

        if not r["items"]:
            console.print(Panel(f"[dim]{r['suggestion'] or 'Nothing found'}[/dim]",
                                title=title, border_style=colour))
            continue

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Item", style="white")
        table.add_column("Size", justify="right", style=colour)

        for item in r["items"][:20]:  # cap display at 20 rows
            table.add_row(item["label"], format_size(item["size_bytes"]))
        if len(r["items"]) > 20:
            table.add_row(f"[dim]...and {len(r['items']) - 20} more[/dim]", "")

        console.print(Panel(table, title=title, border_style=colour))
        if r["suggestion"]:
            console.print(f"  [dim]{r['suggestion']}[/dim]")


def print_item_detail(item: dict) -> None:
    meta_str = ""
    if "last_modified" in item["meta"]:
        meta_str = f" [dim](last modified {item['meta']['last_modified']})[/dim]"
    if "duplicate_of" in item["meta"]:
        meta_str = f" [dim](duplicate of {item['meta']['duplicate_of']})[/dim]"
    console.print(f"  {item['label']} — [yellow]{format_size(item['size_bytes'])}[/yellow]{meta_str}")


def build_summary_text(result: CleanResult) -> str:
    freed = format_size(result.bytes_freed)
    lines = [f"Cleaned: {result.moved} items, {freed} freed"]
    if result.errors:
        lines.append(f"Errors: {result.errors} item(s) could not be removed")
    if result.moved > 0:
        lines.append("Files moved to Trash — review before emptying.")
    return "\n".join(lines)


def print_summary(result: CleanResult) -> None:
    text = build_summary_text(result)
    console.print(Panel(text, title="[bold green]Done[/bold green]", border_style="green"))


def print_unattended_report(results: list[dict], clean_result: CleanResult) -> str:
    lines = ["# Mac Maid Nightly Report\n"]
    for r in results:
        lines.append(f"## {r['category']} [{r['risk'].upper()}]")
        lines.append(f"{r['suggestion'] or ''}\n")
        for item in r["items"][:10]:
            lines.append(f"- {item['label']} ({format_size(item['size_bytes'])})")
        if len(r["items"]) > 10:
            lines.append(f"- ...and {len(r['items']) - 10} more")
        lines.append("")
    lines.append(f"## Summary\n{build_summary_text(clean_result)}")
    return "\n".join(lines)
