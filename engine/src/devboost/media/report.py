"""Injected reporter seam: live rich progress/steps/summary (real) or recorder (fake)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol, runtime_checkable

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn


@runtime_checkable
class Reporter(Protocol):
    def step(self, msg: str) -> None: ...
    def progress(
        self, label: str, total: int
    ) -> AbstractContextManager[Callable[[int], None]]: ...
    def summary(self, panel: str) -> None: ...


class RichReporter:
    def __init__(self) -> None:
        self._console = Console()

    def step(self, msg: str) -> None:
        self._console.print(f"[green]✓[/green] {msg}")

    @contextmanager
    def progress(self, label: str, total: int) -> Iterator[Callable[[int], None]]:
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            console=self._console,
        ) as prog:
            task_id = prog.add_task(label, total=total or None)

            def advance(n: int) -> None:
                prog.update(task_id, advance=n)

            yield advance

    def summary(self, panel: str) -> None:
        self._console.print(Panel(panel, expand=False))


class FakeReporter:
    def __init__(self) -> None:
        self.steps: list[str] = []
        self.summaries: list[str] = []
        self.progress_calls: list[tuple[str, int]] = []
        self.advances: list[int] = []

    def step(self, msg: str) -> None:
        self.steps.append(msg)

    @contextmanager
    def progress(self, label: str, total: int) -> Iterator[Callable[[int], None]]:
        self.progress_calls.append((label, total))

        def advance(n: int) -> None:
            self.advances.append(n)

        yield advance

    def summary(self, panel: str) -> None:
        self.summaries.append(panel)
