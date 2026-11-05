"""Command-line entry point. Commands are filled in by later tasks (see contracts/cli.md)."""

import typer

from thinkbible_pipeline import __version__

app = typer.Typer(
    help="ThinkBible content pipeline: frozen sources -> reviewed, versioned content packs.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """ThinkBible content pipeline."""


@app.command()
def version() -> None:
    """Print the pipeline version."""
    typer.echo(__version__)
