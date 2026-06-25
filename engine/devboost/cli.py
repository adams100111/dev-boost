from typing import Annotated, Optional

import typer

from devboost import __version__

app = typer.Typer(help="dev-boost portable installer", no_args_is_help=True)


def _version(value: Optional[bool]) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=_version, is_eager=True),
    ] = None,
) -> None:
    """dev-boost CLI root."""
