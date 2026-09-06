"""Command line interface.

newsanchor refresh          fetch feeds and build today's digest
newsanchor show             print the stored digest
newsanchor sources check    verify every feed URL actually resolves
newsanchor sources balance  report the roster's spectrum coverage
newsanchor balance          what your feed has actually consisted of
newsanchor serve            run the API for the React frontend
"""

from __future__ import annotations

import asyncio
from datetime import UTC

import typer
from rich.console import Console
from rich.table import Table

from . import db, llm
from .balance import roster_warnings
from .digest import DigestOptions, run_digest
from .models import LEAN_LABELS, LEAN_ORDER
from .sources import active_sources, default_registry

app = typer.Typer(help="A daily news feed built for balanced exposure.", no_args_is_help=True)
sources_app = typer.Typer(help="Inspect and validate the source registry.")
app.add_typer(sources_app, name="sources")

console = Console()


def _lean_of(article, registry):
    """Lean of the newsroom that reported it, not the outlet that reprinted it."""
    source = registry.get(article.syndicated_from or article.source_id)
    return source.lean if source else None


# Colour per spectrum position, reused across every table.
LEAN_STYLE = {-2: "blue", -1: "cyan", 0: "white", 1: "yellow", 2: "red"}


def _spectrum_bar(histogram: dict[int, int], width: int = 3) -> str:
    """Fixed-width cell per spectrum position, so bars line up down the page."""
    cells = []
    for lean in LEAN_ORDER:
        count = histogram.get(lean, 0)
        style = LEAN_STYLE[lean]
        fill = ("#" * min(count, width)).ljust(width, " ") if count else "-".ljust(width)
        cells.append(f"[{style}]{fill}[/{style}]")
    return "|".join(cells)


@app.command()
def refresh(
    window_hours: int = typer.Option(24, help="How far back to look."),
    min_sources: int = typer.Option(1, help="Drop stories carried by fewer than N outlets."),
    include_state_affiliated: bool = typer.Option(
        False, help="Include state-controlled outlets (labelled in output)."
    ),
    summarise: bool = typer.Option(
        False, help="Generate neutral summaries (needs ANTHROPIC_API_KEY)."
    ),
    limit: int = typer.Option(25, help="Stories to display."),
) -> None:
    """Fetch every active feed, build the digest, store it, and print it."""
    registry = default_registry()
    options = DigestOptions(
        window_hours=window_hours,
        min_sources=min_sources,
        include_state_affiliated=include_state_affiliated,
    )

    with console.status("Fetching feeds..."):
        digest = asyncio.run(run_digest(options, registry=registry))

    if summarise:
        if not llm.is_available():
            console.print(
                "[yellow]--summarise ignored: set ANTHROPIC_API_KEY and "
                "`pip install 'newsanchor[llm]'`[/yellow]"
            )
        else:
            with console.status("Writing neutral summaries..."):
                llm.summarise_digest(digest.stories, registry)

    with db.connect() as conn:
        db.save_digest(conn, digest)

    _render(digest, registry, limit)


@app.command()
def show(
    digest_id: int | None = typer.Option(None, help="Defaults to the most recent."),
    limit: int = typer.Option(25),
) -> None:
    """Print a stored digest without touching the network."""
    registry = default_registry()
    with db.connect() as conn:
        digest = db.load_digest(conn, digest_id)
    if digest is None:
        console.print("[red]No digest stored yet. Run `newsanchor refresh`.[/red]")
        raise typer.Exit(1)
    _render(digest, registry, limit)


def _render(digest, registry, limit: int) -> None:
    console.print(
        f"\n[bold]NewsAnchor[/bold]  {digest.generated_at:%Y-%m-%d %H:%M UTC}   "
        f"{digest.article_count} articles from {digest.source_count} sources   "
        f"{len(digest.stories)} stories\n"
    )

    for warning in digest.warnings:
        console.print(f"[yellow]roster: {warning}[/yellow]")
    if digest.errors:
        console.print(
            f"[dim]{len(digest.errors)} feed(s) failed; "
            f"run `newsanchor sources check` for detail[/dim]"
        )
    if digest.warnings or digest.errors:
        console.print()

    for index, story in enumerate(digest.stories[:limit], start=1):
        gaps = (
            "  [yellow]silent: "
            + ", ".join(LEAN_LABELS[g] for g in story.coverage_gaps)
            + "[/yellow]"
            if story.coverage_gaps
            else ""
        )
        console.print(f"[bold]{index:2d}.[/bold] {story.articles[0].title}")
        console.print(
            f"    {_spectrum_bar(story.lean_histogram)}   "
            f"balance {story.balance_score:.2f}  diversity {story.diversity_score:.2f}  "
            f"{len(story.source_ids)} outlets"
            + (
                f", {sum(1 for a in story.articles if a.syndicated_from)} reprints"
                if any(a.syndicated_from for a in story.articles)
                else ""
            )
            + gaps
        )
        if story.neutral_summary:
            console.print(f"    [dim]{story.neutral_summary}[/dim]")

        # Show how each side headlined it -- the actual point of the app.
        # Attribution follows the reporting newsroom, not the outlet that
        # reprinted it, so this listing agrees with the histogram above.
        seen: set[str] = set()
        for article in sorted(
            story.articles,
            key=lambda a: _lean_of(a, registry) if _lean_of(a, registry) is not None else 99,
        ):
            newsroom_id = article.syndicated_from or article.source_id
            if newsroom_id in seen:
                continue
            seen.add(newsroom_id)

            newsroom = registry.get(newsroom_id)
            lean = newsroom.lean if newsroom else None
            style = LEAN_STYLE.get(lean, "dim") if lean is not None else "dim"
            label = LEAN_LABELS.get(lean, "unrated") if lean is not None else "unrated"
            name = newsroom.name if newsroom else newsroom_id

            via = ""
            if article.syndicated_from:
                carriers = sorted(
                    {
                        a.source_id
                        for a in story.articles
                        if a.syndicated_from == article.syndicated_from
                    }
                )
                via = f" [dim](reprinted by {len(carriers)} outlets)[/dim]"
            console.print(f"      [{style}]{label:>10}[/{style}]  {name}: {article.title}{via}")
        console.print()


@sources_app.command("check")
def sources_check(
    timeout: float = typer.Option(15.0),
    include_state_affiliated: bool = typer.Option(False),
) -> None:
    """Fetch every configured feed once and report which ones are dead.

    Feed URLs rot constantly. Run this after cloning and whenever a source
    stops appearing in your digests.
    """
    import httpx

    registry = default_registry()
    targets = [
        (source, url)
        for source in active_sources(registry, include_state_affiliated=include_state_affiliated)
        for url in source.feeds
    ]

    table = Table("source", "status", "items", "feed")
    ok_count = 0

    async def probe() -> list[tuple]:
        from datetime import datetime, timedelta

        from .ingest.rss import USER_AGENT, entries_to_articles

        since = datetime.now(UTC) - timedelta(days=7)
        results = []
        sem = asyncio.Semaphore(8)

        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:

            async def one(source, url):
                async with sem:
                    try:
                        resp = await client.get(url, follow_redirects=True)
                        resp.raise_for_status()
                    except httpx.HTTPError as exc:
                        return (source, url, type(exc).__name__, 0)
                    try:
                        n = len(entries_to_articles(source, resp.content, since))
                    except Exception as exc:  # noqa: BLE001
                        return (source, url, f"parse: {exc}", 0)
                    return (source, url, "ok" if n else "empty", n)

            results = await asyncio.gather(*(one(s, u) for s, u in targets))
        return list(results)

    with console.status(f"Probing {len(targets)} feeds..."):
        results = asyncio.run(probe())

    for source, url, status, count in sorted(results, key=lambda r: (r[2] != "ok", r[0].id)):
        if status == "ok":
            ok_count += 1
        style = "green" if status == "ok" else ("yellow" if status == "empty" else "red")
        table.add_row(source.id, f"[{style}]{status}[/{style}]", str(count), url)

    console.print(table)
    console.print(f"\n{ok_count}/{len(results)} feeds healthy.")
    if ok_count < len(results):
        console.print(
            "[dim]Dead feeds are normal -- outlets move them without notice. "
            "Fix or remove them in data/sources.yaml.[/dim]"
        )


@sources_app.command("balance")
def sources_balance() -> None:
    """Report how well the roster itself covers the spectrum.

    A feed cannot be more balanced than its inputs. If this table is lopsided,
    every downstream 'coverage gap' is suspect.
    """
    registry = default_registry()
    active = active_sources(registry)

    table = Table("position", "sources", "outlets")
    for lean in LEAN_ORDER:
        ids = [s.name for s in active if s.lean == lean]
        style = LEAN_STYLE[lean]
        table.add_row(
            f"[{style}]{LEAN_LABELS[lean]}[/{style}]",
            str(len(ids)),
            ", ".join(ids) or "[red]none[/red]",
        )
    unrated = [s.name for s in active if s.lean is None]
    table.add_row("[dim]unrated[/dim]", str(len(unrated)), ", ".join(unrated))

    console.print(table)

    countries: dict[str, int] = {}
    for source in active:
        countries[source.country] = countries.get(source.country, 0) + 1
    console.print(
        "\ncountries: "
        + ", ".join(f"{c}={n}" for c, n in sorted(countries.items(), key=lambda kv: -kv[1]))
    )

    for warning in roster_warnings(active):
        console.print(f"[yellow]warning: {warning}[/yellow]")


@app.command()
def balance(days: int = typer.Option(30, help="Look-back window.")) -> None:
    """What your feed has actually consisted of, by outlet and by lean.

    Per-story scores can look healthy while the feed overall is three outlets
    in a trench coat. This is the check on that.
    """
    registry = default_registry()
    with db.connect() as conn:
        counts = db.reading_balance(conn, days)

    if not counts:
        console.print(f"[yellow]No articles stored in the last {days} days.[/yellow]")
        raise typer.Exit(1)

    total = sum(counts.values())
    table = Table("outlet", "lean", "articles", "share")
    for source_id, n in list(counts.items())[:20]:
        source = registry.get(source_id)
        lean = source.lean if source else None
        style = LEAN_STYLE.get(lean, "dim") if lean is not None else "dim"
        label = source.lean_label if source else "unrated"
        table.add_row(
            source.name if source else source_id,
            f"[{style}]{label}[/{style}]",
            str(n),
            f"{n / total:.1%}",
        )
    console.print(table)

    by_lean: dict[str, int] = {}
    for source_id, n in counts.items():
        source = registry.get(source_id)
        key = source.lean_label if source else "unrated"
        by_lean[key] = by_lean.get(key, 0) + n
    console.print("\nby position: " + "  ".join(f"{k} {v / total:.0%}" for k, v in by_lean.items()))

    top_share = max(counts.values()) / total
    if top_share > 0.30:
        top = max(counts, key=counts.get)
        name = registry[top].name if top in registry else top
        console.print(
            f"[yellow]{name} accounts for {top_share:.0%} of what you have been "
            f"shown. Consider adding sources or lowering max_source_share.[/yellow]"
        )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(False),
) -> None:
    """Run the API server that the React frontend talks to."""
    import uvicorn

    uvicorn.run("newsanchor.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
