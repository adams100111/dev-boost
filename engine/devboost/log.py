import typer


def info(msg: str) -> None:
    typer.echo(msg)


def ok(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.GREEN)


def skip(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.YELLOW)


def error(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)
